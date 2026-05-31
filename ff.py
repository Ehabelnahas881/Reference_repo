import time
import pytz
import random
import re
import logging
import sys
import threading
import queue
import psycopg2
from datetime import datetime, timedelta
from curl_cffi import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- CONFIGURATION ---
DB_CONFIG = {
    "user": "YFS",
    "password": "YFSpostgres2025",
    "database": "dyDATA_new",
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": 5432
}

ASSETS = ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "HPQ", "AMD", "ARM"]

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("market_sync.log"), logging.StreamHandler()]
)
logger = logging.getLogger("SyncBot")

UTC = pytz.utc

# --- DATABASE ISOLATION LAYER ---
class AsyncDBWriter:
    def __init__(self, config):
        self.config = config
        self.queue = queue.Queue()
        threading.Thread(target=self._writer_loop, daemon=True, name="DB-Writer").start()

    def _get_conn(self):
        return psycopg2.connect(**self.config)

    def push_data(self, ticker, row):
        self.queue.put((ticker, row))

    def _writer_loop(self):
        conn = self._get_conn()
        while True:
            ticker, row = self.queue.get()
            try:
                with conn.cursor() as cur:
                    full_timestamp = f"{row[0]} {row[1]}"
                    query = f'''
                        INSERT INTO "ASSET_{ticker}"."one_min_timeseries_data" (
                            "one_min_timeseries_date",
                            "one_min_timeseries_timestamp", 
                            "one_min_timeseries_OP_open_price",
                            "one_min_timeseries_HP_high_price", 
                            "one_min_timeseries_LP_low_price",
                            "one_min_timeseries_CP_close_price",
                            "one_min_timeseries_environment_PK"
                        ) VALUES (%s, %s, %s, %s, %s, %s, 4)
                        ON CONFLICT DO NOTHING
                    '''
                    cur.execute(query, (row[0], full_timestamp, row[2], row[3], row[4], row[5]))
                conn.commit()
            except Exception as e:
                logger.error(f"DB Write Error for {ticker}: {e}")
                conn.rollback()
                try: 
                    conn.close()
                    conn = self._get_conn()
                except: pass
            finally:
                self.queue.task_done()

db_writer = AsyncDBWriter(DB_CONFIG)

# --- SCRAPER LOGIC ---
STABLE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Referer": "https://finance.yahoo.com/",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

FINGERPRINTS = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", "impersonate": "chrome120"},
    {"ua": "Mozilla/5.0 (Windows NT 10.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", "impersonate": "chrome120"}
]

# --- UTILITY FUNCTIONS (NO WEB INTERACTION) ---

def is_market_day_in_db():
    """Talks only to DB. Returns True if (Next Session Date - 1) == Today."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            query = f'''
                    SELECT "financial_market_session_next_market_trading_session_date"::date 
                    FROM "dyTRADE"."financial_market_session_time_log"
                    ORDER BY "financial_market_session_time_PK" DESC
                    LIMIT 1;
            '''
            cur.execute(query)
            row = cur.fetchone()
            if row and row[0]:
                next_session = row[0]
                return (next_session) == datetime.now(UTC).date()
        return False
    except Exception as e:
        logger.error(f"Market Day DB Check Error: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def is_within_time_window():
    """Checks if current UTC time is between 00:00 and 08:00."""
    now_now = datetime.now(UTC).time()
    start = datetime.strptime("00:00", "%H:%M").time()
    end = datetime.strptime("08:00", "%H:%M").time()
    return start <= now_now <= end

class SyncScraper:
    def __init__(self, ticker, fingerprint):
        self.ticker = ticker
        self.fp = fingerprint
        self.headers = STABLE_HEADERS.copy()
        self.headers["User-Agent"] = self.fp["ua"]
        self.todayIsMarketDay = False


    def handle_cookies(self, session):
        try:
            resp = session.get(f"https://finance.yahoo.com/quote/{self.ticker}", headers=self.headers, impersonate=self.fp["impersonate"], timeout=15)
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    for btn in soup.find_all("button"):
                        if any(k in btn.get_text().lower() for k in ["agree", "accept", "akseptieren", "alle"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value", "agree")
                    time.sleep(random.uniform(2, 4))
                    session.post(action, data=payload, headers=self.headers, impersonate=self.fp["impersonate"], timeout=15)
            return True
        except Exception: return False

    def fetch_price(self, session):
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}?guccounter=1"
            resp = session.get(url, headers=self.headers, impersonate=self.fp["impersonate"], timeout=12)
            if resp.status_code in [403, 429]: return "BLOCK"
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-overnight-price"})
            return float(re.sub(r'[^\d.]', '', el.text)) if el else None
        except Exception: return None

def asset_worker_thread(ticker):
    
    # 1. Day Check (Only once at start)
    if not is_market_day_in_db():
        logger.info(f"[{ticker}] Not a market day. Thread exiting.")
        return

    logger.info(f"[{ticker}] Day validated. Monitoring [{datetime.now(UTC).date()}] window...")

    while True:
        # 2. Time Gate
        if not is_within_time_window():
            time.sleep(60)
            continue 
        while True:
            fp = random.choice(FINGERPRINTS)
            scraper = SyncScraper(ticker, fp)
            session_expiry = datetime.now() + timedelta(minutes=random.randint(120, 180))
            
            with requests.Session(impersonate=fp["impersonate"]) as session:
                if not scraper.handle_cookies(session):
                    time.sleep(60); continue
                
                while datetime.now() < session_expiry:
                    now = datetime.now(UTC)
                    wait_to_sync = 60 - now.second - (now.microsecond / 1000000)
                    time.sleep(max(0, wait_to_sync))
                    
                    ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                    start_minute_time = time.time()
                    prices = []
                    
                    schedule = sorted([random.uniform(5, 55) for _ in range(4)])
                    for target_sec in schedule:
                        elapsed = time.time() - start_minute_time
                        sleep_needed = target_sec - elapsed
                        if sleep_needed > 0: time.sleep(sleep_needed)
                        
                        p = scraper.fetch_price(session)
                        if p == "BLOCK":
                            session_expiry = datetime.now()
                            break
                        if isinstance(p, float): prices.append(p)
                    
                    if len(prices) == 4:
                        middle_vals = [prices[1], prices[2]]
                        row = (ts_val.date(), ts_val.strftime('%H:%M:%S'), prices[0], max(middle_vals), min(middle_vals), prices[-1])
                        db_writer.push_data(ticker, row)
                        logger.info(f"DATA | {ticker} | {row[1]} | O:{row[2]} H:{row[3]} L:{row[4]} C:{row[5]}")

            time.sleep(random.uniform(10, 20))

if __name__ == "__main__":
    logger.info("SYNC ENGINE STARTING - MARKET VALIDATION MODE ACTIVE")
    for asset in ASSETS:
        t = threading.Thread(target=asset_worker_thread, args=(asset,), name=f"Worker-{asset}")
        t.daemon = True
        t.start()
        time.sleep(random.uniform(2, 5))

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)