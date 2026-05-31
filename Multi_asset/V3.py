cat << 'EOF' > V3.py
import threading, time, random, logging, pytz, os, sys, re
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from curl_cffi import requests as cur_req 

# --- CONFIGURATION ---
UTC = pytz.utc
USER_AGENTS = ['Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0']

class DriverPool:
    def __init__(self):
        print("[SYSTEM] Booting Firefox Guard...", flush=True)
        opts = FirefoxOptions()
        opts.add_argument("--headless")
        try:
            self.driver = webdriver.Firefox(options=opts)
            print("[SYSTEM] Firefox Online.", flush=True)
        except Exception as e:
            print(f"[CRITICAL] Firefox failed: {e}", flush=True)
            sys.exit(1)
        self.lock = threading.Lock()
        self.tabs = {}

    def get_session_data(self, ticker):
        # Added a timeout to the lock to prevent permanent "stuck" state
        acquired = self.lock.acquire(timeout=30)
        if not acquired:
            print(f"[WARN] {ticker} could not acquire browser lock. Skipping sync.", flush=True)
            return None
        try:
            if ticker not in self.tabs:
                self.driver.execute_script("window.open('about:blank', '_blank');")
                self.tabs[ticker] = self.driver.window_handles[-1]
            
            self.driver.switch_to.window(self.tabs[ticker])
            print(f"[DEBUG] {ticker} refreshing Selenium session...", flush=True)
            self.driver.get(f"https://finance.yahoo.com/quote/{ticker}?guccounter=1")
            time.sleep(7) 
            return self.driver.get_cookies()
        except Exception as e:
            print(f"[ERROR] Selenium error for {ticker}: {e}", flush=True)
            return None
        finally:
            self.lock.release()

global_pool = None

def get_market_session_config():
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    if 8.0 <= curr < 13.5: return ["qsp-pre-price", "qsp-post-price", "qsp-price"], "Pre-Market"
    elif 13.5 <= curr < 20.0: return ["qsp-price"], "Regular"
    elif 20.0 <= curr <= 24.0: return ["qsp-post-price", "qsp-price"], "Post-Market"
    else: return ["qsp-overnight-price", "qsp-post-price", "qsp-price"], "Overnight"

class DataWorker:
    def __init__(self, ticker):
        self.ticker = ticker
        self.cookies = {}
        self.logger = self.create_logger()
        
    def create_logger(self):
        if not os.path.exists('logs'): os.makedirs('logs')
        logger = logging.getLogger(f"{self.ticker}_Scraper")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            h = TimedRotatingFileHandler(f"logs/{self.ticker}.log", when="midnight", interval=1, backupCount=7)
            h.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(h)
        return logger

    def sync_session(self):
        try:
            raw_cookies = global_pool.get_session_data(self.ticker)
            if raw_cookies:
                self.cookies = {c['name']: c['value'] for c in raw_cookies}
                return True
            return False
        except: return False

    def fetch_price(self):
        target_ids, _ = get_market_session_config()
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}/?p={self.ticker}&guccounter=1&ts={time.time()}"
            resp = cur_req.get(url, cookies=self.cookies, impersonate="chrome110", timeout=10)
            if resp.status_code != 200: return None
            
            # Using html.parser to avoid dependency issues with lxml
            soup = BeautifulSoup(resp.text, 'html.parser')
            for tid in target_ids:
                el = soup.find(attrs={"data-testid": tid})
                if el and el.text:
                    try: return float(el.text.replace(',', '').strip())
                    except: continue
            
            match = re.search(r'"regularMarketPrice":\{"raw":([\d\.]+)', resp.text)
            if match: return float(match.group(1))
            return None
        except: return None

    def run(self):
        print(f"[SYSTEM] Worker for {self.ticker} starting...", flush=True)
        self.sync_session()
        
        # Start immediately
        next_run = datetime.now(UTC)
        
        while True:
            try:
                # Calculate sleep until the start of the next minute
                now = datetime.now(UTC)
                if now < next_run:
                    time.sleep((next_run - now).total_seconds())
                
                curr_ts = next_run
                next_run = (curr_ts + timedelta(minutes=1)).replace(second=0, microsecond=0)
                
                _, s_name = get_market_session_config()
                m_open = self.fetch_price()
                
                if m_open is None:
                    print(f"[WARN] {self.ticker} fetch failed. Syncing...", flush=True)
                    self.sync_session()
                    continue
                
                m_high, m_low, m_close = m_open, m_open, m_open
                
                # Sampling 6 times per minute
                for _ in range(6):
                    time.sleep(random.uniform(7.0, 9.0))
                    tick = self.fetch_price()
                    if tick:
                        m_high, m_low, m_close = max(m_high, tick), min(m_low, tick), tick

                log_msg = f"[{s_name}] O:{m_open:.2f} | H:{m_high:.2f} | L:{m_low:.2f} | C:{m_close:.2f} | TS:{curr_ts.strftime('%H:%M:%S')}"
                self.logger.info(log_msg)
                print(f"[LIVE] {self.ticker}: {log_msg}", flush=True)

                if datetime.now(UTC).minute % 15 == 0: self.sync_session()
            except Exception as e:
                print(f"[CRITICAL] {self.ticker} loop error: {e}", flush=True)
                time.sleep(5)

# --- API ---
type_defs = """
    type Query { status: String }
    type Mutation { resolve_IDE(financial_asset_list: [Int]): IDEResponse }
    type IDEResponse { success: Boolean }
"""

def resolve_IDE(obj, info, financial_asset_list=[1,2,3]):
    mapping = {1: "TSLA", 2: "AAPL", 3: "NVDA"}
    def _start():
        global global_pool
        if not global_pool: global_pool = DriverPool()
        for aid in financial_asset_list:
            ticker = mapping.get(aid)
            if ticker:
                threading.Thread(target=DataWorker(ticker).run, daemon=True).start()
                # Stagger by 15s to allow Firefox to handle the first request fully
                time.sleep(15) 
    threading.Thread(target=_start, daemon=True).start()
    return {"success": True}

query = ObjectType("Query")
@query.field("status")
def resolve_status(*_): return "Online"
mutation = ObjectType("Mutation")
mutation.set_field("resolve_IDE", resolve_IDE)

schema = make_executable_schema(type_defs, [query, mutation])
app = Flask(__name__)

@app.route("/graphql", methods=["POST"])
def g():
    _, res = graphql_sync(schema, request.get_json(), context_value=request)
    return jsonify(res), 200

if __name__ == "__main__":
    def auto():
        time.sleep(5)
        try: cur_req.post("http://127.0.0.1:3989/graphql", json={"query": "mutation { resolve_IDE(financial_asset_list: [1, 2, 3]) { success } }"})
        except: pass
    threading.Thread(target=auto, daemon=True).start()
    app.run(host="0.0.0.0", port=3989)
EOF