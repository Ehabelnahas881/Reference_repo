import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time, json, pytz, os, random
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 144  
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "newlogic.jsonl" 
DAYS_TO_VALIDATE = 4 

# ADD YOUR SYMBOLS HERE
SYMBOLS = ["TSLA", "NVDA", "AAPL", "MSFT"]

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

def save_and_sort_jsonl(new_entries):
    existing_data = {} # Key: (symbol, timestamp) to prevent cross-asset overwriting
    cutoff_ts = int(time.time()) - (86400 * DAYS_TO_VALIDATE)
    
    # Load existing file if it exists
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'r') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    if obj['timestamp'] >= cutoff_ts:
                        # Use a unique key for the dictionary
                        key = (obj['symbol'], obj['timestamp'])
                        existing_data[key] = obj
                except: continue

    # Add new data
    for entry in new_entries:
        if entry['timestamp'] >= cutoff_ts:
            key = (entry['symbol'], entry['timestamp'])
            existing_data[key] = entry

    # Sort by timestamp, then symbol
    sorted_keys = sorted(existing_data.keys(), key=lambda x: (x[1], x[0]))
    
    with open(JSON_FILE, 'w') as f:
        for key in sorted_keys:
            f.write(json.dumps(existing_data[key]) + "\n")
    return len(existing_data)

def run_once():
    driver = None
    all_assets_data = []
    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        driver = uc.Chrome(options=options, version_main=CHROME_VERSION)
        
        now_ts = int(time.time())
        start_ts = now_ts - (86400 * DAYS_TO_VALIDATE) 

        for symbol in SYMBOLS:
            print(f"📉 Fetching data for: {symbol}")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start_ts}&period2={now_ts}&interval=1m&includePrePost=true"
            
            driver.get(url)
            time.sleep(random.uniform(2, 4)) # Human-like delay
            
            try:
                raw_data = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_data)
                result = data['chart']['result'][0]
                meta = result['meta']
                quote = result['indicators']['quote'][0]
                ts_list = result.get('timestamp', [])

                for i in range(len(ts_list)):
                    if quote['close'][i] is not None:
                        sid = get_session_id(ts_list[i], meta)
                        all_assets_data.append({
                            "symbol": symbol,
                            "session_id": sid,
                            "session_name": SESSION_NAMES[sid],
                            "timestamp": ts_list[i],
                            "date": datetime.fromtimestamp(ts_list[i], NY_TZ).strftime('%Y-%m-%d %H:%M:%S'),
                            "close": round(float(quote['close'][i]), 4),
                            "volume": int(quote['volume'][i] or 0)
                        })
            except Exception as e:
                print(f"❌ Failed to parse {symbol}: {e}")

        total = save_and_sort_jsonl(all_assets_data)
        print(f"✅ Sync Success. Total records in {JSON_FILE}: {total}")
        
    finally:
        if driver:
            try: driver.quit()
            except: pass

if __name__ == "__main__":
    run_once()