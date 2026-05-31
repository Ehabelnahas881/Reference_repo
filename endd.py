import threading, time, random, uuid, logging, requests, pytz, os, sys, json, re, psycopg2
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# --- CONFIGURATION ---
UTC = pytz.utc
DB_CONFIG = {
    "dbname": "dyDATA_new",
    "user": "ehab.elnahas",
    "password": "test", 
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": "5432"
}
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
]

# --- SELENIUM GUARD ---
class DriverPool:
    def __init__(self):
        print("[SYSTEM] Booting Selenium Guard...", flush=True)
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        try:
            self.driver = webdriver.Chrome(options=opts)
            print("[SYSTEM] Selenium Driver Online.", flush=True)
        except Exception as e:
            print(f"[CRITICAL] Driver failed: {e}", flush=True)
            sys.exit(1)
        self.lock = threading.Lock()
        self.tabs = {}

    def get_session_data(self, ticker):
        with self.lock:
            if ticker not in self.tabs:
                self.driver.execute_script("window.open('about:blank', '_blank');")
                self.tabs[ticker] = self.driver.window_handles[-1]
            self.driver.switch_to.window(self.tabs[ticker])
            self.driver.get(f"https://finance.yahoo.com/quote/{ticker}?guccounter=1")
            time.sleep(8)
            try:
                for btn in self.driver.find_elements("tag name", "button"):
                    if any(x in btn.text.lower() for x in ["akzeptieren", "agree", "accept"]):
                        btn.click(); time.sleep(3); break
            except: pass
            return self.driver.get_cookies()

global_pool = None

# --- DATABASE DISCOVERY ---
def fetch_asset_metadata(pk_list):
    assets = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute('SET search_path TO "dyLEARN", public;')
        query = f"""
            SELECT financial_asset_symbol, financial_asset_postgresql_schema_name, "financial_asset_PK" 
            FROM "dyLEARN".financial_asset_list 
            WHERE "financial_asset_PK" = ANY(%s)
        """
        cur.execute(query, (pk_list,))
        for row in cur.fetchall():
            assets.append({"ticker": row[0], "schema": row[1], "pk": row[2]})
        cur.close(); conn.close()
    except Exception as e:
        print(f"[DB ERROR] Metadata fetch failed: {e}", flush=True)
    return assets

# --- DATA WORKER (Thread Inheritance) ---
class DataWorker(threading.Thread):
    def __init__(self, asset_info):
        super().__init__(daemon=True)
        self.ticker = asset_info['ticker']
        self.schema = asset_info['schema']
        self.pk = asset_info['pk']
        self.session = requests.Session()
        self.logger = self.create_logger()

    def create_logger(self):
        if not os.path.exists('logs'): os.makedirs('logs')
        logger = logging.getLogger(f"{self.ticker}_Scraper")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            h = TimedRotatingFileHandler(f"logs/{self.ticker}.log", when="midnight", backupCount=7)
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
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}/?p={self.ticker}&guccounter=1&_ts={time.time()}"
            resp = self.session.get(url, timeout=12)
            if resp.status_code != 200: return None
            soup = BeautifulSoup(resp.text, 'lxml')
            for tid in ["qsp-price", "qsp-pre-price", "qsp-post-price"]:
                el = soup.find(attrs={"data-testid": tid})
                if el and el.text: return float(el.text.replace(',', '').strip())
            match = re.search(r'"regularMarketPrice":\{"raw":([\d\.]+)', resp.text)
            return float(match.group(1)) if match else None
        except: return None

    def save_to_db(self, o, h, l, c, ts):
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            query = f'INSERT INTO "{self.schema}".one_min_timeseries_data (one_min_timeseries_timestamp, open_price, high_price, low_price, close_price, financial_asset_fk) VALUES (%s, %s, %s, %s, %s, %s)'
            cur.execute(query, (ts, o, h, l, c, self.pk))
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            print(f"[DB SAVE ERROR] {self.ticker}: {e}", flush=True)

    def run(self):
        print(f"[LIVE] Thread started for {self.ticker}", flush=True)
        self.sync_session()
        
        while True:
            try:
                # 1. Precise minute alignment
                now = datetime.now(UTC)
                next_min = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                wait_time = (next_min - now).total_seconds()
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # 2. Burst sampling for 50 seconds
                ticks = []
                sample_end = datetime.now(UTC) + timedelta(seconds=50)
                
                while datetime.now(UTC) < sample_end:
                    price = self.fetch_price()
                    if price:
                        ticks.append(price)
                    time.sleep(random.uniform(4.0, 6.0)) # Sample every ~5 seconds
                
                # 3. Process OHLC if data exists
                if ticks:
                    m_open, m_high, m_low, m_close = ticks[0], max(ticks), min(ticks), ticks[-1]
                    msg = f"O:{m_open:.2f} | H:{m_high:.2f} | L:{m_low:.2f} | C:{m_close:.2f} ({len(ticks)} samples)"
                    self.logger.info(msg)
                    print(f"[DATA] {self.ticker}: {msg}", flush=True)
                    self.save_to_db(m_open, m_high, m_low, m_close, next_min)
                else:
                    # If no ticks found, the session might be stale
                    self.sync_session()

            except Exception as e:
                print(f"[LOOP ERROR] {self.ticker}: {e}")
                time.sleep(5)

# --- API ---
type_defs = "type Query { status: String } type Mutation { resolve_IDE(pk_list: [Int]): Boolean }"
mutation = ObjectType("Mutation")

@mutation.field("resolve_IDE")
def resolve_IDE(_, info, pk_list=[14, 15, 20]):
    def _start_workers_background(financial_asset_symbol, environment_pk):
        global global_pool
        if not global_pool: global_pool = DriverPool()
        active_assets = fetch_asset_metadata(financial_asset_symbol)
        for asset in active_assets:
            worker = DataWorker(asset)
            worker.start()
            time.sleep(10)
    
    threading.Thread(target=_start_workers_background, args=(pk_list, "PROD"), daemon=True).start()
    return True

schema = make_executable_schema(type_defs, [mutation])
app = Flask(__name__)

@app.route("/graphql", methods=["POST"])
def g():
    _, res = graphql_sync(schema, request.get_json())
    return jsonify(res), 200

if __name__ == "__main__":
    def auto():
        time.sleep(5)
        print("[AUTO] Triggering dyDATA_new data extraction...", flush=True)
        try: 
            requests.post("http://127.0.0.1:3989/graphql", 
                         json={"query": "mutation { resolve_IDE(pk_list: [14, 15, 20]) }"})
        except Exception as e:
            print(f"[AUTO FAIL] {e}")
            
    threading.Thread(target=auto, daemon=True).start()
    app.run(host="0.0.0.0", port=3989)