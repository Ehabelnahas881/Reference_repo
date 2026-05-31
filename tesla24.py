import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import json
import gc # Garbage collection for overnight stability
from datetime import datetime

def scrape_and_force_append():
    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    
    driver = uc.Chrome(options=options, version_main=144)
    driver.set_page_load_timeout(30)
    
    count = 0 # Counter to track session health

    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing Session...")
        
        # Initial visit to set session cookies
        try:
            driver.get("https://finance.yahoo.com/quote/TSLA/")
        except:
            pass 
            
        time.sleep(5)

        print("--- STARTING OVERNIGHT CONTINUOUS APPEND ---")
        while True:
            try:
                # ADAPTIVE RECHECK: Every 100 pulls (~10 mins), 
                # refresh the main page to prevent session expiration.
                if count > 0 and count % 100 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Refreshing Session Token...")
                    driver.get("https://finance.yahoo.com/quote/TSLA/")
                    time.sleep(5)
                    gc.collect() # Clear internal memory

                # The "Secret Backdoor" URL for live data
                api_url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d&includePrePost=true"
                
                driver.get(api_url)
                time.sleep(1.2) # Small buffer for the JSON to render
                
                raw_text = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_text)
                
                res = data['chart']['result'][0]
                ts = res['timestamp'][-1]
                quote = res['indicators']['quote'][0]
                
                # Formatting date exactly as requested
                readable_time = datetime.fromtimestamp(ts).strftime('%m/%d %I:%M %p')
                
                record = {
                    str(time.time()): {
                        "data_points": [{
                            "Date": readable_time,
                            "Close": str(round(quote['close'][-1], 2)),
                            "Open": str(round(quote['open'][-1], 2)),
                            "High": str(round(quote['high'][-1], 2)),
                            "Low": str(round(quote['low'][-1], 2)),
                            "Volume": "{:,}".format(quote['volume'][-1])
                        }],
                        "ranges": []
                    }
                }
                
                # Write to both files as in your inherited code
                for filename in ["onon.json", "onon.json"]:
                    with open(filename, "a") as f:
                        f.write(json.dumps(record) + "\n")
                
                count += 1
                
                # Console feedback
                if count % 5 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Records: {count} | Market Time: {readable_time} | ${quote['close'][-1]}")
                
            except Exception as e:
                # If internet blips or Yahoo acts up, wait 10s and keep trying
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection blip. Retrying in 10s...")
                time.sleep(10)
            
            # Polling speed
            time.sleep(5) 

    except KeyboardInterrupt:
        print("\nStopping script...")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    scrape_and_force_append()