import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time, json, pytz
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 144
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "pp9.jsonl"
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"
# LOCKED SELECTOR
PRICE_SELECTOR = '[data-testid="qsp-post-price"]'

def get_current_val(driver):
    """Checks the specific span every second."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, PRICE_SELECTOR)
        val = el.text.replace(',', '').strip()
        if val: return float(val)
    except:
        return None

def run_worker():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
    
    print(f"🛰️ Targeting: {PRICE_SELECTOR}")
    driver.get(TARGET_URL)
    time.sleep(5)

    try:
        while True:
            # 1. CLOCK SYNC (Wait for :00 seconds to start the minute)
            now = datetime.now(NY_TZ)
            wait = 60 - now.second - (now.microsecond / 1000000.0)
            time.sleep(wait)
            
            # 2. CAPTURE OPEN (The very first value seen at :00)
            m_open = get_current_val(driver)
            
            # If the tag is missing (Regular Market Hours), we wait and notify
            if m_open is None:
                print(f"⚠️ {datetime.now(NY_TZ).strftime('%H:%M:%S')} | Tag {PRICE_SELECTOR} not found. (Likely Regular Market Hours)")
                time.sleep(10)
                continue

            m_high = m_open
            m_low = m_open
            m_close = m_open
            record_date = datetime.now(NY_TZ).strftime('%Y-%m-%d %H:%M:00')

            # 3. TRACKING LOOP (Second-by-second comparison)
            print(f"▶️ Monitoring {record_date}...")
            start_track = time.time()
            
            while (time.time() - start_track) < 58.5:
                tick = get_current_val(driver)
                if tick:
                    # Logic: If price breaks the current range, update High/Low
                    if tick > m_high: m_high = tick
                    if tick < m_low: m_low = tick
                    # The latest tick is the close
                    m_close = tick
                time.sleep(1) # Your 1sec by 1sec requirement

            # 4. SAVE RECORD
            record = {
                "symbol": "TSLA",
                "date": record_date,
                "open": m_open,
                "high": m_high,
                "low": m_low,
                "close": m_close,
                "volume": 0
            }

            with open(JSON_FILE, "a", buffering=1) as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
            
            print(f"💾 SAVED | O:{m_open} H:{m_high} L:{m_low} C:{m_close}")

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_worker()