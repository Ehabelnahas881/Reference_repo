################################## All market sessions including the overnight ##################
                        ####################################################

import time
import threading
import logging
import pandas as pd
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

PRICE_SELECTOR = '[data-testid="qsp-post-price"]'
CHROME_VERSION = 144  # Chrome version for undetected_chromedriver


# ==========================================================
# LOGGER
# ==========================================================

def create_logger():
    """Creates and configures logger for the scraper"""
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
        """Initialize the DataFetcher, connect DB, check market day, and start scraper."""
        self.ticker = ticker
        self.logger = create_logger()

        self.conn = None
        self.cursor = None
        self.driver = None

        self.todayIsMarketDay = False

        # Connect DB
        try:
            self.connect_database()
        except Exception as e:
            self.logger.error(f"Database connection failed: {e}")
            return

        # Validate market day
        try:
            self.validate_market_day()
        except Exception as e:
            self.logger.error(f"Market validation failed: {e}")
            self.todayIsMarketDay = False

        if not self.todayIsMarketDay:
            self.logger.info("Today is NOT a trading day. Scraper will not start.")
            return

        # Initialize session timestamps from DB
        self.initialize_queries()

        # Initialize Selenium scraper
        self.init_scraper()

        # Start the scraping loop
        self.start()

    # ======================================================
    # DATABASE CONNECTION
    # ======================================================

    def connect_database(self):
        """Connect to PostgreSQL DB."""
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.conn.autocommit = True
        self.cursor = self.conn.cursor()
        self.logger.info("Connected to PostgreSQL.")

    # ======================================================
    # MARKET VALIDATION
    # ======================================================

    def validate_market_day(self):
        """Check if today is a market working day using DB info."""
        financial_market_pk_query = f'''
            SELECT "financial_asset_market_PK", financial_market_code
            FROM "dyLEARN".financial_asset_list_view
            WHERE financial_asset_symbol = '{self.ticker}' ;
        '''
        self.cursor.execute(financial_market_pk_query)
        self.financial_market_pk, self.financial_market_code = self.cursor.fetchone()

        last_trading_date_query = f'''
            SELECT MAX("period_date_UTC"::date)
            FROM "dyLEARN".market_session_periods_list_view
            WHERE "financial_market_PK" = {self.financial_market_pk}
        '''
        self.cursor.execute(last_trading_date_query)
        last_trading_date = self.cursor.fetchone()[0]

        if last_trading_date == datetime.now(pytz.UTC).date():
            self.todayIsMarketDay = True
        else:
            self.todayIsMarketDay = False

        self.logger.info(f"Today Market Day? {self.todayIsMarketDay}")

    # ======================================================
    # INITIALIZE MARKET SESSIONS
    # ======================================================

    def initialize_queries(self):
        """Initialize all session timestamps (pre, regular, post, overnight) from DB."""
        self.logger.info("Initializing session timestamps...")

        # Get last 2 trading dates
        self.cursor.execute(f'''
            SELECT DISTINCT "market_session_period_date_UTC"
            FROM "dyLEARN".market_session_periods_list
            WHERE "market_session_period_financial_market_PK" = {self.financial_market_pk}
            ORDER BY "market_session_period_date_UTC" DESC LIMIT 2;
        ''')
        last_2_trading_dates = self.cursor.fetchall()
        self.todays_market_date = last_2_trading_dates[0][0]

        # Pre Market
        self.cursor.execute(f'''
            SELECT "period_start_time_UTC","period_end_time_UTC"
            FROM "dyLEARN".market_session_periods_list_view
            WHERE period_type_name = 'Session'
            AND "market_session_PK" = 1
            AND "period_start_time_UTC"::date = '{self.todays_market_date}'
            AND "financial_market_PK" = {self.financial_market_pk}
        ''')
        self.pre_market_start_timestamp, self.pre_market_close_timestamp = self.cursor.fetchone()

        # Regular Market
        self.cursor.execute(f'''
            SELECT "period_start_time_UTC","period_end_time_UTC"
            FROM "dyLEARN".market_session_periods_list_view
            WHERE period_type_name = 'Session'
            AND "market_session_PK" = 2
            AND "period_start_time_UTC"::date = '{self.todays_market_date}'
            AND "financial_market_PK" = {self.financial_market_pk}
        ''')
        self.open_market_start_timestamp, self.open_market_close_timestamp = self.cursor.fetchone()

        # Post Market
        self.cursor.execute(f'''
            SELECT "period_start_time_UTC","period_end_time_UTC"
            FROM "dyLEARN".market_session_periods_list_view
            WHERE period_type_name = 'Session'
            AND "market_session_PK" = 3
            AND "period_start_time_UTC"::date = '{self.todays_market_date}'
            AND "financial_market_PK" = {self.financial_market_pk}
        ''')
        self.after_hours_start_timestamp, self.after_hours_close_timestamp = self.cursor.fetchone()

        # Overnight session (from previous day's post-market to pre-market)
        self.overnight_start_timestamp = self.after_hours_close_timestamp
        self.overnight_close_timestamp = self.pre_market_start_timestamp

    # ======================================================
    # CURRENT SESSION DETECTION
    # ======================================================

    def get_current_session(self):
        """Return the current session based on DB timestamps, only overnight active."""
        now = datetime.now(pytz.UTC)

        if not self.todayIsMarketDay:
            return "CLOSED_DAY"

        # Only run overnight
        if self.overnight_start_timestamp <= now < self.overnight_close_timestamp:
            return "OVERNIGHT"

        return "CLOSED_SESSION"

    # ======================================================
    # SCRAPER INITIALIZATION
    # ======================================================

    def init_scraper(self):
        """Start Selenium WebDriver and wait for price element."""
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

        WebDriverWait(self.driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, PRICE_SELECTOR))
        )

        self.logger.info("Scraper initialized.")

    # ======================================================
    # GET CURRENT PRICE
    # ======================================================

    def get_current_price(self):
        """Fetch the current price from the page element."""
        try:
            el = self.driver.find_element(By.CSS_SELECTOR, PRICE_SELECTOR)
            val = el.text.replace(",", "").strip()
            return float(val)
        except:
            return None

    # ======================================================
    # FETCH MINUTE DATA
    # ======================================================

    def fetch_minute(self):
        """Fetch price for the current minute and calculate OHLC."""
        session = self.get_current_session()

        if session in ["CLOSED_DAY", "CLOSED_SESSION"]:
            self.logger.info(f"Market closed ({session}). Skipping.")
            time.sleep(60)
            return

        self.logger.info(f"Active Session: {session}")

        # Wait until the start of the next minute
        now = datetime.now(pytz.UTC)
        wait = 60 - now.second - (now.microsecond / 1_000_000)
        time.sleep(wait)

        minute_timestamp = datetime.now(pytz.UTC).replace(second=0, microsecond=0)

        # Initial price
        open_price = self.get_current_price()
        if open_price is None:
            return

        high_price = open_price
        low_price = open_price
        close_price = open_price

        # Collect prices for the full minute
        start = time.time()
        while (time.time() - start) < 58:
            price = self.get_current_price()
            if price:
                high_price = max(high_price, price)
                low_price = min(low_price, price)
                close_price = price
            time.sleep(1)

        self.logger.info(f"{session} | O:{open_price} H:{high_price} L:{low_price} C:{close_price}")

        # TODO: Save minute OHLC to your ASSET schema

    # ======================================================
    # START LOOP
    # ======================================================

    def start(self):
        """Start the scraping loop in a separate thread."""
        def loop():
            while True:
                try:
                    self.fetch_minute()
                except Exception as e:
                    self.logger.error(e)
                    time.sleep(5)

        thread = threading.Thread(target=loop)
        thread.daemon = True
        thread.start()


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":
    DataFetcher("TSLA")

    while True:
        time.sleep(1)