import time, pytz, os, random, uuid, logging, psycopg2, requests
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

# Added Cache-Control to headers
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
        self.buffer = []
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
                self.logger.info("DB Connected")
                return
            except Exception as e:
                self.logger.error(f"DB Fail (attempt {attempt}/5): {e}")
                time.sleep(5 * attempt)

    def fetch_price(self):
        try:
            # CRITICAL: Added unique timestamp to URL to force Yahoo to bypass cache
            burst_url = f"https://finance.yahoo.com/quote/TSLA/?p=TSLA&guccounter=1&nocache={time.time()}"
            
            response = requests.get(burst_url, headers=HEADERS, cookies=COOKIES, timeout=10)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Use the ID you specifically want
            price_element = soup.find(attrs={"data-testid": "qsp-overnight-price"})

            if price_element:
                price_str = price_element.text.replace(',', '')
                val = float(price_str)
                # If you see the same price, Yahoo's HTML source hasn't updated yet
                return val
        except Exception as e:
            self.logger.warning(f"Fetch error: {e}")
        return None

    def flush_buffer(self):
        if not self.buffer: return
        try:
            query = (
                f'INSERT INTO {TABLE_NAME} ('
                '"one_min_timeseries_date", "one_min_timeseries_timestamp", '
                '"one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", '
                '"one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price", '
                '"one_min_timeseries_PK", "one_min_timeseries_UUID", '
                '"one_min_timeseries_creation_date_time", "one_min_timeseries_activity_status", '
                '"one_min_timeseries_financial_data_source_PK") VALUES %s'
            )
            now_utc = datetime.now(UTC)
            data_tuples = [
                (rec['ts'].date(), rec['ts'], rec['o'], rec['h'], rec['l'], rec['c'],
                 int(time.time()*1000) + random.randint(0,999), str(uuid.uuid4()), now_utc, 1, 1)
                for rec in self.buffer
            ]
            with self.conn.cursor() as cur:
                execute_values(cur, query, data_tuples)
            self.logger.info(f"FLUSHED | Candle {self.buffer[0]['ts'].strftime('%H:%M')} | O:{self.buffer[0]['o']} C:{self.buffer[0]['c']}")
            self.buffer = []
        except Exception as e:
            self.logger.error(f"Flush Error: {e}")

    def run(self):
        self.logger.info("Scraper Started - Strict 1-min OHLC")
        # Align to the next minute start
        next_run = (datetime.now(UTC) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        
        while True:
            now = datetime.now(UTC)
            wait_sec = (next_run - now).total_seconds()
            
            if wait_sec > 0:
                time.sleep(min(wait_sec, 1))
                continue

            # --- Start of 1-minute Candle ---
            curr_candle_ts = next_run
            next_run += timedelta(minutes=1)
            
            m_open = self.fetch_price()
            if m_open is None:
                continue

            m_high, m_low, m_close = m_open, m_open, m_open
            
            # Collect ticks for the next 55 seconds
            end_time = time.time() + 55 
            while time.time() < end_time:
                tick = self.fetch_price()
                if tick:
                    m_high = max(m_high, tick)
                    m_low = min(m_low, tick)
                    m_close = tick
                    self.logger.info(f"Tick: {tick}")
                time.sleep(3) # Slowed down slightly to prevent IP banning

            # Save and Flush
            self.buffer.append({'ts': curr_candle_ts, 'o': m_open, 'h': m_high, 'l': m_low, 'c': m_close})
            self.flush_buffer()

if __name__ == "__main__":
    DataWorker().run()