import time, pytz, os, random, uuid, logging, psycopg2, requests, re, json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from psycopg2.extras import execute_values
from logging.handlers import TimedRotatingFileHandler

UTC = pytz.utc
TICKER = "TSLA"
DB_CONFIG = {"host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com", "user": "ehab.elnahas", "password": "test", "database": "dyDATA_new", "port": "5432"}
TABLE_NAME = '"TEST_TSLA"."one_min_timeseries_data"'

COOKIES = {
    "A3": "d=AQABBAE1qmkcEAf_Tt8_pPFYFEgABCAHYsWngAeANylMA9qMCAAdATWqac_pPFY&S=AQAAAhpgeBDsfqp1GQXTrpvdhiQ",
    "GUC": "AQABCAFpsdVp4ElexwRn&s=AQAAAB6Ykc6t&g=abCHZA",
    "CONSENT": "YES+cb.20240116-07-p0.en+FX+999",
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

def create_logger():
    if not os.path.exists('logs'): os.makedirs('logs')
    logger = logging.getLogger("TSLA_Scraper")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = TimedRotatingFileHandler(f"logs/{TICKER}.log", when="midnight", interval=1, backupCount=5)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        logger.addHandler(handler)
        logger.addHandler(logging.StreamHandler())
    return logger

class DataWorker:
    def __init__(self):
        self.logger = create_logger()
        self.conn = None
        self.connect_db()

    def connect_db(self):
        for attempt in range(1, 6):
            try:
                if self.conn:
                    try: self.conn.close()
                    except: pass
                self.conn = psycopg2.connect(**DB_CONFIG)
                self.conn.autocommit = True
                self.logger.info("Database Connected")
                return
            except Exception as e:
                self.logger.error(f"DB Fail: {e}")
                time.sleep(5)

    def fetch_price(self):
        """Fetches price with cache-busting to ensure maximum accuracy."""
        try:
            # Adding random timestamp to URL to force fresh data from Yahoo
            url = f"https://finance.yahoo.com/quote/{TICKER}/?p={TICKER}&guccounter=1&nocache={time.time()}"
            resp = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=10)
            if resp.status_code != 200: return None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Targeted element for overnight/after-hours market
            el = soup.find(attrs={"data-testid": "qsp-overnight-price"}) or \
                 soup.find(attrs={"data-testid": "qsp-post-price"})
            
            if el:
                return float(el.text.replace(',', ''))
        except: pass
        return None

    def save_to_db(self, rec):
        try:
            if not self.conn or self.conn.closed: self.connect_db()
            query = f'INSERT INTO {TABLE_NAME} ("one_min_timeseries_date", "one_min_timeseries_timestamp", "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price", "one_min_timeseries_PK", "one_min_timeseries_UUID", "one_min_timeseries_creation_date_time", "one_min_timeseries_activity_status", "one_min_timeseries_financial_data_source_PK") VALUES %s'
            now_utc = datetime.now(UTC)
            data = [(rec['ts'].date(), rec['ts'], rec['o'], rec['h'], rec['l'], rec['c'], int(time.time()*1000) + random.randint(0,999), str(uuid.uuid4()), now_utc, 1, 1)]
            with self.conn.cursor() as cur:
                execute_values(cur, query, data)
            self.logger.info(f"CANDLE SAVED | {rec['ts'].strftime('%H:%M')} | O:{rec['o']} H:{rec['h']} L:{rec['l']} C:{rec['c']}")
        except Exception as e:
            self.logger.error(f"Save Error: {e}")

    def run(self):
        self.logger.info("Scraper Started - Strict 1-min OHLC")
        next_run = (datetime.now(UTC) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        
        while True:
            # Sync to start of the minute
            wait = (next_run - datetime.now(UTC)).total_seconds()
            if wait > 0:
                time.sleep(wait)
            
            curr_ts = next_run
            next_run += timedelta(minutes=1)
            
            # 1. Fetch OPEN (first fetch of the minute)
            m_open = self.fetch_price()
            if m_open is None: continue
            
            m_high, m_low, m_close = m_open, m_open, m_open
            
            # 2. Sample every 10 seconds to get H/L/C
            # We sample 5 more times (at 10s, 20s, 30s, 40s, 50s)
            for _ in range(5):
                time.sleep(10)
                tick = self.fetch_price()
                if tick:
                    m_high = max(m_high, tick)
                    m_low = min(m_low, tick)
                    m_close = tick # Last successful tick becomes the Close
            
            # 3. Save the full record to DB
            self.save_to_db({'ts': curr_ts, 'o': m_open, 'h': m_high, 'l': m_low, 'c': m_close})

if __name__ == "__main__":
    DataWorker().run()