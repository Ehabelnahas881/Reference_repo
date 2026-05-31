import undetected_chromedriver as uc
import json
import time
import csv
import os
from datetime import datetime

def save_to_csv_smart(all_records):
    file_exists = os.path.isfile('TSLA_History.csv')
    existing_timestamps = set()

    if file_exists:
        with open('TSLA_History.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_timestamps.add(row['Time'])

    new_entries = [r for r in all_records if r['Time'] not in existing_timestamps]
    
    if new_entries:
        with open('TSLA_History.csv', 'a', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['Time', 'Price'])
            if not file_exists:
                w.writeheader()
            w.writerows(new_entries)
        print(f"   Successfully added {len(new_entries)} new points.")
    else:
        print("   No new data points found in this cycle.")

def scrape_tsla_logic():
    options = uc.ChromeOptions()
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    
    # Optional: Uncomment the line below to run without a visible window
    # options.add_argument('--headless') 
    
    driver = uc.Chrome(options=options, version_main=144)
    driver.set_page_load_timeout(60)

    try:
        driver.get("https://finance.yahoo.com/quote/TSLA/")
        time.sleep(10) 
        driver.execute_script("window.scrollBy(0, 500);")
        time.sleep(5)
        
        logs = driver.get_log("performance")
        all_records = []
        
        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") == "Network.responseReceived":
                    url = msg.get("params", {}).get("response", {}).get("url", "")
                    
                    if "v8/finance/chart/TSLA" in url:
                        req_id = msg["params"]["requestId"]
                        body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                        data = json.loads(body['body'])
                        
                        chart = data['chart']['result'][0]
                        ts = chart['timestamp']
                        prices = chart['indicators']['quote'][0]['close']
                        
                        for i in range(len(ts)):
                            if prices[i] is not None:
                                # Using Date + Time to ensure uniqueness across days
                                all_records.append({
                                    'Time': datetime.fromtimestamp(ts[i]).strftime('%Y-%m-%d %H:%M'),
                                    'Price': round(prices[i], 2)
                                })
                        
                        if all_records:
                            save_to_csv_smart(all_records)
                            return True
            except:
                continue
    finally:
        try:
            driver.quit()
        except:
            pass
    return False

def run_forever(interval_seconds=300):
    print(f"*** TSLA MONITOR ACTIVE ***")
    print(f"Target: https://finance.yahoo.com/quote/TSLA/")
    print(f"Interval: {interval_seconds/60} minutes. Press Ctrl+C to exit.\n")
    
    while True:
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{now}] Fetching latest chart data...")
            
            success = scrape_tsla_logic()
            
            if success:
                print(f"[{now}] Cycle complete. Waiting {interval_seconds/60} minutes...")
            else:
                print(f"[{now}] Data not found this time. Retrying in 60s...")
                time.sleep(60)
                continue
                
        except Exception as e:
            print(f"ERROR: {e}")
            print("Recovering in 60 seconds...")
            time.sleep(60)
            continue
        
        time.sleep(interval_seconds)

if __name__ == "__main__":
    run_forever(interval_seconds=300)