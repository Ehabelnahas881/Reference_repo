import time, pytz, os, random, uuid, logging, psycopg2, threading, re, json, sys
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from curl_cffi import requests
from bs4 import BeautifulSoup
from logging.handlers import TimedRotatingFileHandler

UTC = pytz.utc
DB_CONFIG = {
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "user": "ehab.elnahas", "password": "test", "database": "dyDATA_new", "port": "5432"
}

# ──────────────────────────────────────────────
# BROWSER PROFILE ROTATION
# ──────────────────────────────────────────────
BROWSER_PROFILES = [
    {
        "impersonate": "chrome124",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    },
    {
        "impersonate": "chrome126",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
    },
    {
        "impersonate": "chrome131",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "impersonate": "edge101",
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.47",
        "sec_ch_ua": '"Microsoft Edge";v="101", "Chromium";v="101", "Not_A Brand";v="99"',
    },
]

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

# ──────────────────────────────────────────────
# MARKET SESSION CONFIG
# ──────────────────────────────────────────────
def get_market_session_config():
    try:
        now_utc = datetime.now(UTC)
        curr = now_utc.hour + (now_utc.minute / 60)
        if 1.0 <= curr < 9.5:     return "qsp-overnight-price", "Overnight", 1
        elif 9.5 <= curr < 14.5:  return "qsp-pre-price", "Pre-Market", 2
        elif 14.5 <= curr < 21.0: return "qsp-price", "Regular", 3
        else:                      return "qsp-post-price", "Post-Market", 4
    except:
        return "qsp-post-price", "Unknown", 4


class CookieManager:
    """
    Dynamic, renewable cookie + crumb manager for Yahoo Finance.
    - Fetches fresh cookies by visiting Yahoo Finance like a real browser.
    - Extracts the 'crumb' token from the page for API compatibility.
    - Tracks cookie age and auto-renews before expiry.
    - Forces immediate renewal on any auth/block failure.
    - Thread-safe via a lock.
    """

    COOKIE_MAX_AGE_SEC = 1800          # force refresh every 30 min
    COOKIE_REFRESH_ON_FAIL = True      # auto-refresh on block detection
    CRUMB_PATTERN = re.compile(r'"crumb"\s*:\s*"([^"]+)"')

    def __init__(self, session, profile_fn, headers_fn, logger):
        self._session = session
        self._profile_fn = profile_fn
        self._headers_fn = headers_fn
        self._logger = logger
        self._lock = threading.Lock()
        self._crumb = None
        self._cookie_ts = None             # when cookies were last obtained
        self._cookie_names = []
        self._consecutive_refresh_fails = 0

    @property
    def crumb(self):
        return self._crumb

    @property
    def cookies_valid(self):
        """Return True if cookies exist and haven't expired."""
        if self._cookie_ts is None:
            return False
        age = (datetime.now(UTC) - self._cookie_ts).total_seconds()
        return age < self.COOKIE_MAX_AGE_SEC

    def set_session(self, new_session):
        """Called after profile rotation — replaces the underlying session."""
        with self._lock:
            self._session = new_session
            self._cookie_ts = None       # invalidate: new session has no cookies
            self._crumb = None

    def ensure_valid(self, ticker):
        """If cookies are stale or missing, refresh them. Thread-safe."""
        if not self.cookies_valid:
            self.refresh(ticker)

    def force_refresh(self, ticker):
        """Unconditionally refresh (call after block detection)."""
        self._cookie_ts = None
        self.refresh(ticker)

    def refresh(self, ticker):
        """
        Full cookie renewal flow:
          1. GET finance.yahoo.com  → obtain base cookies
          2. Handle consent/GUCE redirect if present
          3. GET quote page          → obtain quote-specific cookies + crumb
        """
        with self._lock:
            # double-check inside lock
            if self.cookies_valid:
                return

            self._logger.info("[CookieManager] Starting cookie refresh...")
            try:
                # Step 1 — Homepage visit
                resp = self._session.get(
                    "https://finance.yahoo.com/",
                    headers=self._headers_fn(referer=None),
                    timeout=20,
                    allow_redirects=True,
                )
                time.sleep(random.uniform(1.5, 4.0))

                # Step 2 — Consent / GUCE handling
                if "consent" in resp.url.lower() or "guce" in resp.url.lower():
                    self._logger.info("[CookieManager] Consent page detected — accepting...")
                    self._handle_consent(resp)

                # Step 3 — Quote page visit (sets quote-scoped cookies + yields crumb)
                quote_resp = self._session.get(
                    f"https://finance.yahoo.com/quote/{ticker}/",
                    headers=self._headers_fn(referer="https://finance.yahoo.com/"),
                    timeout=20,
                    allow_redirects=True,
                )
                time.sleep(random.uniform(1.0, 3.0))

                # Extract crumb from page source
                self._extract_crumb(quote_resp.text)

                # Record state
                self._cookie_ts = datetime.now(UTC)
                self._cookie_names = list(self._session.cookies.keys())
                self._consecutive_refresh_fails = 0

                self._logger.info(
                    f"[CookieManager] Cookies refreshed OK — "
                    f"keys={self._cookie_names}, crumb={'yes' if self._crumb else 'no'}"
                )

            except Exception as e:
                self._consecutive_refresh_fails += 1
                backoff = min(120, 5 * (2 ** self._consecutive_refresh_fails))
                self._logger.error(
                    f"[CookieManager] Refresh FAILED ({self._consecutive_refresh_fails}x): {e} "
                    f"— retry in {backoff}s"
                )
                time.sleep(backoff)

    def _handle_consent(self, resp):
        """Submit the EU/GUCE consent form if present."""
        try:
            soup = BeautifulSoup(resp.text, "html.parser")
            form = soup.find("form", {"method": "post"})
            if form:
                action = form.get("action", resp.url)
                inputs = {
                    inp.get("name"): inp.get("value", "")
                    for inp in form.find_all("input")
                    if inp.get("name")
                }
                self._session.post(
                    action,
                    data=inputs,
                    headers=self._headers_fn(referer=resp.url),
                    timeout=20,
                    allow_redirects=True,
                )
                time.sleep(random.uniform(1.0, 3.0))
                self._logger.info("[CookieManager] Consent form submitted.")
        except Exception as e:
            self._logger.warning(f"[CookieManager] Consent handling error: {e}")

    def _extract_crumb(self, page_text):
        """Pull the crumb token from page HTML/JS."""
        m = self.CRUMB_PATTERN.search(page_text)
        if m:
            self._crumb = m.group(1)
            self._logger.info(f"[CookieManager] Crumb extracted: {self._crumb[:8]}...")
        else:
            self._logger.warning("[CookieManager] Crumb not found in page source.")


class DataWorker:
    def __init__(self, ticker, table_name, store_to_db=False, start_delay=0):
        self.ticker = ticker
        self.table_name = table_name
        self.store_to_db = store_to_db
        self.start_delay = start_delay

        # Anti-detection state
        self.consecutive_failures = 0
        self.max_backoff = 600
        self.requests_since_rotate = 0
        self.rotate_interval = random.randint(30, 60)
        self.current_profile = None

        # Build initial session + cookie manager
        self._rotate_profile()
        self._setup_logger()
        self.cookie_mgr = CookieManager(
            session=self.session,
            profile_fn=self._rotate_profile,
            headers_fn=self._build_headers,
            logger=self.logger,
        )

    # ──────────────────────────────────────────
    # SESSION & PROFILE MANAGEMENT
    # ──────────────────────────────────────────
    def _rotate_profile(self):
        """Switch TLS fingerprint + User-Agent + Sec-Ch-Ua to a new browser identity."""
        self.current_profile = random.choice(BROWSER_PROFILES)
        self.os_platform = random.choice(OS_PLATFORMS)
        self.session = requests.Session(impersonate=self.current_profile["impersonate"])
        self.requests_since_rotate = 0
        self.rotate_interval = random.randint(30, 60)
        # Notify cookie manager about the new session (if it exists yet)
        if hasattr(self, "cookie_mgr"):
            self.cookie_mgr.set_session(self.session)

    def _build_headers(self, referer=None):
        """Generate realistic browser headers for each request."""
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
        """Simulate natural navigation patterns."""
        return random.choice([
            f"https://finance.yahoo.com/quote/{self.ticker}/",
            f"https://finance.yahoo.com/quote/{self.ticker}/",
            "https://finance.yahoo.com/",
            "https://finance.yahoo.com/markets/",
            None,
        ])

    # ──────────────────────────────────────────
    # BOT DETECTION
    # ──────────────────────────────────────────
    def _is_blocked(self, resp):
        """Detect bot protection / challenge pages."""
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
        """Exponential backoff + full session reset on detection."""
        self.consecutive_failures += 1
        backoff = min(
            self.max_backoff,
            (2 ** self.consecutive_failures) * 10 + random.uniform(0, 15)
        )
        self.logger.warning(
            f"BLOCKED — failure #{self.consecutive_failures}, "
            f"backing off {backoff:.0f}s, rotating profile + refreshing cookies"
        )
        time.sleep(backoff)
        self._rotate_profile()
        # Force-refresh cookies on the new session immediately
        self.cookie_mgr.force_refresh(self.ticker)

    # ──────────────────────────────────────────
    # LOGGER
    # ──────────────────────────────────────────
    def _setup_logger(self):
        if not os.path.exists('/app/logs'):
            os.makedirs('/app/logs')
        self.logger = logging.getLogger(self.ticker)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            handler = TimedRotatingFileHandler(
                f"/app/logs/{self.ticker}.log", when="midnight", delay=True
            )
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.logger.addHandler(handler)

    # ──────────────────────────────────────────
    # WARM-UP
    # ──────────────────────────────────────────
    def _warm_up(self):
        """Simulate natural browsing session at startup."""
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
            self.logger.warning(f"Warm-up failed (non-fatal): {e}")

    # ──────────────────────────────────────────
    # PRICE FETCH  (same selectors & logic)
    # ──────────────────────────────────────────
    def fetch_price(self):
        try:
            self.requests_since_rotate += 1

            # Rotate browser profile periodically
            if self.requests_since_rotate >= self.rotate_interval:
                self.logger.info("Rotating browser profile...")
                self._rotate_profile()
                self._warm_up()

            # >>> DYNAMIC COOKIES: ensure valid before every fetch <<<
            self.cookie_mgr.ensure_valid(self.ticker)

            referer = self._get_referer()
            headers = self._build_headers(referer=referer)

            url = f"https://finance.yahoo.com/quote/{self.ticker}/"
            resp = self.session.get(url, headers=headers, timeout=15)

            if resp.status_code != 200 or self._is_blocked(resp):
                self.logger.error(f"HTTP {resp.status_code} or block detected")
                self._handle_block()       # _handle_block already force-refreshes cookies
                return None

            self.consecutive_failures = 0

            # ─── Strategy 1: JSON search ───
            match = re.search(r'root\.App\.main\s*=\s*(\{.*?\});', resp.text)
            if match:
                data = json.loads(match.group(1))
                price_store = data['context']['dispatcher']['stores']['QuoteSummaryStore']['price']
                for field in ['overnightPrice', 'postMarketPrice', 'preMarketPrice',
                              'regularMarketPrice', 'previousClose']:
                    val = price_store.get(field, {}).get('raw')
                    if val and float(val) > 0:
                        return float(val)

            # ─── Strategy 2: BS4 with declared selectors ───
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Try the session-specific selector first, then fallback list
            session_selector, _, _ = get_market_session_config()
            ordered_selectors = [session_selector]
            for tid in [ "qsp-overnight-price" , "qsp-overnight-price"]:
                if tid not in ordered_selectors:
                    ordered_selectors.append(tid)

            for tid in ordered_selectors:
                el = soup.find(attrs={"data-testid": tid})
                if el and el.text:
                    raw = el.text.strip().replace(',', '')
                    try:
                        return float(raw)
                    except ValueError:
                        continue

        except Exception as e:
            self.logger.error(f"Fetch Logic Fail: {e}")
        return None

    # ──────────────────────────────────────────
    # MAIN LOOP — 1 OHLC RECORD PER 1 MINUTE
    # ──────────────────────────────────────────
    def run(self):
        if self.start_delay > 0:
            self.logger.info(f"Staggering start by {self.start_delay:.1f}s")
            time.sleep(self.start_delay)

        self.logger.info(f"Worker initialized for {self.ticker}")
        self._warm_up()
        # Initial cookie acquisition via CookieManager
        self.cookie_mgr.force_refresh(self.ticker)

        while True:
            try:
                # ─── SYNC TO TOP OF NEXT MINUTE ───
                now = datetime.now(UTC)
                seconds_to_next = 60 - now.second - (now.microsecond / 1e6)
                sync_jitter = random.uniform(0.2, 1.5)
                time.sleep(max(0, seconds_to_next + sync_jitter))

                candle_start = time.monotonic()
                ts = datetime.now(UTC).replace(second=0, microsecond=0)
                _, _, sid = get_market_session_config()

                # ─── OPEN PRICE ───
                price = self.fetch_price()
                if not price:
                    self.logger.warning(f"No OPEN price for {ts} — retrying next cycle")
                    continue

                # ─── SAMPLE H/L/C WITHIN 55s CEILING ───
                h, l, c = price, price, price
                CANDLE_DURATION = 55.0
                SAMPLES = 5

                for i in range(SAMPLES):
                    elapsed = time.monotonic() - candle_start
                    remaining = CANDLE_DURATION - elapsed

                    if remaining <= 2.0:
                        self.logger.info(f"Candle time exhausted after {i} sub-samples")
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
                        c = t               # last valid price becomes Close

                # ─── DB WRITE / LOG  (exactly 1 record per minute) ───
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
                                 datetime.now(UTC), 1, 1, sid)
                            )
                        conn.commit()
                        conn.close()
                        self.logger.info(f"DB_FLUSH: {ts} | O:{price} H:{h} L:{l} C:{c}")
                    except Exception as db_e:
                        self.logger.error(f"DB Fail: {db_e}")
                else:
                    self.logger.info(f"LOG_ONLY: {ts} | O:{price} H:{h} L:{l} C:{c}")

                # ─── IDLE UNTIL NEXT MINUTE BOUNDARY ───
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
        print(f"Spawned {ticker} (delay: {delay:.1f}s)")

    app.run(host="0.0.0.0", port=3989)