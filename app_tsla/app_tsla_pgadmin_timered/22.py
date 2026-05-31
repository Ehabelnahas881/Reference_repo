################################## All market sessions including the overnight ##################
                        ####################################################

import time
import threading
import logging
import psycopg2
import pytz
from datetime import datetime
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================================
# CONFIG
# ==========================================================

DB_CONFIG = {
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": "5432",
    "user": "ehab.elnahas",
    "password": "test",
    "database": "dyDATA_new",
    "sslmode": "require"
}

# Selector to catch standard price if post-market isn't available
PRICE_SELECTOR = '[data-testid="qsp-post-price"], [data-testid="qsp-price"]'
CHROME_VERSION = 144 

# ==========================================================
# LOGGER
# ==========================================================

def create_logger():
    logger = logging.getLogger("Scraper")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

# ==========================================================
# DATA FETCHER CLASS
# ==========================================================

class DataFetcher:

    def __init__(self, ticker):
        self.ticker = ticker
        self.logger = create_logger()
        self.conn = None
        self.cursor = None
        self.driver = None

        # Force bypass of DB validation
        self.todayIsMarketDay = True 

        try:
            self.connect_database()
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
        
        self.logger.info("Bypassing Market Validation. Starting auto-scrape...")

        self.init_scraper()
        self.start()

    def connect_database(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.conn.autocommit = True
        self.cursor = self.conn.cursor()
        self.logger.info("Connected to PostgreSQL.")

    # Bypassed DB Methods
    def validate_market_day(self): pass
    def initialize_queries(self): pass

    def get_current_session(self):
        return "ACTIVE_AUTO"

    def init_scraper(self):
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")

        self.driver = uc.Chrome(
            options=options,
            version_main=CHROME_VERSION,
            use_subprocess=True
        )

        url = f"https://finance.yahoo.com/quote/{self.ticker}/"
        self.driver.get(url)
        self.logger.info(f"Navigating to {url}")
        
        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, PRICE_SELECTOR))
        )
        self.logger.info("Scraper initialized.")

    def get_current_price(self):
        """Fetch current price from the DOM."""
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, PRICE_SELECTOR)
            val = el.text.replace(",", "").strip()
            return float(val)
        except:
            return None

    def fetch_minute(self):
        """Your specific High-Frequency calculation logic."""
        
        # 1. Sync to start of next minute
        now = datetime.now(pytz.UTC)
        wait = 60 - now.second - (now.microsecond / 1_000_000)
        time.sleep(wait)

        # 2. Refresh and grab Open
        self.driver.refresh()
        time.sleep(2)
        
        m_open = self.get_current_price()
        if m_open is None:
            self.logger.warning("No price detected at open. Skipping minute.")
            return

        # Initialize OHLC with Open value
        m_high = m_open
        m_low = m_open
        m_close = m_open
        
        # Format date for logging/saving (UTC)
        record_date = datetime.now(pytz.UTC).replace(second=0, microsecond=0)

        # 3. TRACKING LOOP (Exact 1sec-by-1sec requirement)
        self.logger.info(f"▶️ Monitoring {record_date}...")
        start_track = time.time()
        
        while (time.time() - start_track) < 58.5:
            tick = self.get_current_price()
            if tick:
                # Update High/Low if price breaks current range
                if tick > m_high: m_high = tick
                if tick < m_low: m_low = tick
                # Latest tick is always the close
                m_close = tick
            time.sleep(1) 

        # 4. Final Save
        try:
            query = """
                INSERT INTO tsla_timered (symbol, price_date, open, high, low, close) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.cursor.execute(query, (self.ticker, record_date, m_open, m_high, m_low, m_close))
            self.logger.info(f"💾 Saved {record_date} | O:{m_open} H:{m_high} L:{m_low} C:{m_close}")
        except Exception as e:
            self.logger.error(f"Save failed: {e}")

    def start(self):
        def loop():
            while True:
                try:
                    self.fetch_minute()
                except Exception as e:
                    self.logger.error(f"Loop error: {e}")
                    time.sleep(5)

        thread = threading.Thread(target=loop)
        thread.daemon = True
        thread.start()

if __name__ == "__main__":
    DataFetcher("TSLA")
    while True:
        time.sleep(1)