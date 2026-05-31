cat << 'EOF' > omni_engine.py
import threading
import time
import random
import uuid
import logging
import requests
import pytz
import os
import sys
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

# Selenium Imports
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
UTC = pytz.utc
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
]

class DriverPool:
    def __init__(self):
        print("[SYSTEM] Initializing Selenium Browser...", flush=True)
        options = Options()
        options.add_argument("--headless") 
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"user-agent={random.choice(USER_AGENTS)}")
        
        # This will automatically download the correct ChromeDriver
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.tabs = {} 
        self.lock = threading.Lock()
        print("[SYSTEM] Browser Ready.", flush=True)

    def get_cookies(self, ticker):
        with self.lock:
            print(f"[SELENIUM] Opening tab for {ticker}...", flush=True)
            if ticker not in self.tabs:
                self.driver.execute_script("window.open('about:blank', '_blank');")
                self.tabs[ticker] = self.driver.window_handles[-1]
            
            self.driver.switch_to.window(self.tabs[ticker])
            self.driver.get(f"https://finance.yahoo.com/quote/{ticker}")
            time.sleep(5) 
            return self.driver.get_cookies()

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
        self.logger = self.create_logger()
        self.session = requests.Session()
        
    def create_logger(self):
        if not os.path.exists('logs'): os.makedirs('logs')
        logger = logging.getLogger(f"{self.ticker}_Scraper")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = TimedRotatingFileHandler(f"logs/{self.ticker}.log", when="midnight", interval=1, backupCount=7)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
        return logger

    def sync_session(self):
        print(f"[{self.ticker}] Syncing Selenium cookies to Request Session...", flush=True)
        try:
            cookies = global_pool.get_cookies(self.ticker)
            for cookie in cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])
            print(f"[{self.ticker}] Sync Successful.", flush=True)
        except Exception as e:
            print(f"[{self.ticker}] Sync Failed: {e}", flush=True)

    def fetch_price(self):
        target_ids, _ = get_market_session_config()
        try:
            headers = {'User-Agent': random.choice(USER_AGENTS)}
            url = f"https://finance.yahoo.com/quote/{self.ticker}/"
            resp = self.session.get(url, headers=headers, timeout=10)
            if resp.status_code != 200: return None
            
            soup = BeautifulSoup(resp.text, 'lxml')
            for tid in target_ids:
                el = soup.find(attrs={"data-testid": tid})
                if el and el.text:
                    return float(el.text.replace(',', '').strip())
            return None
        except:
            return None

    def run(self):
        print(f"[WORKER] Starting thread for {self.ticker}...", flush=True)
        self.sync_session()
        
        next_min = (datetime.now(UTC) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        
        while True:
            try:
                wait = (next_min - datetime.now(UTC)).total_seconds()
                if wait > 0: time.sleep(wait)
                curr_ts, next_min = next_min, next_min + timedelta(minutes=1)
                
                m_open = self.fetch_price()
                if m_open is None:
                    print(f"[RETRY] {self.ticker} fetch failed, retrying...", flush=True)
                    continue
                
                m_high, m_low, m_close = m_open, m_open, m_open
                for _ in range(5):
                    time.sleep(random.uniform(5, 8))
                    tick = self.fetch_price()
                    if tick: m_high, m_low, m_close = max(m_high, tick), min(m_low, tick), tick

                log_msg = f"O:{m_open:.2f} | H:{m_high:.2f} | L:{m_low:.2f} | C:{m_close:.2f} | TS:{curr_ts.strftime('%H:%M:%S')}"
                print(f"[LIVE] {self.ticker}: {log_msg}", flush=True)
                self.logger.info(log_msg)
            except Exception as e:
                print(f"[ERROR] {self.ticker}: {e}", flush=True)
                time.sleep(5)

# --- GRAPHQL ---
type_defs = """
    type Query { status: String }
    type Mutation { resolve_IDE(financial_asset_list: [Int]): IDEResponse }
    type IDEResponse { success: Boolean }
"""

def resolve_IDE(obj, info, financial_asset_list=[1,2,3]):
    mapping = {1: "TSLA", 2: "AAPL", 3: "NVDA"}
    def _start():
        global global_pool
        if global_pool is None: global_pool = DriverPool()
        
        for aid in financial_asset_list:
            ticker = mapping.get(aid)
            if ticker:
                worker = DataWorker(ticker)
                t = threading.Thread(target=worker.run, daemon=True)
                t.start()
                time.sleep(5) 
    
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
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request)
    return jsonify(result), 200

def trigger_on_start():
    """Automatically starts the workers so you don't have to send a manual request."""
    time.sleep(3)
    print("[SYSTEM] Auto-triggering workers...", flush=True)
    try:
        requests.post("http://127.0.0.1:3989/graphql", 
                     json={"query": "mutation { resolve_IDE(financial_asset_list: [1, 2, 3]) { success } }"}, 
                     timeout=10)
    except Exception as e:
        print(f"[SYSTEM] Auto-trigger failed: {e}", flush=True)

if __name__ == "__main__":
    # Start the auto-trigger in the background
    threading.Thread(target=trigger_on_start, daemon=True).start()
    print("[SYSTEM] Starting Flask Server on port 3989...", flush=True)
    app.run(host="0.0.0.0", port=3989, debug=False, threaded=True)
EOF

pkill -9 python3
nohup python3 assets10_db.py > assets10_db.log 2>&1 &
tail -f assets10_db.log