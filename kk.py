import time, pytz, os, random, uuid, logging, psycopg2, threading, re, json, sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from curl_cffi import requests
from bs4 import BeautifulSoup
from logging.handlers import TimedRotatingFileHandler

UTC = pytz.utc
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")

DB_CONFIG = {
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "user": "ehab.elnahas", "password": "test", "database": "dyDATA_new", "port": "5432"
}

# ──────────────────────────────────────────────
# BROWSER PROFILE ROTATION
# ──────────────────────────────────────────────
_CANDIDATE_PROFILES = [
    {
        "impersonate": "chrome124",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    },
    {
        "impersonate": "chrome120",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    },
    {
        "impersonate": "chrome110",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="110", "Not A(Brand";v="24", "Google Chrome";v="110"',
    },
    {
        "impersonate": "chrome107",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="107", "Chromium";v="107", "Not=A?Brand";v="24"',
    },
    {
        "impersonate": "edge101",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.47",
        "sec_ch_ua": '"Microsoft Edge";v="101", "Chromium";v="101", "Not_A Brand";v="99"',
    },
]

def _validate_profiles():
    valid = []
    for p in _CANDIDATE_PROFILES:
        try:
            requests.Session(impersonate=p["impersonate"])
            valid.append(p)
        except Exception:
            print(f"  [WARN] Profile '{p['impersonate']}' not supported -- skipping")
    if not valid:
        print("[FATAL] No browser profiles supported! Run: pip install --upgrade curl_cffi")
        sys.exit(1)
    return valid

BROWSER_PROFILES = _validate_profiles()

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.9,de;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
    "en-US,en;q=0.9,fr;q=0.7",
    "en-US,en;q=0.9,es;q=0.8,pt;q=0.7",
]

OS_PLATFORMS = [
    ('"Windows"', "Windows NT 10.0; Win64; x64"),
    ('"macOS"',   "Macintosh; Intel Mac OS X 10_15_7"),
]

PRICE_SELECTOR = "qsp-overnight-price"


def _seed_consent_cookies(session):
    """
    Pre-inject GDPR consent cookies BEFORE any request.
    This tells Yahoo 'user already consented' so the consent wall
    is never shown, regardless of IP location (Germany, EU, etc).
    """
    # These are the cookies Yahoo sets after clicking 'Alle akzeptieren'.
    # They don't contain personal data — just consent flags.
    session.cookies.set("GUCS", "AQABAAFZ", domain=".yahoo.com")
    session.cookies.set("GUC",
        "AQABAQFnIGBnQUIhTQTB&s=AQAAAFkXrDk-&g=YR8vZQ",
        domain=".yahoo.com")
    session.cookies.set("A1",
        "d=AQABBDkYYGcCELkw&S=AQAAAkYXrDk-",
        domain=".yahoo.com")
    session.cookies.set("A3",
        "d=AQABBDkYYGcCELkw&S=AQAAAkYXrDk-",
        domain=".yahoo.com")
    session.cookies.set("A1S",
        "d=AQABBDkYYGcCELkw&S=AQAAAkYXrDk-",
        domain=".yahoo.com")
    session.cookies.set("EuConsent",
        "true",
        domain=".yahoo.com")
    session.cookies.set("GUCS",
        "AQABAAFZ",
        domain=".yahoo.com")


class CookieManager:
    """
    Cookie manager for Yahoo Finance.
    Pre-seeds GDPR consent cookies so the consent wall is never hit.
    Refreshes real session cookies by visiting Yahoo like a browser.
    """

    COOKIE_MAX_AGE_SEC = 1800
    CRUMB_PATTERN = re.compile(r'"crumb"\s*:\s*"([^"]+)"')

    def __init__(self, session, headers_fn, logger):
        self._session = session
        self._headers_fn = headers_fn
        self._logger = logger
        self._lock = threading.Lock()
        self._crumb = None
        self._cookie_ts = None
        self._cookie_names = []
        self._consecutive_refresh_fails = 0

    @property
    def crumb(self):
        return self._crumb

    @property
    def cookies_valid(self):
        if self._cookie_ts is None:
            return False
        age = (datetime.now(UTC) - self._cookie_ts).total_seconds()
        return age < self.COOKIE_MAX_AGE_SEC

    def set_session(self, new_session):
        with self._lock:
            self._session = new_session
            self._cookie_ts = None
            self._crumb = None

    def ensure_valid(self, ticker):
        if not self.cookies_valid:
            self.refresh(ticker)

    def force_refresh(self, ticker):
        self._cookie_ts = None
        self.refresh(ticker)

    def refresh(self, ticker):
        with self._lock:
            if self.cookies_valid:
                return

            self._logger.info("[CookieManager] Starting cookie refresh...")
            try:
                # Pre-seed consent cookies so we skip GDPR wall
                _seed_consent_cookies(self._session)

                # Step 1 -- Homepage (with consent cookies already set)
                resp = self._session.get(
                    "https://finance.yahoo.com/",
                    headers=self._headers_fn(referer=None),
                    timeout=20,
                    allow_redirects=True,
                )
                time.sleep(random.uniform(1.5, 4.0))

                # If STILL on consent wall, submit the form
                if "consent.yahoo" in resp.url.lower():
                    self._logger.info("[CookieManager] Consent wall despite pre-seeded cookies, submitting form...")
                    resp = self._solve_consent(resp)
                    time.sleep(random.uniform(1.0, 3.0))

                # Step 2 -- Quote page
                quote_resp = self._session.get(
                    f"https://finance.yahoo.com/quote/{ticker}/",
                    headers=self._headers_fn(referer="https://finance.yahoo.com/"),
                    timeout=20,
                    allow_redirects=True,
                )
                time.sleep(random.uniform(1.0, 3.0))

                # If quote page redirected to consent, try once more
                if "consent.yahoo" in quote_resp.url.lower():
                    self._logger.warning("[CookieManager] Quote page hit consent, re-seeding and retrying...")
                    _seed_consent_cookies(self._session)
                    quote_resp = self._session.get(
                        f"https://finance.yahoo.com/quote/{ticker}/",
                        headers=self._headers_fn(referer="https://finance.yahoo.com/"),
                        timeout=20,
                        allow_redirects=True,
                    )
                    time.sleep(random.uniform(1.0, 3.0))

                # Verify we got a real quote page (not consent)
                if "consent.yahoo" in quote_resp.url.lower():
                    self._logger.error("[CookieManager] STILL on consent wall after all attempts!")
                else:
                    self._extract_crumb(quote_resp.text)

                self._cookie_ts = datetime.now(UTC)
                self._cookie_names = list(self._session.cookies.keys())
                self._consecutive_refresh_fails = 0

                self._logger.info(
                    "[CookieManager] Cookies refreshed OK -- "
                    "keys=%s, crumb=%s",
                    self._cookie_names,
                    "yes" if self._crumb else "no"
                )

            except Exception as e:
                self._consecutive_refresh_fails += 1
                backoff = min(120, 5 * (2 ** self._consecutive_refresh_fails))
                self._logger.error(
                    "[CookieManager] Refresh FAILED (%dx): %s -- retry in %ds",
                    self._consecutive_refresh_fails, e, backoff
                )
                time.sleep(backoff)

    def _solve_consent(self, resp):
        """Submit EU consent form if present."""
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            form = soup.find("form", {"method": "post"})
            if not form:
                self._logger.warning("[CookieManager] No POST form found on consent page")
                return resp

            action = form.get("action") or resp.url
            inputs = {
                inp.get("name"): inp.get("value", "")
                for inp in form.find_all("input")
                if inp.get("name")
            }

            # Find agree button
            for btn in form.find_all("button"):
                btn_name = btn.get("name", "")
                btn_value = btn.get("value", "")
                btn_text = btn.text.strip().lower()
                if any(kw in btn_text for kw in ["accept", "agree", "akzeptieren"]):
                    inputs[btn_name] = btn_value
                    self._logger.info("[CookieManager] Clicking consent button: '%s'", btn.text.strip())
                    break
                if btn_value.lower() in ["agree", "accept"]:
                    inputs[btn_name] = btn_value
                    break
            else:
                inputs["agree"] = "agree"

            result = self._session.post(
                action,
                data=inputs,
                headers=self._headers_fn(referer=resp.url),
                timeout=20,
                allow_redirects=True,
            )
            self._logger.info(
                "[CookieManager] Consent POST -- status=%d, url=%s",
                result.status_code, result.url[:80]
            )
            return result

        except Exception as e:
            self._logger.error("[CookieManager] Consent solving failed: %s", e)
            return resp

    def _extract_crumb(self, page_text):
        m = self.CRUMB_PATTERN.search(page_text)
        if m:
            self._crumb = m.group(1)
            self._logger.info("[CookieManager] Crumb extracted: %s...", self._crumb[:8])
        else:
            self._logger.warning("[CookieManager] Crumb not found in page source.")


class DataWorker:
    def __init__(self, ticker, table_name, store_to_db=False, start_delay=0):
        self.ticker = ticker
        self.table_name = table_name
        self.store_to_db = store_to_db
        self.start_delay = start_delay

        self.consecutive_failures = 0
        self.max_backoff = 600
        self.requests_since_rotate = 0
        self.rotate_interval = random.randint(30, 60)
        self.current_profile = None

        self._rotate_profile()
        self._setup_logger()
        self.cookie_mgr = CookieManager(
            session=self.session,
            headers_fn=self._build_headers,
            logger=self.logger,
        )

    def _rotate_profile(self):
        self.current_profile = random.choice(BROWSER_PROFILES)
        self.os_platform = random.choice(OS_PLATFORMS)
        self.session = requests.Session(impersonate=self.current_profile["impersonate"])
        # Pre-seed consent cookies on every new session
        _seed_consent_cookies(self.session)
        self.requests_since_rotate = 0
        self.rotate_interval = random.randint(30, 60)
        if hasattr(self, "cookie_mgr"):
            self.cookie_mgr.set_session(self.session)

    def _build_headers(self, referer=None):
        p = self.current_profile
        headers = {
            "User-Agent": p["ua"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": random.choice(ACCEPT_LANGUAGES),
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Cache-Control": random.choice(["max-age=0", "no-cache", ""]),
            "Sec-Ch-Ua": p["sec_ch_ua"],
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": self.os_platform[0],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin" if referer and "yahoo" in referer else "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",
            "Connection": "keep-alive",
            "Priority": "u=0, i",
        }
        if referer:
            headers["Referer"] = referer
        return {k: v for k, v in headers.items() if v}

    def _get_referer(self):
        return random.choice([
            f"https://finance.yahoo.com/quote/{self.ticker}/",
            f"https://finance.yahoo.com/quote/{self.ticker}/",
            "https://finance.yahoo.com/",
            "https://finance.yahoo.com/markets/",
            None,
        ])

    def _is_blocked(self, resp):
        if resp.status_code in (403, 429, 503, 999):
            return True
        text_lower = resp.text[:5000].lower()
        signals = [
            "captcha" in text_lower,
            "perimeterx" in text_lower,
            "px-captcha" in text_lower,
            "blocked" in text_lower and len(resp.text) < 5000,
            "distil" in text_lower,
            "are you a human" in text_lower,
            "unusual traffic" in text_lower,
            "recaptcha" in text_lower,
            "challenge" in text_lower and "security" in text_lower,
        ]
        return any(signals)

    def _handle_block(self):
        self.consecutive_failures += 1
        backoff = min(
            self.max_backoff,
            (2 ** self.consecutive_failures) * 10 + random.uniform(0, 15)
        )
        self.logger.warning(
            "BLOCKED -- failure #%d, backing off %ds, rotating profile",
            self.consecutive_failures, int(backoff)
        )
        time.sleep(backoff)
        self._rotate_profile()
        self.cookie_mgr.force_refresh(self.ticker)

    def _setup_logger(self):
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        self.logger = logging.getLogger(self.ticker)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            # File handler
            file_handler = TimedRotatingFileHandler(
                os.path.join(LOG_DIR, f"{self.ticker}.log"),
                when="midnight", delay=True
            )
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.logger.addHandler(file_handler)

            # Console handler -- force UTF-8 on Windows
            console_handler = logging.StreamHandler(
                open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
            )
            console_handler.setFormatter(
                logging.Formatter('%(asctime)s - [%(name)s] %(message)s')
            )
            self.logger.addHandler(console_handler)

    def _warm_up(self):
        self.logger.info("Warming up session...")
        try:
            self.session.get(
                "https://finance.yahoo.com/",
                headers=self._build_headers(referer=None),
                timeout=20,
            )
            time.sleep(random.uniform(2.0, 5.0))
            self.session.get(
                f"https://finance.yahoo.com/quote/{self.ticker}/",
                headers=self._build_headers(referer="https://finance.yahoo.com/"),
                timeout=20,
            )
            time.sleep(random.uniform(1.5, 4.0))
            self.logger.info("Warm-up complete")
        except Exception as e:
            self.logger.warning("Warm-up failed (non-fatal): %s", e)

    def fetch_price(self):
        try:
            self.requests_since_rotate += 1

            if self.requests_since_rotate >= self.rotate_interval:
                self.logger.info("Rotating browser profile...")
                self._rotate_profile()
                self._warm_up()

            self.cookie_mgr.ensure_valid(self.ticker)

            referer = self._get_referer()
            headers = self._build_headers(referer=referer)

            url = f"https://finance.yahoo.com/quote/{self.ticker}/"
            resp = self.session.get(url, headers=headers, timeout=15)

            if resp.status_code != 200 or self._is_blocked(resp):
                self.logger.error("HTTP %d or block detected", resp.status_code)
                self._handle_block()
                return None

            self.consecutive_failures = 0

            soup = BeautifulSoup(resp.text, 'html.parser')
            el = soup.find(attrs={"data-testid": PRICE_SELECTOR})
            if el and el.text:
                raw = el.text.strip().replace(',', '')
                try:
                    price = float(raw)
                    self.logger.info("Price fetched: %s", price)
                    return price
                except ValueError:
                    self.logger.warning("Could not parse price text: '%s'", raw)
                    return None

            self.logger.warning("Selector '%s' not found in page", PRICE_SELECTOR)
            return None

        except Exception as e:
            self.logger.error("Fetch Logic Fail: %s", e)
        return None

    def run(self):
        if self.start_delay > 0:
            self.logger.info("Staggering start by %.1fs", self.start_delay)
            time.sleep(self.start_delay)

        self.logger.info("Worker initialized for %s | selector: %s", self.ticker, PRICE_SELECTOR)
        self._warm_up()
        self.cookie_mgr.force_refresh(self.ticker)

        while True:
            try:
                now = datetime.now(UTC)
                seconds_to_next = 60 - now.second - (now.microsecond / 1e6)
                sync_jitter = random.uniform(0.2, 1.5)
                time.sleep(max(0, seconds_to_next + sync_jitter))

                candle_start = time.monotonic()
                ts = datetime.now(UTC).replace(second=0, microsecond=0)

                price = self.fetch_price()
                if not price:
                    self.logger.warning("No OPEN price for %s -- retrying next cycle", ts)
                    continue

                h, l, c = price, price, price
                CANDLE_DURATION = 55.0
                SAMPLES = 5

                for i in range(SAMPLES):
                    elapsed = time.monotonic() - candle_start
                    remaining = CANDLE_DURATION - elapsed

                    if remaining <= 2.0:
                        self.logger.info("Candle time exhausted after %d sub-samples", i)
                        break

                    samples_left = SAMPLES - i
                    base_interval = remaining / samples_left
                    jitter = random.uniform(-0.2, 0.2) * base_interval
                    sleep_time = max(1.0, min(base_interval + jitter, remaining - 1.0))

                    time.sleep(sleep_time)

                    t = self.fetch_price()
                    if t:
                        h = max(h, t)
                        l = min(l, t)
                        c = t

                if self.store_to_db:
                    try:
                        conn = psycopg2.connect(**DB_CONFIG, connect_timeout=5)
                        with conn.cursor() as cur:
                            pk = int(time.time() * 1000) + random.randint(0, 999)
                            cur.execute(
                                f'INSERT INTO {self.table_name} '
                                f'("one_min_timeseries_date", "one_min_timeseries_timestamp", '
                                f'"one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", '
                                f'"one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price", '
                                f'"one_min_timeseries_PK", "one_min_timeseries_UUID", '
                                f'"one_min_timeseries_creation_date_time", "one_min_timeseries_activity_status", '
                                f'"one_min_timeseries_financial_data_source_PK", "one_min_timeseries_ID") '
                                f'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                                (ts.date(), ts, price, h, l, c, pk, str(uuid.uuid4()),
                                 datetime.now(UTC), 1, 1, 1)
                            )
                        conn.commit()
                        conn.close()
                        self.logger.info("DB_FLUSH: %s | O:%s H:%s L:%s C:%s", ts, price, h, l, c)
                    except Exception as db_e:
                        self.logger.error("DB Fail: %s", db_e)
                else:
                    self.logger.info("LOG_ONLY: %s | O:%s H:%s L:%s C:%s", ts, price, h, l, c)

                elapsed_total = time.monotonic() - candle_start
                if elapsed_total < 58.0:
                    time.sleep(58.0 - elapsed_total)

            except Exception as e:
                print(f"THREAD CRASH RECOVERY [{self.ticker}]: {e}")
                time.sleep(random.uniform(10, 30))


# ──────────────────────────────────────────────
# FLASK + LAUNCH
# ──────────────────────────────────────────────
app = Flask(__name__)

@app.route("/graphql", methods=["POST"])
def gq():
    return jsonify({"data": {"status": "Online"}})

if __name__ == "__main__":
    print(f"Log directory: {LOG_DIR}")
    print(f"Supported profiles: {[p['impersonate'] for p in BROWSER_PROFILES]}")

    assets = [
        ("TSLA",    '"TEST_TSLA"."one_min_timeseries_data"', True),
        ("BTC-USD", "LOG", False),
        ("NVDA",    "LOG", False),
    ]
    for i, (ticker, table, store) in enumerate(assets):
        delay = i * random.uniform(7, 20)
        threading.Thread(
            target=DataWorker(ticker, table, store, start_delay=delay).run,
            daemon=True,
        ).start()
        print(f"Spawned {ticker} (delay: {delay:.1f}s, store_to_db: {store})")

    app.run(host="0.0.0.0", port=3989)