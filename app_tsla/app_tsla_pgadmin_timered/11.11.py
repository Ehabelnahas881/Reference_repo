import time, json, pytz, os, random
import psycopg2
from psycopg2.extras import execute_values
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

import undetected_chromedriver as uc 
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

# --- CONFIG ---
CHROME_VERSION = 144
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "11.jsonl"
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"
TICKER = "TSLA"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

# --- DATABASE CONFIG ---
DB_USER = "ehab.elnahas"
DB_PASS = "test"
DB_HOST = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "dyDATA_new"
TABLE_NAME = "tsla_timered"

def create_logger(ticker):
    logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    if not os.path.exists(logs_dir): os.makedirs(logs_dir)
    log_path = os.path.join(logs_dir, f"{ticker}.log")
    logger = logging.getLogger(f"{ticker}_logger")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1, backupCount=5, utc=True, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.addHandler(logging.StreamHandler())
    return logger

class DataWorker:
    def __init__(self):
        self.logger = create_logger(TICKER)
        self.db_buffer = []  
        self.conn = None
        self.connect_to_database()
        self.browser_start_time = time.time()

    def connect_to_database(self):
        try:
            if self.conn: self.conn.close()
            self.conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME)
            self.conn.autocommit = True
            self.logger.info("✅ Database Connection Established.")
            return True
        except Exception as e:
            self.logger.error(f"❌ DB Connection Failed: {e}")
            return False

    def init_driver(self):
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
        options.page_load_strategy = 'eager' 
        
        prefs = {"profile.managed_default_content_settings.images": 2, "profile.default_content_setting_values.notifications": 2}
        options.add_experimental_option("prefs", prefs)

        try:
            driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
            driver.set_page_load_timeout(30) 
            self.browser_start_time = time.time()
            return driver
        except Exception as e:
            self.logger.error(f"🔥 Driver Init Failed: {e}")
            raise

    def flush_buffer(self):
        if not self.db_buffer: return
        if self.conn is None or self.conn.closed != 0:
            if not self.connect_to_database(): return
        query = f"INSERT INTO {TABLE_NAME} (symbol, price_date, open, high, low, close, volume) VALUES %s"
        data_tuples = [(r['symbol'], r['date'], r['open'], r['high'], r['low'], r['close'], r['volume']) for r in self.db_buffer]
        try:
            with self.conn.cursor() as cur:
                execute_values(cur, query, data_tuples)
            self.logger.info(f"✨ DB SYNC: {len(self.db_buffer)} rows.")
            self.db_buffer = [] 
        except Exception as e:
            self.logger.error(f"⚠️ Sync Failed: {e}")

    def save_record(self, record):
        try:
            with open(JSON_FILE, "a", encoding='utf-8') as f:
                f.write(json.dumps(record) + "\n")
        except: pass
        self.logger.info(f"📊 {record['date']} | C: {record['close']:.2f}")
        self.db_buffer.append(record)
        self.flush_buffer()

    def get_current_val(self, driver):
        # FIXED: Added regularMarketPrice and generic qsp-price fallback
        selectors = [
            'fin-streamer[data-field="regularMarketPrice"]', 
            '[data-testid="qsp-overnight-price"]', 
            '[data-testid="qsp-pre-price"]',
            '[data-testid="qsp-post-price"]',
            '[data-testid="qsp-price"]' 
        ]
        for s in selectors:
            try:
                val = driver.find_element(By.CSS_SELECTOR, s).text.replace(',', '').strip()
                if val and val != "--" and val != "": return float(val)
            except: continue
        return None

    def run(self):
        driver = self.init_driver()
        self.logger.info(f"🛰️ Targeting: {TARGET_URL}")
        try:
            driver.get(TARGET_URL)
            driver.execute_script("window.scrollTo(0, 200);")
        except TimeoutException:
            self.logger.warning("🕒 Initial load timed out, proceeding...")
        
        time.sleep(15)
        
        try:
            while True:
                now = datetime.now(NY_TZ)
                
                # STABILITY: Cycle browser every 6 hours (only time we refresh)
                if (time.time() - self.browser_start_time) > 21600:
                    self.logger.info("🔄 6-Hour Cycle: Full Reset...")
                    driver.quit()
                    driver = self.init_driver()
                    try: 
                        driver.get(TARGET_URL)
                        driver.execute_script("window.scrollTo(0, 200);")
                    except: pass
                    time.sleep(15)

                # 1. Clock Sync
                wait = 60 - now.second - (now.microsecond / 1000000.0)
                if wait > 0: time.sleep(wait)
                
                # 2. Start Capture
                m_open = self.get_current_val(driver)
                
                # If price is missing, give it 5 seconds for JS to catch up before refreshing
                if m_open is None:
                    time.sleep(5)
                    m_open = self.get_current_val(driver)

                if m_open is None:
                    self.logger.warning("⚠️ No price detected. Performing Recovery Refresh...")
                    try: 
                        driver.refresh()
                        driver.execute_script("window.scrollTo(0, 200);")
                    except: pass
                    time.sleep(15)
                    continue

                m_high, m_low, m_close = m_open, m_open, m_open
                record_date = now.strftime('%Y-%m-%d %H:%M:00')

                # 3. Monitor Minute (High Resolution)
                start_track = time.time()
                while (time.time() - start_track) < 58.0:
                    tick = self.get_current_val(driver)
                    if tick:
                        if tick > m_high: m_high = tick
                        if tick < m_low: m_low = tick
                        m_close = tick
                    time.sleep(0.5)

                self.save_record({"symbol": TICKER, "date": record_date, "open": m_open, "high": m_high, "low": m_low, "close": m_close, "volume": 0})

        except Exception as e:
            self.logger.error(f"🔥 Unexpected Crash: {e}")
        finally:
            if self.conn: self.conn.close()
            try: driver.quit()
            except: pass

if __name__ == "__main__":
    DataWorker().run()