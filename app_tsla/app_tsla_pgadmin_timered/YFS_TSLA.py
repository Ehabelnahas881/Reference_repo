import time, json, pytz, os, random
import psycopg2
from psycopg2.extras import execute_values
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

import undetected_chromedriver as uc 
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException

######## CONFIG ##############
CHROME_VERSION = 145
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "11.jsonl"
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"
TICKER = "TSLA"

# Expanded User Agents for better rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
]

######### DATABASE CONFIG #########
DB_USER = "ehab.elnahas"
DB_PASS = "test"
DB_HOST = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "dyDATA_new"
TABLE_NAME = '"TEST_TSLA"."one_min_timeseries_data"' 

########### Logger Setup ############
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
        options.add_argument("--headless=new") 
        options.add_argument(f'--user-agent={random.choice(USER_AGENTS)}')
        options.add_argument('--no-sandbox') 
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        
        # Anti-Detection Flags
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        options.binary_location = "/usr/bin/chromium"

        try:
            driver = uc.Chrome(
                options=options, 
                version_main=CHROME_VERSION,
                browser_executable_path="/usr/bin/chromium",
                driver_executable_path="/usr/bin/chromedriver"
            )
            driver.set_page_load_timeout(60) 
            self.browser_start_time = time.time()
            return driver
        except Exception as e:
            self.logger.error(f"❌ Driver Init Failed: {e}")
            raise

    def flush_buffer(self):
        if not self.db_buffer: return
        if self.conn is None or self.conn.closed != 0:
            if not self.connect_to_database(): return

        query = f"""
            INSERT INTO {TABLE_NAME} (
                "one_min_timeseries_date",
                "one_min_timeseries_timestamp",
                "one_min_timeseries_OP_open_price",
                "one_min_timeseries_HP_high_price",
                "one_min_timeseries_LP_low_price",
                "one_min_timeseries_CP_close_price",
                "one_min_timeseries_PK",
                "one_min_timeseries_creation_date_time",
                "one_min_timeseries_last_modification_date_time"
            ) VALUES %s
        """
        
        now = datetime.now(NY_TZ)
        data_tuples = []
        for r in self.db_buffer:
            manual_pk = int(time.time() * 1000) + random.randint(0, 999)
            data_tuples.append((
                now.date(), r['date'], r['open'], r['high'], r['low'], r['close'],
                manual_pk, now, now
            ))

        try:
            with self.conn.cursor() as cur:
                execute_values(cur, query, data_tuples)
            self.logger.info(f"💾 DB SYNC: {len(self.db_buffer)} rows saved.")
            self.db_buffer = [] 
        except Exception as e:
            self.logger.error(f"❌ Sync Failed: {e}")

    def save_record(self, record):
        try:
            with open(JSON_FILE, "a", encoding='utf-8') as f:
                f.write(json.dumps(record) + "\n")
        except: pass
        self.logger.info(f"📈 {record['date']} | C: {record['close']:.2f}")
        self.db_buffer.append(record)
        self.flush_buffer()

    def Scraper(self, driver):
        # Your original selectors
        selectors = [
            'fin-streamer[data-field="regularMarketPrice"]', 
            '[data-testid="qsp-overnight-price"]', 
            '[data-testid="qsp-pre-price"]',
            '[data-testid="qsp-post-price"]',
            '[data-testid="qsp-price"]' 
        ]
        for s in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, s)
                val = el.text.replace(',', '').strip()
                if val and "." in val: return float(val)
            except: continue
        return None

    def run(self):
        driver = self.init_driver()
        self.logger.info(f"🚀 Targeting: {TARGET_URL}")
        
        try:
            driver.get(TARGET_URL)
            time.sleep(15) 
            
            # Check for block immediately
            if "Too Many Requests" in driver.page_source:
                self.logger.error("🛑 IP is still blocked (429). Sleeping 10 mins before first retry...")
                time.sleep(600)
                driver.get(TARGET_URL)

            try:
                btns = driver.find_elements(By.XPATH, "//button[contains(., 'Accept') or contains(., 'Agree')]")
                if btns:
                    btns[0].click()
                    self.logger.info("🍪 Cookie consent bypassed.")
                    time.sleep(5)
            except: pass

        except TimeoutException:
            self.logger.warning("⚠️ Initial load timed out, proceeding...")
        
        try:
            while True:
                now = datetime.now(NY_TZ)
                
                # 6-Hour Reset
                if (time.time() - self.browser_start_time) > 21600:
                    self.logger.info("🔄 6-Hour Cycle: Resetting driver...")
                    driver.quit()
                    driver = self.init_driver()
                    driver.get(TARGET_URL)
                    time.sleep(15)

                # Timing logic
                wait = 60 - now.second - (now.microsecond / 1000000.0)
                if wait > 0: 
                    self.logger.info(f"😴 Sleeping {round(wait,1)}s until next minute starts...")
                    time.sleep(wait)
                
                # Price extraction with retry
                m_open = None
                for _ in range(3):
                    m_open = self.Scraper(driver)
                    if m_open is not None: break
                    time.sleep(2)

                if m_open is None:
                    # BLOCK DETECTION LOGIC
                    if "Too Many Requests" in driver.page_source:
                        self.logger.warning("🛑 429 Blocked! Backing off for 2 minutes...")
                        time.sleep(120)
                    else:
                        self.logger.warning("❓ No price found! Refreshing...")
                    
                    driver.refresh()
                    time.sleep(20)
                    continue

                # OHLC calculation logic (Your original logic)
                m_high, m_low, m_close = m_open, m_open, m_open
                record_date = datetime.now(NY_TZ).strftime('%Y-%m-%d %H:%M:00')

                start_track = time.time()
                while (time.time() - start_track) < 58.0:
                    tick = self.Scraper(driver)
                    if tick:
                        if tick > m_high: m_high = tick
                        if tick < m_low: m_low = tick
                        m_close = tick
                    time.sleep(random.uniform(0.5, 1.0))

                self.save_record({"date": record_date, "open": m_open, "high": m_high, "low": m_low, "close": m_close})

        except KeyboardInterrupt:
            self.logger.info("🛑 Stopped by user.")
        except WebDriverException as e:
            self.logger.error(f"💥 Browser Crashed: {e}")
        finally:
            if self.conn: self.conn.close()
            try:
                driver.quit()
            except: pass

if __name__ == "__main__":
    DataWorker().run()