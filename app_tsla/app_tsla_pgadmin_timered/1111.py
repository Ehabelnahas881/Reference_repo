import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time, json, pytz, os
import psycopg2
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 144
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "pp9.jsonl"
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"
PRICE_SELECTOR = '[data-testid="qsp-overnight-price"]'
TICKER = "TSLA"

# --- DATABASE CONFIG ---
DB_USER = "ehab.elnahas"
DB_PASS = "test"
DB_HOST = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "dyDATA_new"
TABLE_NAME = "tsla_timered"

# --- 1. LOGGER SETUP ---
def create_logger(ticker):
    logs_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    if not os.path.exists(logs_directory):
        os.makedirs(logs_directory)
    
    log_path = os.path.join(logs_directory, f"{ticker}.log")
    logger = logging.getLogger(f"{ticker}_logger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1, backupCount=5, utc=True, encoding='utf-8')
        handler.suffix = "%Y-%m-%d"
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addHandler(console_handler)
    return logger

class DataWorker:
    def __init__(self):
        self.logger = create_logger(TICKER)
        self.conn = self.connect_to_database()
        self.cursor = self.conn.cursor()
        self.conn.autocommit = True
        self.logger.info(f"--- Session Started for {TICKER} ---")

    def connect_to_database(self, retries=5, delay=5):
        for attempt in range(retries):
            try:
                conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME)
                self.logger.info("✅ Database Connection Established.")
                return conn
            except Exception as e:
                self.logger.error(f"❌ Attempt {attempt + 1} failed: {e}")
                time.sleep(delay)
        raise Exception("CRITICAL: DB connection failed.")

    # --- UPDATED SAVE FUNCTION ---
    def save_to_db(self, record):
        """Matches your specific PGAdmin column names exactly."""
        query = f"""
            INSERT INTO {TABLE_NAME} (symbol, price_date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        try:
            self.cursor.execute(query, (
                record['symbol'], 
                record['date'], 
                record['open'],
                record['high'], 
                record['low'], 
                record['close'], 
                record['volume']
            ))
            self.logger.info(f"💾 DB SAVED | {record['date']} | C: {record['close']}")
        except Exception as e:
            self.logger.error(f"❌ DB SAVE ERROR: {e}")
            # If the error is a connection loss, try to reset the cursor
            try:
                self.conn = self.connect_to_database()
                self.cursor = self.conn.cursor()
            except:
                pass

    def get_current_val(self, driver):
        try:
            el = driver.find_element(By.CSS_SELECTOR, PRICE_SELECTOR)
            val = el.text.replace(',', '').strip()
            if val: return float(val)
        except:
            return None

    def run(self):
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
        
        self.logger.info(f"🛰️ Targeting: {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(5)

        try:
            while True:
                # 1. CLOCK SYNC
                now = datetime.now(NY_TZ)
                wait = 60 - now.second - (now.microsecond / 1000000.0)
                if wait > 0: time.sleep(wait)
                
                # 2. CAPTURE MINUTE OPEN
                m_open = self.get_current_val(driver)
                if m_open is None:
                    self.logger.warning("⚠️ Selector not found. Retrying in 10s...")
                    time.sleep(10)
                    continue

                m_high, m_low, m_close = m_open, m_open, m_open
                record_date = datetime.now(NY_TZ).strftime('%Y-%m-%d %H:%M:00')

                # 3. TRACKING LOOP
                self.logger.info(f"▶️ Monitoring Minute: {record_date}")
                start_track = time.time()
                while (time.time() - start_track) < 58.5:
                    tick = self.get_current_val(driver)
                    if tick:
                        if tick > m_high: m_high = tick
                        if tick < m_low: m_low = tick
                        m_close = tick
                    time.sleep(1)

                # 4. PREPARE & SAVE
                record = {
                    "symbol": TICKER,
                    "date": record_date,
                    "open": m_open,
                    "high": m_high,
                    "low": m_low,
                    "close": m_close,
                    "volume": 0
                }

                # Local Backup
                with open(JSON_FILE, "a", encoding='utf-8') as f:
                    f.write(json.dumps(record) + "\n")
                
                # DB Push
                self.save_to_db(record)

        except KeyboardInterrupt:
            self.logger.info("🛑 Stopped by user.")
        finally:
            if self.cursor: self.cursor.close()
            if self.conn: self.conn.close()
            driver.quit()

if __name__ == "__main__":
    worker = DataWorker()
    worker.run()