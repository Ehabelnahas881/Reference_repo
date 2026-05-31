import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, json, random, pytz, os, re
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 144  
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "mutation.jsonl" 
SCRAPE_INTERVAL = 30 

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

SESSION_NAMES = {1: "PRE_MARKET", 2: "REGULAR", 3: "POST_MARKET", 0: "OVERNIGHT"}

class SafeChrome(uc.Chrome):
    def __del__(self):
        try: self.quit()
        except: pass

def get_session_id(ts, meta):
    try:
        tps = meta.get('tradingPeriods', {})
        mapping = {"pre": 1, "regular": 2, "post": 3}
        for s_type, periods_list in tps.items():
            sid = mapping.get(s_type)
            if not sid: continue
            for day_list in periods_list:
                for period in day_list:
                    if period['start'] <= ts < period['end']:
                        return sid
        return 0
    except: return 0

def save_and_impute_data(new_entries):
    data_map = {} 
    cutoff_ts = int(time.time()) - 432000 
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'r') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj['timestamp'] >= cutoff_ts:
                        data_map[obj['timestamp']] = obj
                except: continue

    for entry in new_entries:
        if entry['timestamp'] >= cutoff_ts:
            # Prioritize existing detailed data, but always allow overnight updates
            if entry['timestamp'] not in data_map or entry['session_id'] == 0:
                data_map[entry['timestamp']] = entry
    
    sorted_ts = sorted(data_map.keys())
    with open(JSON_FILE, 'w') as f:
        for ts in sorted_ts:
            f.write(json.dumps(data_map[ts]) + "\n")
    return len(sorted_ts)

def scrape_overnight_ui(driver):
    """Refined for 2026 Yahoo Finance UI using specific data-testids."""
    try:
        driver.get("https://finance.yahoo.com/quote/TSLA/")
        
        # Selectors based on your provided Outer HTML and 2026 structure
        # Order: Post-Market, Pre-Market, Regular Price
        selectors = [

            'span[data-testid="qsp-price"]'
            'span[data-testid="qsp-post-price"]',
            'span[data-testid="qsp-pre-price"]',
            'span[data-testid="qsp-overnight-price"]',
            'fin-streamer[data-field="postMarketPrice"]',
            'fin-streamer[data-field="regularMarketPrice"]'
        ]
        
        found_price = None
        for selector in selectors:
            try:
                # Short wait per selector to iterate quickly
                element = WebDriverWait(driver, 5).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                raw_text = element.text.strip().replace(',', '') # Handle thousands separators
                
                if raw_text:
                    # Extracts the first decimal number found (e.g., 409.00)
                    match = re.search(r"(\d{1,5}\.\d{2})", raw_text)
                    if match:
                        found_price = round(float(match.group(1)), 4)
                        print(f"🎯 DEBUG: Found Price via {selector}: {found_price}")
                        break
            except:
                continue
        
        return found_price
    except Exception as e:
        print(f"⚠️ UI Scrape Error: {e}")
        return None

def run_worker():
    driver = None
    first_run = True 
    print("💎 HARDENED HYBRID RECORDER ACTIVE 💎")

    while True:
        now_ny = datetime.now(NY_TZ)
        hour = now_ny.hour
        is_overnight_time = (hour >= 20 or hour < 4)

        # Weekend Check
        if now_ny.weekday() >= 5 and not is_overnight_time and not first_run:
            print(f"🛑 Weekend: Sleeping... ({now_ny.strftime('%H:%M:%S')})")
            time.sleep(60); continue

        try:
            options = uc.ChromeOptions()
            options.add_argument("--headless")
            ua = random.choice(USER_AGENTS)
            options.add_argument(f"--user-agent={ua}")
            options.add_argument("--window-size=1920,1080") 
            
            driver = SafeChrome(options=options, version_main=CHROME_VERSION)
            driver.set_page_load_timeout(30)
            
            processed_batch = []

            # A. API SYNC (Historical)
            try:
                now_ts = int(time.time())
                api_url = f"https://query1.finance.yahoo.com/v8/finance/chart/TSLA?period1={now_ts-432000}&period2={now_ts}&interval=1m&includePrePost=true"
                driver.get(api_url)
                # Ensure the text is loaded in the <pre> tag
                json_element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "pre")))
                data = json.loads(json_element.text)
                res = data['chart']['result'][0]
                ts_list = res.get('timestamp', [])
                quote = res['indicators']['quote'][0]
                for i in range(len(ts_list)):
                    if quote['close'][i] is not None:
                        ts = ts_list[i]
                        sid = get_session_id(ts, res['meta'])
                        processed_batch.append({
                            "symbol": "TSLA", "session_id": sid, "session_name": SESSION_NAMES[sid],
                            "timestamp": ts, "date": datetime.fromtimestamp(ts, NY_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                            "close": round(float(quote['close'][i]), 4), 
                            "open": round(float(quote['open'][i] or quote['close'][i]), 4),
                            "high": round(float(quote['high'][i] or quote['close'][i]), 4), 
                            "low": round(float(quote['low'][i] or quote['close'][i]), 4),
                            "volume": int(quote['volume'][i] or 0)
                        })
            except Exception as e:
                print(f"📡 API Sync Skip: {e}")

            # B. LIVE OVERNIGHT SCRAPE
            if is_overnight_time:
                print(f"🌙 Overnight Mode: Checking TSLA UI...")
                ui_price = scrape_overnight_ui(driver)
                if ui_price:
                    # Align to the start of the current minute
                    cur_ts = int(time.time() // 60 * 60)
                    processed_batch.append({
                        "symbol": "TSLA", "session_id": 0, "session_name": "OVERNIGHT",
                        "timestamp": cur_ts, "date": datetime.fromtimestamp(cur_ts, NY_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                        "close": ui_price, "open": ui_price, "high": ui_price, "low": ui_price, "volume": 0
                    })
                else:
                    print("❌ UI Scrape failed to find a price.")

            if processed_batch:
                total = save_and_impute_data(processed_batch)
                print(f"✅ [{now_ny.strftime('%H:%M:%S')}] Total Records in File: {total}")
            
            first_run = False
            driver.quit()
        except Exception as e:
            print(f"❌ Worker Error: {e}")
            if driver: driver.quit()
            time.sleep(10)

        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    run_worker()