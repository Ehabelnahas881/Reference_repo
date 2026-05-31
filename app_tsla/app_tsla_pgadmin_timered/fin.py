import threading
import psycopg2
import pandas as pd
import requests
import json
import time
import pytz
import os
import re
import logging
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By

# --- CONFIG & SETTINGS (Replacing local imports for this snippet) ---
CHROME_VERSION = 144
NY_TZ = pytz.timezone('America/New_York')
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"

DB_CONFIG = {
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": "5432",
    "user": "ehab.elnahas",
    "password": "test",
    "database": "dyDATA_new",
    "sslmode": "require"
}

def create_logger(ticker):
    current_directory = os.path.dirname(os.path.abspath(__file__))
    logs_directory = os.path.join(current_directory, 'logs')
    if not os.path.exists(logs_directory):
        os.makedirs(logs_directory)
    
    log_path = os.path.join(logs_directory, f"{ticker}.log")
    logger = logging.getLogger(f"{ticker}_logger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = TimedRotatingFileHandler(log_path, when="midnight", interval=1, backupCount=5, utc=True)
        handler.suffix = "%Y-%m-%d"
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

class DataFetcher(threading.Thread):
    def __init__(self, ticker):
        threading.Thread.__init__(self)
        self.ticker = ticker
        self.logger = create_logger(ticker)
        self.conn = self.connect_to_database()
        self.conn.autocommit = True
        self.cursor = self.conn.cursor()
        
        # Internal Data Storage for OHLC calculation
        self.intraday_data_df = pd.DataFrame() 
        self.logger.info(f"🚀 Engine Initialized for {ticker}")

    def connect_to_database(self, retries=5, delay=5):
        for attempt in range(retries):
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                self.logger.info(f"✅ Connection successful on attempt {attempt + 1}")
                return conn
            except Exception as e:
                self.logger.error(f"❌ Attempt {attempt + 1} failed: {e}")
                time.sleep(delay)
        raise Exception("All database connection attempts failed.")

    def init_driver(self):
        self.logger.info("🌐 Launching Undetected Chrome...")
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
        driver.get(TARGET_URL)
        time.sleep(5)
        return driver

    def get_market_price(self, driver):
        """Checks the specific span for live price."""
        selectors = ['[data-testid="qsp-price"]', '[data-testid="qsp-post-price"]']
        for selector in selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                val = el.text.replace(',', '').strip()
                if val: return float(val)
            except: continue
        return None

    def save_one_min_to_db(self, record):
        """Saves the 1-minute candle to your specific tsla_timered table."""
        query = """
            INSERT INTO tsla_timered (symbol, price_date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (price_date) DO NOTHING;
        """
        try:
            self.cursor.execute(query, (
                record['symbol'], record['date'], record['open'],
                record['high'], record['low'], record['close'], record['volume']
            ))
        except Exception as e:
            self.logger.error(f"DB Insert Error: {e}")

    def run(self):
        driver = self.init_driver()
        
        try:
            while True:
                # 1. CLOCK SYNC
                now = datetime.now(NY_TZ)
                wait = 60 - now.second - (now.microsecond / 1000000.0)
                time.sleep(wait)

                # 2. CAPTURE START OF MINUTE (OPEN)
                record_date = datetime.now(NY_TZ).replace(second=0, microsecond=0)
                m_open = self.get_market_price(driver)
                
                if m_open is None:
                    self.logger.warning("Price tag not found. Retrying...")
                    time.sleep(5)
                    continue

                m_high = m_low = m_close = m_open
                start_track = time.time()

                # 3. SECOND-BY-SECOND TRACKING (Your 1sec requirement)
                self.logger.info(f"▶️ Monitoring {record_date.strftime('%H:%M')}...")
                while (time.time() - start_track) < 58.5:
                    tick = self.get_market_price(driver)
                    if tick:
                        if tick > m_high: m_high = tick
                        if tick < m_low: m_low = tick
                        m_close = tick
                    time.sleep(1)

                # 4. CONSOLIDATE AND SAVE
                record = {
                    "symbol": self.ticker,
                    "date": record_date,
                    "open": m_open, "high": m_high, "low": m_low, "close": m_close,
                    "volume": 0 # Volume scraping can be added similarly
                }
                
                self.save_one_min_to_db(record)
                self.logger.info(f"💾 SAVED {self.ticker} | O:{m_open} H:{m_high} L:{m_low} C:{m_close}")

        except Exception as e:
            self.logger.error(f"FATAL RUN ERROR: {e}")
        finally:
            driver.quit()
            self.conn.close()

if __name__ == "__main__":
    fetcher = DataFetcher(ticker="TSLA")
    fetcher.start()