import threading
import time
import random
import os
import pytz
from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler
import logging
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- CONFIGURATION ---
UTC = pytz.utc
ASSETS = ["TSLA", "AAPL", "NVDA"]

class IndependentAgent(threading.Thread):
    def __init__(self, ticker):
        super().__init__()
        self.ticker = ticker
        self.daemon = True
        self.logger = self._setup_logger()
        self.driver = None

    def _setup_logger(self):
        if not os.path.exists('logs'): os.makedirs('logs')
        logger = logging.getLogger(f"Agent_{self.ticker}")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            h = TimedRotatingFileHandler(f"logs/{self.ticker}.log", when="midnight", backupCount=7)
            h.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(h)
        return logger

    def _init_driver(self):
        """Launches a private Chrome instance with Eager loading."""
        print(f"[*] [{self.ticker}] Launching dedicated Chrome Driver...")
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1024,768")
        # Eager means it doesn't wait for all images/ads to load
        opts.page_load_strategy = 'eager' 
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            # Increased timeout to 90 seconds for heavy cloud environments
            driver.set_page_load_timeout(90) 
            return driver
        except Exception as e:
            print(f"[!] [{self.ticker}] Driver Launch Failed: {e}")
            return None

    def extract_price(self, html):
        soup = BeautifulSoup(html, 'lxml')
        for tid in ["qsp-price", "qsp-pre-price", "qsp-post-price", "qsp-overnight-price"]:
            el = soup.find(attrs={"data-testid": tid})
            if el and el.text:
                try:
                    return float(el.text.replace(',', '').strip())
                except:
                    continue
        return None

    def safe_get(self, url):
        """Attempt to load the page with retries if it times out."""
        attempts = 0
        while attempts < 3:
            try:
                self.driver.get(url)
                return True
            except TimeoutException:
                attempts += 1
                print(f"[!] [{self.ticker}] Timeout on load (Attempt {attempts}/3). Retrying...")
                time.sleep(5)
            except Exception as e:
                print(f"[!] [{self.ticker}] Error loading page: {e}")
                return False
        return False

    def run(self):
        self.driver = self._init_driver()
        if not self.driver: return

        # Try to connect. If it fails, wait 30s and try again instead of crashing.
        print(f"[*] [{self.ticker}] Connecting to Yahoo Finance...")
        if not self.safe_get(f"https://finance.yahoo.com/quote/{self.ticker}/"):
            print(f"[!] [{self.ticker}] Failed to initialize after retries. Thread exiting.")
            return

        while True:
            try:
                now = datetime.now(UTC)
                next_min = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
                wait_secs = (next_min - now).total_seconds()
                
                time.sleep(wait_secs)

                # Refresh logic with Timeout Protection
                try:
                    self.driver.refresh()
                except TimeoutException:
                    print(f"[!] [{self.ticker}] Refresh timed out. Skipping this minute.")
                    continue
                
                time.sleep(5) 
                
                samples = []
                for _ in range(10):
                    try:
                        price = self.extract_price(self.driver.page_source)
                        if price: samples.append(price)
                    except:
                        pass
                    time.sleep(random.uniform(4.0, 5.0))

                if samples:
                    m_open, m_high, m_low, m_close = samples[0], max(samples), min(samples), samples[-1]
                    log_msg = f"O:{m_open:.2f} | H:{m_high:.2f} | L:{m_low:.2f} | C:{m_close:.2f} | TS:{next_min.strftime('%H:%M:%S')}"
                    self.logger.info(log_msg)
                    print(f"[LIVE] {self.ticker}: {log_msg}", flush=True)
                else:
                    print(f"[!] [{self.ticker}] No data captured at {next_min.strftime('%H:%M')}")

            except Exception as e:
                print(f"[X] [{self.ticker}] Loop Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    print(f"[*] Initializing Multi-Driver Scraper for {len(ASSETS)} assets...")
    
    for ticker in ASSETS:
        agent = IndependentAgent(ticker)
        agent.start()
        # Still using a 60s stagger to keep CPU usage low during launch
        print(f"[*] Waiting 60s for {ticker} to stabilize...")
        time.sleep(60)

    print("[*] All agents deployed. System is now LIVE.")
    while True: time.sleep(1)