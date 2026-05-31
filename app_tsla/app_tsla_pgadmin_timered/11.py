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
# Use this for overnight; the script will handle if it switches back to regular
PRICE_SELECTOR = '[data-testid="qsp-overnight-price"]' 
TICKER = "TSLA"

# --- DATABASE CONFIG ---
DB_USER = "ehab.elnahas"
DB_PASS = "test"
DB_HOST = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "dyDATA_new"
TABLE_NAME = "tsla_timered"

def create_logger(ticker):
    logs_directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    if not os.path.exists(logs_directory): os.makedirs(logs_directory)
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
        self.db_buffer = []  # <--- THE SAFETY NET
        self.conn = None
        self.cursor = None
        self.connect_to_database()

    def connect_to_database(self):
        try:
            if self.conn: self.conn.close()
            self.conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME)
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
            self.logger.info("✅ Database Connection Established.")
            return True
        except Exception as e:
            self.logger.error(f"❌ DB Connection Failed: {e}")
            return False

    def flush_buffer(self):
        """Attempts to save any records that failed previously."""
        if not self.db_buffer:
            return

        self.logger.info(f"📤 Attempting to flush {len(self.db_buffer)} pending records...")
        still_failed = []
        
        for record in self.db_buffer:
            query = f"INSERT INTO {TABLE_NAME} (symbol, price_date, open, high, low, close, volume) VALUES (%s, %s, %s, %s, %s, %s, %s)"
            try:
                self.cursor.execute(query, (record['symbol'], record['date'], record['open'], record['high'], record['low'], record['close'], record['volume']))
            except Exception:
                still_failed.append(record)
        
        self.db_buffer = still_failed
        if not self.db_buffer:
            self.logger.info("✨ Buffer cleared. All data synced to DB.")

    def save_record(self, record):
        """Logic: Save to JSON (always) -> Add to Buffer -> Flush Buffer."""
        # 1. Local JSON Backup (Never fails)
        try:
            with open(JSON_FILE, "a", encoding='utf-8') as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            self.logger.error(f"File write error: {e}")

        # 2. Add to processing buffer
        self.db_buffer.append(record)

        # 3. Try to push everything in buffer
        try:
            self.flush_buffer()
        except Exception as e:
            self.logger.error(f"⚠️ DB Flush failed (Data kept in memory): {e}")
            self.connect_to_database() # Try to heal the connection for next minute

    def get_current_val(self, driver):
        # List of possible selectors because Yahoo changes them based on market phase
        selectors = [PRICE_SELECTOR, '[data-testid="qsp-post-price"]', '[data-field="regularMarketPrice"]']
        for selector in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                val = el.text.replace(',', '').strip()
                if val: return float(val)
            except:
                continue
        return None

    def run(self):
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
        
        self.logger.info(f"🛰️ Targeting: {TARGET_URL}")
        driver.get(TARGET_URL)
        time.sleep(5)

        last_refresh_hour = -1

        try:
            while True:
                now = datetime.now(NY_TZ)
                
                # REFRESH LOGIC: Once per hour to keep the stream alive
                if now.hour != last_refresh_hour:
                    self.logger.info("♻️ Refreshing page to prevent session stale-out...")
                    driver.refresh()
                    time.sleep(8)
                    last_refresh_hour = now.hour

                # 1. CLOCK SYNC
                wait = 60 - now.second - (now.microsecond / 1000000.0)
                if wait > 0: time.sleep(wait)
                
                # 2. CAPTURE OPEN
                m_open = self.get_current_val(driver)
                if m_open is None:
                    self.logger.warning("⚠️ No price detected. Market might be in 'dead' zone.")
                    continue

                m_high, m_low, m_close = m_open, m_open, m_open
                record_date = datetime.now(NY_TZ).strftime('%Y-%m-%d %H:%M:00')

                # 3. TRACKING LOOP (Increased frequency to 0.5s for accuracy)
                start_track = time.time()
                while (time.time() - start_track) < 58.5:
                    tick = self.get_current_val(driver)
                    if tick:
                        if tick > m_high: m_high = tick
                        if tick < m_low: m_low = tick
                        m_close = tick
                    time.sleep(0.5)

                # 4. PREPARE & PERSIST
                record = {
                    "symbol": TICKER, "date": record_date,
                    "open": m_open, "high": m_high, "low": m_low, "close": m_close,
                    "volume": 0
                }
                self.save_record(record)

        except KeyboardInterrupt:
            self.logger.info("🛑 Stopped by user.")
        finally:
            if self.cursor: self.cursor.close()
            if self.conn: self.conn.close()
            driver.quit()

if __name__ == "__main__":
    DataWorker().run()


######### latest version
