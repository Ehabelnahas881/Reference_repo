import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, json, pytz, os, subprocess, re
from datetime import datetime

# --- CONFIG ---
CHROME_VERSION = 144  
NY_TZ = pytz.timezone('America/New_York')
JSON_FILE = "jon.jsonl" 
SCRAPE_INTERVAL = 30 

def get_market_session(dt):
    """Calculates session_id based on NY Time."""
    h = dt.hour + dt.minute/60.0
    if 4.0 <= h < 9.5: return 1, "PRE_MARKET"
    elif 9.5 <= h < 16.0: return 2, "REGULAR"
    elif 16.0 <= h < 20.0: return 3, "POST_MARKET"
    else: return 0, "OVERNIGHT"

def kill_chrome():
    try:
        subprocess.run("taskkill /f /im chrome.exe", shell=True, capture_output=True)
        subprocess.run("taskkill /f /im chromedriver.exe", shell=True, capture_output=True)
    except: pass

def get_visual_price(driver):
    """Targets the specific 2026 'Blue Ocean' and 'After Hours' price containers."""
    try:
        # These are the priority containers for Yahoo 2026
        selectors = [
            'fin-streamer[data-field="postMarketPrice"][data-symbol="TSLA"]',
            'fin-streamer[data-field="regularMarketPrice"][data-symbol="TSLA"]',
            '.livePrice', # Common 2026 class
            'span[data-testid="qsp-price"]'
        ]
        for s in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, s)
            for el in elements:
                txt = el.text.strip().replace(',', '')
                # Specifically look for the price (ignoring the +/- change text)
                match = re.search(r"(\d{2,4}\.\d{2})", txt)
                if match:
                    val = float(match.group(1))
                    if 100 < val < 1200: # Sane range for TSLA
                        return val
        return None
    except: return None

def save_data(entries):
    data_map = {}
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'r') as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    data_map[obj['timestamp']] = obj
                except: continue
    for e in entries:
        data_map[e['timestamp']] = e
    sorted_ts = sorted(data_map.keys())
    with open(JSON_FILE, 'w') as f:
        for ts in sorted_ts[-7200:]: 
            f.write(json.dumps(data_map[ts]) + "\n")
    return len(data_map)

def run_worker():
    print("💎 RECORRECTED OVERNIGHT HYBRID SCRAPER ACTIVE 💎")
    driver = None
    loop_count = 0

    while True:
        try:
            if loop_count % 15 == 0 or driver is None:
                if driver: 
                    try: driver.quit()
                    except: pass
                kill_chrome()
                options = uc.ChromeOptions()
                options.add_argument("--headless")
                # Added 2026 stability flags
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                driver = uc.Chrome(options=options, version_main=CHROME_VERSION)

            now_ny = datetime.now(NY_TZ)
            sid, sname = get_market_session(now_ny)
            
            # Weekend Check
            if (now_ny.weekday() == 5) or (now_ny.weekday() == 6 and now_ny.hour < 20):
                print(f"🕒 {now_ny.strftime('%H:%M:%S')} | Weekend: Sleeping...")
                time.sleep(60); continue

            processed_batch = []
            
            # 1. Try API First
            now_ts = int(time.time())
            chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/TSLA?period1={now_ts-3600}&period2={now_ts}&interval=1m&includePrePost=true"
            driver.get(chart_url)
            try:
                raw_json = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "pre"))).text
                data = json.loads(raw_json)
                if data['chart']['result']:
                    res = data['chart']['result'][0]
                    ts_list = res.get('timestamp', [])
                    q = res['indicators']['quote'][0]
                    for i in range(len(ts_list)):
                        if q['close'][i]:
                            dt_o = datetime.fromtimestamp(ts_list[i], NY_TZ)
                            api_sid, api_sname = get_market_session(dt_o)
                            processed_batch.append({
                                "symbol": "TSLA", "session_id": api_sid, "session_name": api_sname,
                                "timestamp": ts_list[i], "date": dt_o.strftime('%Y-%m-%d %H:%M:%S'),
                                "close": round(float(q['close'][i]), 4),
                                "open": round(float(q['open'][i] or q['close'][i]), 4),
                                "high": round(float(q['high'][i] or q['close'][i]), 4),
                                "low": round(float(q['low'][i] or q['close'][i]), 4),
                                "volume": int(q['volume'][i] or 0)
                            })
            except: pass

            # 2. Try Visual Fallback (Crucial for Overnight 8pm-4am)
            driver.get("https://finance.yahoo.com/quote/TSLA/")
            time.sleep(2) # Allow price to render
            live_price = get_visual_price(driver)
            
            if live_price:
                # Align to the start of the current minute
                cur_min_ts = int(time.time() // 60 * 60)
                processed_batch.append({
                    "symbol": "TSLA", "session_id": sid, "session_name": sname,
                    "timestamp": cur_min_ts, "date": now_ny.strftime('%Y-%m-%d %H:%M:%S'),
                    "close": live_price, "open": live_price, "high": live_price, "low": live_price,
                    "volume": 0
                })
                print(f"🎯 Live Scrape: ${live_price} ({sname})")

            if processed_batch:
                total = save_data(processed_batch)
                print(f"✅ [{now_ny.strftime('%H:%M:%S')}] Records: {total}")
            else:
                print(f"🕒 {now_ny.strftime('%H:%M:%S')} | No trade detected (Market Quiet)")

            loop_count += 1
            time.sleep(SCRAPE_INTERVAL)

        except Exception as e:
            print(f"❌ Error: {e}")
            driver = None
            time.sleep(10)

if __name__ == "__main__":
    run_worker()