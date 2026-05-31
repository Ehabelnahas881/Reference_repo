import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, json, random, pytz, re, os
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 144  
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "pp.jsonl"
SCRAPE_INTERVAL = 30 
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"

def get_session_info(dt):
    h = dt.hour + dt.minute/60.0
    if 4.0 <= h < 9.5: return 1, "PRE_MARKET"
    elif 9.5 <= h < 16.0: return 2, "REGULAR"
    elif 16.0 <= h < 20.0: return 3, "POST_MARKET"
    else: return 0, "OVERNIGHT"

def extract_with_logic(driver):
    """Extracts price and change, then calculates OHLC variance."""
    try:
        # 1. Capture the Live Price
        price_el = WebDriverWait(driver, 15).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-testid="qsp-post-price"], [data-testid="qsp-price"]'))
        )
        price = float(price_el.text.replace(',', ''))

        # 2. Capture the Change (EX: -0.38)
        try:
            change_el = driver.find_element(By.CSS_SELECTOR, '[data-testid="qsp-post-price-change"], [data-testid="qsp-price-change"]')
            # Remove symbols like '+', '-', '(', ')'
            change_txt = re.sub(r'[()%+]', '', change_el.text)
            change = float(change_txt)
        except:
            change = 0.0

        # 3. Calculation Logic:
        # We simulate the minute's movement using the current session change
        # Base OHLC on the price + a small random volatility (0.01% - 0.05%)
        volatility = price * random.uniform(0.0001, 0.0003)
        
        c_open = round(price - (change * 0.05), 4) # Weighted open
        c_high = round(max(price, c_open) + volatility, 4)
        c_low = round(min(price, c_open) - volatility, 4)

        return {"close": price, "open": c_open, "high": c_high, "low": c_low, "change": change}
    except Exception as e:
        print(f"⚠️ Extraction failed: {e}")
        return None

def run_worker():
    print("💎 TSLA 24H CALCULATED SCRAMBLER ACTIVE 💎")
    
    # --- STABILITY FIX: Handling the Timeout Error ---
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # Initialize driver with a longer page load timeout
    driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
    driver.set_page_load_timeout(60) 

    try:
        while True:
            try:
                driver.get(TARGET_URL)
                time.sleep(5) # Let dynamic values settle
                
                data = extract_with_logic(driver)
                if data:
                    now_ny = datetime.now(NY_TZ)
                    sid, sname = get_session_info(now_ny)
                    
                    record = {
                        "symbol": "TSLA",
                        "session_id": sid,
                        "session_name": sname,
                        "timestamp": int(now_ny.timestamp()),
                        "date": now_ny.strftime('%Y-%m-%d %H:%M:%S'),
                        "close": data['close'],
                        "open": data['open'],
                        "high": data['high'],
                        "low": data['low'],
                        "volume": 0
                    }
                    
                    with open(JSON_FILE, "a") as f:
                        f.write(json.dumps(record) + "\n")
                    
                    print(f"✅ Saved {sname}: ${data['close']} (O:{data['open']} H:{data['high']} L:{data['low']})")

            except Exception as e:
                # If the HTTP timeout occurs, we catch it here and restart the driver
                print(f"❌ Connection Error: {e}. Restarting Browser...")
                try: driver.quit()
                except: pass
                time.sleep(5)
                driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
                driver.set_page_load_timeout(60)

            time.sleep(SCRAPE_INTERVAL)

    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_worker()