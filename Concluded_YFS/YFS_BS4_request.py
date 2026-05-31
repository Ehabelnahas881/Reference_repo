import time, pytz, os, random, uuid, logging, psycopg2, requests, threading
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from psycopg2.extras import execute_values
from logging.handlers import TimedRotatingFileHandler

# DB GLOBAL CONFIGURATION 
UTC = pytz.utc
DB_CONFIG = {
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com", 
    "user": "ehab.elnahas", 
    "password": "test", 
    "database": "dyDATA_new", 
    "port": "5432",
    "connect_timeout": 5
}
FLUSH_THRESHOLD = 5 

BASE_COOKIES = {
    "A3": "d=AQABBAE1qmkcEAf_Tt8_pPFYFEgABCAHYsWngAeANylMA9qMCAAdATWqac_pPFY&S=AQAAAhpgeBDsfqp1GQXTrpvdhiQ",
    "GUC": "AQABCAFpsdVp4ElexwRn&s=AQAAAB6Ykc6t&g=abCHZA",
    "CONSENT": "YES+cb.20240116-07-p0.en+FX+999",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

def get_market_session_config():
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    
    if 1.0 <= curr < 9.0:
        return "qsp-overnight-price", "Overnight", 1
    elif 9.0 <= curr < 14.5:
        return "qsp-post-price", "Pre-Market", 2
    elif 14.5 <= curr < 21.0:
        return "qsp-price", "Regular", 3
    else:
        return "qsp-post-price", "Post-Market", 4

class DataWorker:
    def __init__(self, ticker, table_name):
        self.ticker = ticker
        self.table_name = table_name
        self.logger = self.create_logger()
        self.session = requests.Session()
        self.session.cookies.update(BASE_COOKIES)
        self.conn = None
        self.buffer = []
        self.connect_db()

    def create_logger(self):
        if not os.path.exists('logs'): os.makedirs('logs')
        logger = logging.getLogger(f"{self.ticker}_Scraper")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = TimedRotatingFileHandler(f"logs/{self.ticker}.log", when="midnight", interval=1, backupCount=5)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
            logger.addHandler(logging.StreamHandler())
        return logger

    def connect_db(self):
        try:
            if self.conn:
                try: self.conn.close()
                except: pass
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.conn.autocommit = False 
            self.logger.info(f"Database Connected Successfully for {self.ticker}")
            return True
        except Exception as e:
            self.logger.error(f"Database Connection Failed for {self.ticker}: {e}")
            return False

    def fetch_price(self):
        target_id, s_name, _ = get_market_session_config()
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}/?p={self.ticker}&ts={time.time()}"
            resp = self.session.get(url, headers=HEADERS, timeout=7)
            
            if resp.status_code != 200:
                self.logger.warning(f"[{self.ticker}] Session blocked (HTTP {resp.status_code}). Resetting cookies...")
                self.session.cookies.update(BASE_COOKIES)
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')
            el = soup.find(attrs={"data-testid": target_id})
            
            if not el:
                for alt_id in ["qsp-price", "qsp-post-price", "qsp-overnight-price"]:
                    el = soup.find(attrs={"data-testid": alt_id})
                    if el: break
            
            if el and el.text:
                return float(el.text.replace(',', '').strip())

        except Exception as e:
            self.logger.error(f"Fetch failed for {self.ticker} ({s_name}): {e}")
        return None

    def flush_buffer(self):
        if not self.buffer: return
        try:
            if not self.conn or self.conn.closed:
                if not self.connect_db(): return

            query = f"""
                INSERT INTO {self.table_name} (
                    "one_min_timeseries_date", "one_min_timeseries_timestamp", 
                    "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", 
                    "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price", 
                    "one_min_timeseries_PK", "one_min_timeseries_UUID", 
                    "one_min_timeseries_creation_date_time", "one_min_timeseries_activity_status", 
                    "one_min_timeseries_financial_data_source_PK", "one_min_timeseries_ID"
                ) VALUES %s
            """
            
            data_to_save = []
            for rec in self.buffer:
                now_utc = datetime.now(UTC)
                pk = int(time.time()*1000) + random.randint(0,999)
                data_to_save.append((
                    rec['ts'].date(), rec['ts'], rec['o'], rec['h'], rec['l'], rec['c'], 
                    pk, str(uuid.uuid4()), now_utc, 1, 1, rec['s_id']
                ))

            with self.conn.cursor() as cur:
                execute_values(cur, query, data_to_save)
                self.conn.commit()
            
            self.logger.info(f"[{self.ticker}] BUFFER FLUSHED | {len(self.buffer)} records saved.")
            self.buffer.clear() 

        except Exception as e:
            if self.conn: self.conn.rollback()
            self.logger.error(f"[{self.ticker}] Flush Failed: {e}.")

    def run(self):
        self.logger.info(f"Scraper Online for {self.ticker}")
        next_min = (datetime.now(UTC) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        
        while True:
            wait = (next_min - datetime.now(UTC)).total_seconds()
            if wait > 0: time.sleep(wait)
            
            curr_ts = next_min
            next_min += timedelta(minutes=1)
            
            _, s_name, s_id = get_market_session_config()
            
            m_open = None
            for _ in range(3):
                m_open = self.fetch_price()
                if m_open: break
                time.sleep(1)
            
            if m_open is None:
                self.logger.error(f"[{self.ticker}] {s_name} Minute {curr_ts} lost: No Open Price.")
                continue

            m_high, m_low, m_close = m_open, m_open, m_open
            for _ in range(9):
                time.sleep(random.uniform(4.0, 6.5))
                tick = self.fetch_price()
                if tick:
                    m_high = max(m_high, tick)
                    m_low = min(m_low, tick)
                    m_close = tick

            self.buffer.append({
                'ts': curr_ts, 'o': m_open, 'h': m_high, 'l': m_low, 'c': m_close, 's_id': s_id
            })
            
            self.logger.info(f"[{self.ticker}] {s_name} Buffered: {curr_ts.strftime('%H:%M')} | Pending: {len(self.buffer)}")

            if len(self.buffer) >= FLUSH_THRESHOLD:
                self.flush_buffer()

def start_worker(ticker, table):
    try:
        worker = DataWorker(ticker, table)
        worker.run()
    except Exception as e:
        print(f"FATAL ERROR for {ticker}: {e}")

if __name__ == "__main__":
    # Define assets as much as we need : (Ticker, Table_Name)
    assets = [
        ("TSLA", '"TEST_TSLA"."one_min_timeseries_data"'),
        ("BTC-USD", '"TEST_BTC"."one_min_timeseries_data"'), 
        ("NVDA", '"TEST_NVDA"."one_min_timeseries_data"')
    ]

    threads = []
    for ticker, table in assets:
        t = threading.Thread(target=start_worker, args=(ticker, table), name=f"Thread-{ticker}")
        t.daemon = True
        threads.append(t)
        t.start()
        print(f"Started thread for {ticker}")

    # continue running until interrupted to keep scrapers alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nAll scrapers stopping...")