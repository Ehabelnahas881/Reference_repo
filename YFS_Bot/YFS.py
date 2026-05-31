import os
import copy  
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

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(threadName)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("market_sync.log"), logging.StreamHandler()]
)
logger = logging.getLogger("SyncBot")


from settings import user, password, database, host, port, user_agent
db_config = {"host": host, "port": port, "user": user, "password": password, "database": database}

import copy

FINGERPRINTS = user_agent

# Mapping table ensuring curl_cffi handshakes map natively without failing on local dependencies
CURL_CFFI_MAP = {
    "chrome124": "chrome124",
    "chrome123": "chrome120",
    "chrome120": "chrome120",
    "chrome119": "chrome119",
    "edge122": "chrome120",      # Chromium-based: fallback safely to robust Chrome handshake
    "edge120": "chrome120",      # Chromium-based: fallback safely to robust Chrome handshake
    "safari17_2_1": "safari",    # Maps down to generic compiled Safari TLS footprint
    "ff124": "firefox",          # Maps down to generic compiled Firefox TLS footprint
    "ff123": "firefox"           # Maps down to generic compiled Firefox TLS footprint
}

HUMANOID_PROFILES = []
for profile in FINGERPRINTS:
    if isinstance(profile, dict):
        orig_impersonate = profile.get("impersonate")
        # Translate the target string if it's found in our mapping schema
        if orig_impersonate in CURL_CFFI_MAP:
            cloned_profile = copy.deepcopy(profile)
            cloned_profile["impersonate"] = CURL_CFFI_MAP[orig_impersonate]
            HUMANOID_PROFILES.append(cloned_profile)
        else:
            # Fallback protect: keep profile using Chrome signature if unknown
            cloned_profile = copy.deepcopy(profile)
            cloned_profile["impersonate"] = "chrome120"
            HUMANOID_PROFILES.append(cloned_profile)

# Safe baseline initialization for application fallback layers
STABLE_HEADERS = copy.deepcopy(HUMANOID_PROFILES[0].get("headers", {})) if HUMANOID_PROFILES else {}

logger.info(f"Engine pool balanced. Total active rotational signatures: {len(HUMANOID_PROFILES)}/10")
UTC = pytz.utc # UTC timezone for accurate market timing
network_gate = threading.BoundedSemaphore(5)

def generate_random_url(ticker):
    cb = int(time.time() * 100) + random.randint(1000, 9999)
    
    # Randomly shuffle common industry cache-busting keys 
    # to completely strip the ML firewall of a uniform query signature
    cb_key = random.choice(["_cb", "v", "ver", "ts", "nc", "refresh"])
    
    url_patterns = [
        f"https://finance.yahoo.com/quote/{ticker}?p={ticker}&.tsrc=fin-srch&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}/?p={ticker}&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}?guccounter=1&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}/?guccounter=2&p={ticker}&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}?p={ticker}&.tsrc=apple-ww&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}?{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}/?{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}?p={ticker}&.tsrc=yhoo&guccounter=1&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}?.tsrc=fin-srch-v1&guccounter={random.randint(1,2)}&{cb_key}={cb}",
        f"https://finance.yahoo.com/quote/{ticker}/?.tsrc=apple-ww&{cb_key}={cb}"
    ]
    return random.choice(url_patterns)

# --- DATABASE ISOLATION LAYER ---
class AsyncDBWriter:
    """Manages non-blocking database storage with automatic connection recovery."""
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
        """Internal loop handling direct insertion with total fault resilience."""
        conn = None
        while True:
            ticker, row = self.queue.get()
            try:
                # Lazy initialization / reconnection safety check
                if conn is None or conn.closed != 0:
                    try:
                        if conn: conn.close()
                    except Exception: pass
                    conn = self._get_conn()
                
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
                    logger.info(f"DATA INSERTED for {ticker} | at {full_timestamp}")
                conn.commit()
                
            except Exception as e:
                logger.error(f"DB Write Error for {ticker}: {e}. Attempting recovery...")
                # Defensive Rollback Strategy
                if conn:
                    try:
                        conn.rollback()
                    except Exception as rb_err:
                        logger.debug(f"Rollback skipped (connection dead): {rb_err}")
                    try:
                        conn.close()
                    except Exception: pass
                # Force connection to turn to None so next cycle forces a clean reconnect
                conn = None
                
            finally:
                self.queue.task_done()

# Global DB manager
db_writer = AsyncDBWriter(db_config)

def validate_market_session():
    """Checks if current UTC time is between 07:18 and 11:59 UTC."""
    # Get current date and time in UTC
    now_utc = datetime.now(UTC)
    
    # Dynamically build today's boundary limits directly in UTC
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = now_utc.replace(hour=8, minute=0, second=0, microsecond=0)
    
    # Direct comparison including the full datetime payload
    return start <= now_utc <= end

class SyncScraper:
    def __init__(self, ticker, profile):
        self.ticker = ticker
        self.profile = profile
        self.headers = profile["headers"].copy() # Locked matched profile header dict
        self.todayIsMarketDay = False

    def handle_cookies(self, session):
        try:
            # Wrap cookie intake execution with the global gate token
            with network_gate:
                resp = session.get(
                    f"https://finance.yahoo.com/quote/{self.ticker}", 
                    headers=self.headers, 
                    impersonate=self.profile["impersonate"], 
                    timeout=(5, 20)
                )
            
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
                    
                    with network_gate:
                        session.post(action, data=payload, headers=self.headers, impersonate=self.profile["impersonate"], timeout=(5, 20))
                    logger.info(f"[{self.ticker}] Session Authenticated.")
            return True
        except Exception as e:
            logger.error(f"[{self.ticker}] Auth Failed: {e}")
            return False

    def fetch_price(self, session):
        try:
            # Generate a completely unique, structurally randomized URL syntax for THIS specific request
            url = generate_random_url(self.ticker)
            
            # Dynamically mismatch the referrer structure (with or without trailing slash) 
            # to make the request chain look like chaotic human browsing clickstream
            
            # --- CONTEXTUAL SITE NAVIGATION GRAPH ---
            # Randomizes inbound search directions to prevent predictable toggling signatures
            referer_options = [
                f"https://finance.yahoo.com/quote/{self.ticker}",
                f"https://finance.yahoo.com/quote/{self.ticker}/",
                "https://finance.yahoo.com/",
                f"https://finance.yahoo.com/quote/{self.ticker}?p={self.ticker}"
            ]
            
            # Simulates subtle behavioral variances in human browser navigation properties
            sec_fetch_user = random.choice(["?1", None])

            navigation_headers = {
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
                "Referer": random.choice(referer_options)
            }

            if sec_fetch_user:
                navigation_headers["Sec-Fetch-User"] = sec_fetch_user
            else:
                self.headers.pop("Sec-Fetch-User", None)

            self.headers.update(navigation_headers)
            # Pass safely through our threading concurrency limit gate
            with network_gate:
                resp = session.get(url, headers=self.headers, impersonate=self.profile["impersonate"], timeout=(5, 20))
            
            if resp.status_code == 403: return "BLOCK"
            if resp.status_code == 429: return "RATE_LIMIT"
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-overnight-price"})
            #el = soup.find(attrs={"data-testid": "qsp-post-price"}) or soup.find(attrs={"data-field": "qsp-overnight-price"}) or soup.find(attrs={"data-field": "qsp-pre-price"})
            return float(re.sub(r'[^\d.]', '', el.text)) if el else None
        except Exception as e:
            logger.error(f"[{self.ticker}] Exception during fetch_price: {e}")
            return None

def run(ticker, time_offset=0.0):  # Accept the offset parameter
    # 1. Pick a fresh profile and initialize a dedicated scraper object for this cycle
    profile = random.choice(HUMANOID_PROFILES)
    scraper = SyncScraper(ticker, profile)
    
    session_lifespan = random.randint(120, 240)
    session_expiry = datetime.now() + timedelta(minutes=session_lifespan)
    
    logger.info(f"[{ticker}] Starting session cycle with identity: {profile['env_name']} for {session_lifespan}m")
    
    with requests.Session(impersonate=profile["impersonate"]) as session:
        session.headers.clear()
        session.headers.update(profile["headers"])
        
        if not scraper.handle_cookies(session):
            return 

        # 4. Run the minute-by-minute scraping loop
        while datetime.now() < session_expiry:
            
            if not validate_market_session():
                for asset in [ticker]:
                    logger.info(f"[{ticker}] Market window closed. Returning to standby.")
                    logger.info("All records processed and queue is empty.")
                os._exit(0)
        
            now = datetime.now(UTC)
            
            # Use modulo to calculate the clean structural distance to the next minute mark
            # keeping your custom asset offset intact regardless of parsing overhead time
            seconds_passed = now.second + (now.microsecond / 1000000.0)
            wait_to_sync = (60.0 - seconds_passed + time_offset) % 60.0
            
            # Avoid a zero or near-zero sleep that causes double-clipping a minute mark
            if wait_to_sync < 0.5:
                wait_to_sync += 60.0
                
            time.sleep(wait_to_sync)
            
            # === INITIALIZE RUNTIME VARIABLES FOR THE CURRENT MINUTE ===
            start_minute_time = time.time()
            ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
            prices = []
            # ===========================================================
            
            # Sub-minute polling loop
            schedule = sorted([random.uniform(5, 55) for _ in range(4)])
            for target_sec in schedule:
                elapsed = time.time() - start_minute_time
                sleep_needed = target_sec - elapsed
                if sleep_needed > 0: 
                    time.sleep(sleep_needed)
                
                p = scraper.fetch_price(session)
                
                if p in ["BLOCK", "RATE_LIMIT"]:
                    logger.warning(f"[{ticker}] Identity compromised or rate-limited. Exiting session to rotate profile...")
                    return # Exits run(), breaking the loop and forcing a clean identity rotation
                
                if isinstance(p, float): 
                    prices.append(p)
            
            # Database Delivery Execution
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
                logger.warning(f"[{ticker}] Incomplete data sequence: {len(prices)}/4 points captured.")

        # Once session_expiry passes, code naturally drops out of the while loop
        logger.info(f"[{ticker}] Session lifespan of {session_lifespan}m reached.")
        # returning here drops out of run(), sending execution back to asset_worker_thread's infinite loop
        return
    
def asset_worker_thread(ticker):
    logger.info(f"[{ticker}] Initializing long-polling worker daemon thread stack...")
    
    # Generate a unique temporal offset signature for this specific asset thread
    # This prevents the asset from syncing perfectly on the flat 00-second mark with other assets
    thread_time_offset = random.uniform(0.5, 4.5)
    
    while True:
        is_market_session = validate_market_session()
        
        if is_market_session:
            logger.info(f"[{ticker}] Market is OPEN. Starting scraper...")
            try:
                # Pass the offset directly down to the execution loop
                run(ticker, thread_time_offset) 
            except Exception as e:
                logger.error(f"[{ticker}] Scraper tracking layer encountered an unhandled error: {e}")
                time.sleep(random.uniform(45.0, 75.0))
        else:
            now_utc = datetime.now(UTC).strftime('%H:%M')
            logger.info(f"[{ticker}] Standby ({now_utc} UTC). Market closed or outside hours. Rechecking in 60 min...")
            time.sleep(3600)
   
# --- DATABASE LOOKUP ---
def get_symbols_from_pks(pk_list):
    """Translates a list of PKs into symbols using the database view."""
    if not pk_list:
        return []
    
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        # Using the specific view and PK column you requested
        query = f"""
            SELECT financial_asset_symbol 
            FROM "dyLEARN".financial_asset_list_view 
            WHERE "financial_asset_PK" IN %s;
        """
        # Execute with a tuple for the IN clause
        cur.execute(query, (tuple(pk_list),))
        results = cur.fetchall()
        cur.close()
        conn.close()
        
        symbols = [r[0] for r in results]
        return symbols
    except Exception as e:
        logger.error(f"Error fetching symbols from DB: {e}")
        return []

# --- UPDATED INITIAL FUNCTION ---
def initialize_queries(asset_pks=None):
    logger.info("SYNC ENGINE STARTING")
    
    if not asset_pks:
        logger.error("No Asset PKs provided to initialize_queries(). Waiting for GraphQL trigger...")
        return

    selected_assets = get_symbols_from_pks(asset_pks)
    
    if not selected_assets:
        logger.error(f"Could not find any symbols for PKs: {asset_pks}")
        return

    logger.info(f"Successfully mapped PKs {asset_pks} to {selected_assets}")

    for asset in selected_assets:
        t = threading.Thread(target=asset_worker_thread, args=(asset,), name=f"Worker-{asset}")
        t.daemon = True
        t.start()
        
        # STAGGERED STARTUP OVERLAY:
        # Introduces a 4 to 9 second variable pause during initial thread generation. 
        # This keeps cookie harvesting loops decentralized.
        time.sleep(random.uniform(4.0, 9.0))
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Manual shutdown.")

def resolve_YFS(_obj, _info, financial_asset_list, environment_pk):
    """
    Handles GraphQL query: 
    YFS_Extractor(financial_asset_list: [2, 12...], environment_pk: 4)
    """
    try:
        logger.info(f"GraphQL Trigger: Env {environment_pk} requesting PKs: {financial_asset_list}")
        
        # Pass the PK list directly to the scraper
        scraper_thread = threading.Thread(
            target=initialize_queries,
            args=(financial_asset_list,), 
            name="GraphQL-Trigger"
        )
        scraper_thread.daemon = True
        scraper_thread.start()
        
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e) }
"""
try:
    # Automatically start with your specific list of PKs
    my_pks = [2, 12, 14, 15, 16, 20, 21, 22, 23, 25]
    resolve_YFS(None, None, my_pks, environment_pk=4)

except KeyboardInterrupt:
    print("\n Shutdown requested by user. Exiting...")
except Exception as e:
    print(f"Unexpected error: {e}") 
"""