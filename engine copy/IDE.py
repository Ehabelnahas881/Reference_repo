import os
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


from settings import user, password, database, host, port

db_config = {"host": host, "port": port, "user": user, "password": password, "database": database}

ASSETS = ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "HPQ", "AMD", "ARM"]

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("market_sync.log"), logging.StreamHandler()]
)
logger = logging.getLogger("SyncBot")

UTC = pytz.utc # UTC timezone for accurate market timing

# --- DATABASE ISOLATION LAYER ---
class AsyncDBWriter:
    """Manages non-blocking database storage with direct insertion."""
    def __init__(self, config):
        self.config = config
        self.queue = queue.Queue()
        threading.Thread(target=self._writer_loop, daemon=True, name="DB-Writer").start()

    def _get_conn(self):
        return psycopg2.connect(**self.config)

    def push_data(self, ticker, row):
        """Non-blocking push to the DB queue."""
        self.queue.put((ticker, row))

    def _writer_loop(self):
        """Internal loop that handles the direct insert to the database."""
        conn = self._get_conn()
        while True:
            ticker, row = self.queue.get()
            try:
                with conn.cursor() as cur:
                    # Construct full timestamp from date (row[0]) and time (row[1])
                    full_timestamp = f"{row[0]} {row[1]}"
                    
                    # DIRECT INSERT: No schema creation logic. 
                    # Placeholders fixed to %s for psycopg2 compatibility.
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
                    logger.info(f"DATA INSERTED for {ticker} | at {full_timestamp}")
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

# Global DB manager
db_writer = AsyncDBWriter(db_config)

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

def validate_market_day():
    """Talks only to DB. Returns True if (Next Session Date - 1) == Today."""
    try:
        conn = psycopg2.connect(**db_config)
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
                return (next_session) > datetime.now(UTC).date()
                #return (next_session - timedelta(days=1)) == datetime.now(UTC).date()
        return False
    except Exception as e:
        logger.error(f"Market Day DB Check Error: {e}")
        return False
    finally:
        if 'conn' in locals(): conn.close()

def validate_market_session():
    """Checks if current UTC time is between 00:00 and 08:00."""
    now_now = datetime.now(UTC).time()
    start = datetime.strptime("00:00", "%H:%M").time()
    end = datetime.strptime("13:41", "%H:%M").time()
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
                logger.info(f"[{self.ticker}] Consent wall detected. Resolving...")
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
                    logger.info(f"[{self.ticker}] Session Authenticated.")
            return True
        except Exception as e:
            logger.error(f"[{self.ticker}] Auth Failed: {e}")
            return False

    def fetch_price(self, session):
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}?guccounter=1"
            resp = session.get(url, headers=self.headers, impersonate=self.fp["impersonate"], timeout=12)
            if resp.status_code == 403: return "BLOCK"
            if resp.status_code == 429: return "RATE_LIMIT"
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-price"})
            return float(re.sub(r'[^\d.]', '', el.text)) if el else None
        except Exception:
            return None

def start(ticker):
    fp = random.choice(FINGERPRINTS)
    scraper = SyncScraper(ticker, fp)
    
    # Set a session life (e.g., 2 hours)
    session_expiry = datetime.now() + timedelta(minutes=random.randint(120, 180))
    
    with requests.Session(impersonate=fp["impersonate"]) as session:
        if not scraper.handle_cookies(session):
            return 

        # SINGLE LOOP: Checks both session age AND market window every iteration
        while datetime.now() < session_expiry:
            
            # 1. IMMEDIATE EXIT if window is closed
            if not validate_market_session():
                for asset in ASSETS:
                    logger.info(f"[{asset}] Market window closed. Returning to standby.")
                os._exit(0)
            # 2. SYNC TO TOP OF MINUTE
            now = datetime.now(UTC)
            wait_to_sync = 60 - now.second - (now.microsecond / 1000000)
            if wait_to_sync > 0:
                time.sleep(wait_to_sync)
            
            # 3. DATA COLLECTION LOGIC
            ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
            start_minute_time = time.time()
            prices = []
            
            schedule = sorted([random.uniform(5, 55) for _ in range(4)])
            for target_sec in schedule:
                elapsed = time.time() - start_minute_time
                sleep_needed = target_sec - elapsed
                if sleep_needed > 0: 
                    time.sleep(sleep_needed)
                
                p = scraper.fetch_price(session)
                
                if p in ["BLOCK", "RATE_LIMIT"]:
                    logger.warning(f"[{ticker}] Identity compromised. Rotating...")
                    return # Exit and let asset_worker_thread start a new session
                
                if isinstance(p, float): 
                    prices.append(p)
            
            # 4. DATABASE PUSH
            if len(prices) == 4:
                middle_vals = [prices[1], prices[2]]
                row = (
                    ts_val.date(), 
                    ts_val.strftime('%H:%M:%S'),
                    prices[0],         # Open
                    max(middle_vals),  # High
                    min(middle_vals),  # Low
                    prices[-1]         # Close
                )
                db_writer.push_data(ticker, row)
                logger.info(f"DATA | {ticker} | {row[1]} | O:{row[2]} H:{row[3]} L:{row[4]} C:{row[5]}")
            elif prices:
                logger.warning(f"[{ticker}] Incomplete data: {len(prices)}/4 points.")

        # If we exit the while loop, it means session_expiry was reached
        logger.info(f"[{ticker}] Session expired naturally. Refreshing...")
       
def asset_worker_thread(ticker):
    logger.info(f"[{ticker}] Worker initialized.")

    while True:
        # Check day AND time inside the loop
        is_market_day = validate_market_day()
        is_market_session = validate_market_session()

        if is_market_day and is_market_session:
            logger.info(f"[{ticker}] Inside window. Starting scraper session...")
            try:
                # When start(ticker) is called, it opens the session.
                start(ticker) 
                # When start(ticker) RETURNS, it means the window closed or 
                # session expired. The 'with' block inside start() 
                # has already closed the connection.
            except Exception as e:
                logger.error(f"[{ticker}] Scraper encountered error: {e}")
                time.sleep(60)
        else:
            # Recheck logic: If not time yet, or market closed
            now_utc = datetime.now(UTC).strftime('%H:%M')
            logger.info(f"[{ticker}] Standby ({now_utc} UTC). Rechecking in 5m...")
            time.sleep(60) # This is your 5-minute sleep
            

def initial():
    logger.info("SYNC ENGINE STARTING - DIRECT INSERT MODE")
    # Spawn workers only ONCE
    threads = []
    for asset in ASSETS:
        t = threading.Thread(target=asset_worker_thread, args=(asset,), name=f"Worker-{asset}")
        t.daemon = True
        t.start()
        threads.append(t)
        time.sleep(random.uniform(1, 3)) # Short stagger for DB connections
    
    logger.info(f"All {len(threads)} workers active. Main loop engaged.")
    
    # Keep the MainThread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Engine shutting down...")

def resolve_IDE(_obj, _info, financial_asset_list, environment_pk):
    """
    GraphQL resolver to trigger the scraper.
    The underscores on _obj and _info tell Pylance to ignore 'unused' warnings.
    """
    try:
        # 1. Log the receipt so you see a 'reaction' in the terminal
        logger.info(f"--- GraphQL API TRIGGER RECEIVED ---")
        logger.info(f"Assets IDs: {financial_asset_list} | Env: {environment_pk}")

        # 2. Trigger the scraper threads
        # We run it in a background thread so the API responds 'success: true' immediately
        scraper_thread = threading.Thread(target=initial, name="GraphQL-Trigger")
        scraper_thread.daemon = True
        scraper_thread.start()
        
        return {
            "success": True, 
            "error": None
        }
    except Exception as e:
        logger.error(f"Failed to start scraper via GraphQL: {e}")
        return {
            "success": False, 
            "error": str(e)
        }


