import threading, time, random, uuid, logging, requests, pytz, os, sys, json, re
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService

# --- CONFIGURATION ---
UTC = pytz.utc
BASE_DIR = os.getcwd()
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
    'Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0'
]

# --- SELENIUM GUARD (Firefox Version) ---
class DriverPool:
    def __init__(self):
        print("[SYSTEM] Booting Selenium Firefox Guard...", flush=True)
        opts = FirefoxOptions()
        opts.add_argument("--headless")  # Firefox uses --headless
        
        # Optimization for Linux Pods/Nohup
        opts.set_preference("permissions.default.image", 2) # Don't load images
        opts.set_preference("dom.ipc.plugins.enabled.libflashplayer.so", "false")
        
        try:
            # Selenium Manager handles geckodriver automatically in most modern setups
            self.driver = webdriver.Firefox(options=opts)
            print("[SYSTEM] Firefox Driver Online.", flush=True)
        except Exception as e:
            print(f"[CRITICAL] Firefox Driver failed: {e}", flush=True)
            sys.exit(1)
            
        self.lock = threading.Lock()
        self.tabs = {}

    def get_session_data(self, ticker):
        with self.lock:
            if ticker not in self.tabs:
                # Firefox syntax for opening new tabs
                self.driver.execute_script("window.open('about:blank', '_blank');")
                self.tabs[ticker] = self.driver.window_handles[-1]
            
            self.driver.switch_to.window(self.tabs[ticker])
            self.driver.get(f"https://finance.yahoo.com/quote/{ticker}?guccounter=1")
            time.sleep(8) 
            
            # Consent bypass logic
            try:
                for btn in self.driver.find_elements("tag name", "button"):
                    if any(x in btn.text.lower() for x in ["akzeptieren", "agree", "accept"]):
                        btn.click()
                        time.sleep(3)
                        break
            except: pass
            return self.driver.get_cookies()

global_pool = None

# --- MARKET SESSION LOGIC ---
def get_market_session_config():
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    if 8.0 <= curr < 13.5: return ["qsp-pre-price", "qsp-post-price", "qsp-price"], "Pre-Market"
    elif 13.5 <= curr < 20.0: return ["qsp-price"], "Regular"
    elif 20.0 <= curr <= 24.0: return ["qsp-post-price", "qsp-price"], "Post-Market"
    else: return ["qsp-overnight-price", "qsp-post-price", "qsp-price"], "Overnight"

# --- DATA WORKER ---
class DataWorker:
    def __init__(self, ticker):
        self.ticker = ticker
        self.session = requests.Session()
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
            cookies = global_pool.get_session_data(self.ticker)
            self.session.cookies.clear()
            for c in cookies:
                self.session.cookies.set(c['name'], c['value'], domain=c.get('domain'))
            self.session.headers.update({
                'User-Agent': random.choice(USER_AGENTS),
                'Referer': 'https://finance.yahoo.com/',
                'Cache-Control': 'no-cache'
            })
            return True
        except: return False

    def fetch_price(self):
        target_ids, _ = get_market_session_config()
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}/?p={self.ticker}&guccounter=1&_ts={time.time()}"
            resp = self.session.get(url, timeout=12, allow_redirects=True)
            if resp.status_code != 200: return None
            
            soup = BeautifulSoup(resp.text, 'lxml')
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
        print(f"[SYSTEM] Worker for {self.ticker} Online (Firefox).", flush=True)
        self.sync_session()
        next_min = (datetime.now(UTC) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        
        while True:
            try:
                wait = (next_min - datetime.now(UTC)).total_seconds()
                if wait > 0: time.sleep(wait)
                
                curr_ts = next_min
                next_min = next_min + timedelta(minutes=1)
                
                _, s_name = get_market_session_config()
                m_open = self.fetch_price()
                
                if m_open is None:
                    print(f"[WARN] {self.ticker} Fetch Failed. Resyncing...", flush=True)
                    self.sync_session()
                    continue
                
                m_high, m_low, m_close = m_open, m_open, m_open
                
                # High-frequency sampling (5 ticks)
                for _ in range(5):
                    time.sleep(random.uniform(8.0, 10.0))
                    tick = self.fetch_price()
                    if tick:
                        m_high, m_low, m_close = max(m_high, tick), min(m_low, tick), tick

                log_msg = f"[{s_name}] O:{m_open:.2f} | H:{m_high:.2f} | L:{m_low:.2f} | C:{m_close:.2f} | TS:{curr_ts.strftime('%H:%M:%S')}"
                self.logger.info(log_msg)
                print(f"[LIVE] {self.ticker}: {log_msg}", flush=True)

                if curr_ts.minute % 20 == 0: self.sync_session()
            except Exception:
                time.sleep(5)

# --- API LAYER ---
type_defs = """
    type Query { status: String }
    type Mutation { resolve_IDE(financial_asset_list: [Int]): IDEResponse }
    type IDEResponse { success: Boolean }
"""

def resolve_IDE(obj, info, financial_asset_list=[1,2,3]):
    mapping = {1: "TSLA", 2: "AAPL", 3: "NVDA", 4: "^GSPC", 5: "BTC-USD"}
    def _start():
        global global_pool
        if not global_pool: global_pool = DriverPool()
        for aid in financial_asset_list:
            ticker = mapping.get(aid)
            if ticker:
                # Still using the Thread target logic as requested
                threading.Thread(target=DataWorker(ticker).run, daemon=True).start()
                time.sleep(10) 
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
        try: requests.post("http://127.0.0.1:3989/graphql", json={"query": "mutation { resolve_IDE(financial_asset_list: [1, 2, 3]) { success } }"})
        except: pass
    threading.Thread(target=auto, daemon=True).start()
    app.run(host="0.0.0.0", port=3989)