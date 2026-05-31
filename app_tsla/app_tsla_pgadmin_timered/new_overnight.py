import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, json, random, pytz, os, re
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 146
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "jon.jsonl" 
SCRAPE_INTERVAL = 30 

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

SESSION_NAMES = {1: "PRE_MARKET", 2: "REGULAR", 3: "POST_MARKET", 0: "OVERNIGHT"}

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
            if entry['timestamp'] not in data_map or entry['session_id'] == 0:
                data_map[entry['timestamp']] = entry
    
    sorted_ts = sorted(data_map.keys())
    with open(JSON_FILE, 'w') as f:
        for ts in sorted_ts:
            f.write(json.dumps(data_map[ts]) + "\n")
    return len(sorted_ts)

def scrape_overnight_ui(driver):
    try:
        # Use a direct refresh or get to ensure fresh data
        driver.get("https://finance.yahoo.com/quote/TSLA/")
        
        selectors = [

            'span[data-testid="qsp-price"]'
            'span[data-testid="qsp-post-price"]',
            'span[data-testid="qsp-pre-price"]',
            'span[data-testid="qsp-overnight-price"]',
            'fin-streamer[data-field="postMarketPrice"]',
            'fin-streamer[data-field="regularMarketPrice"]'
        ]
        
        found_price = None
        # Shortened timeout to prevent the "renderer" hang
        wait = WebDriverWait(driver, 10)
        
        for selector in selectors:
            try:
                element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                raw_text = element.text.strip()
                if raw_text:
                    match = re.search(r"(\d{1,4}\.\d{2})", raw_text)
                    if match:
                        found_price = round(float(match.group(1)), 4)
                        print(f"🎯 DEBUG: Found Price via {selector}: {found_price}")
                        break
            except:
                continue
        return found_price
    except Exception as e:
        print(f"⚠️ UI Scrape Error: {str(e).splitlines()[0]}") # Shortened error log
        return None

def init_driver():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    # This prevents the renderer from hanging on useless scripts
    options.page_load_strategy = 'eager' 
    
    driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
    driver.set_page_load_timeout(25)
    return driver

def run_worker():
    print("💎 HARDENED HYBRID RECORDER ACTIVE 💎")
    driver = init_driver()
    
    while True:
        try:
            now_ny = datetime.now(NY_TZ)
            hour = now_ny.hour
            is_overnight_time = (hour >= 20 or hour < 4)

            if now_ny.weekday() >= 5 and not is_overnight_time:
                print(f"🛑 Weekend: Sleeping... ({now_ny.strftime('%H:%M:%S')})")
                time.sleep(60); continue

            processed_batch = []

            # A. API SYNC
            try:
                now_ts = int(time.time())
                api_url = f"https://query1.finance.yahoo.com/v8/finance/chart/TSLA?period1={now_ts-432000}&period2={now_ts}&interval=1m&includePrePost=true"
                driver.get(api_url)
                api_text = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(api_text)
                res = data['chart']['result'][0]
                ts_list = res.get('timestamp', [])
                quote = res['indicators']['quote'][0]
                for i in range(len(ts_list)):
                    if quote['close'][i]:
                        ts = ts_list[i]
                        sid = get_session_id(ts, res['meta'])
                        processed_batch.append({
                            "symbol": "TSLA", "session_id": sid, "session_name": SESSION_NAMES[sid],
                            "timestamp": ts, "date": datetime.fromtimestamp(ts, NY_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                            "close": round(float(quote['close'][i]), 4), "open": round(float(quote['open'][i]), 4),
                            "high": round(float(quote['high'][i]), 4), "low": round(float(quote['low'][i]), 4),
                            "volume": int(quote['volume'][i] or 0)
                        })
            except Exception as e:
                print(f"⚠️ API Sync Skip: {e}")

            # B. LIVE OVERNIGHT SCRAPE
            if is_overnight_time:
                print(f"🌙 Overnight Mode: Checking TSLA UI...")
                ui_price = scrape_overnight_ui(driver)
                if ui_price:
                    cur_ts = int(time.time() // 60 * 60)
                    processed_batch.append({
                        "symbol": "TSLA", "session_id": 0, "session_name": "OVERNIGHT",
                        "timestamp": cur_ts, "date": datetime.fromtimestamp(cur_ts, NY_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                        "close": ui_price, "open": ui_price, "high": ui_price, "low": ui_price, "volume": 0
                    })
                else:
                    print("❌ UI Scrape failed to find a price.")

            total = save_and_impute_data(processed_batch)
            print(f"✅ [{now_ny.strftime('%H:%M:%S')}] Total Records: {total}")

        except Exception as e:
            print(f"❌ Worker Error: {e}")
            # If the driver crashes or times out completely, restart it
            try: driver.quit()
            except: pass
            time.sleep(5)
            driver = init_driver()

        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    run_worker()