import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import json
from datetime import datetime

def scrape_and_force_append():
    options = uc.ChromeOptions()
    
    # FIX 1: Page Load Strategy 'eager' prevents the renderer timeout
    options.page_load_strategy = 'eager'
    
    # FIX 2: Disable GPU and features that cause Windows handles to hang
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    
    driver = uc.Chrome(options=options, version_main=144)
    
    # FIX 3: Shorter timeout so the script moves on quickly
    driver.set_page_load_timeout(30)

    try:
        print("Initializing session (Fast Load)...")
        # Load once to establish session
        try:
            driver.get("https://finance.yahoo.com/quote/TSLA/")
        except:
            pass # Ignore timeout during initial heavy load
            
        time.sleep(5)

        print("--- STARTING CONTINUOUS APPEND ---")
        while True:
            try:
                # includePrePost=true for after-hours data
                api_url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d&includePrePost=true"
                
                driver.get(api_url)
                time.sleep(1) 
                
                raw_text = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_text)
                
                res = data['chart']['result'][0]
                ts = res['timestamp'][-1]
                quote = res['indicators']['quote'][0]
                
                readable_time = datetime.fromtimestamp(ts).strftime('%m/%d %I:%M %p')
                
                # Formatted exactly for your file
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
                
                with open("QWERTY.json", "a") as f:
                    f.write(json.dumps(record) + "\n")
                
                # Ensure each JSON object is on its own line for easy reading
                with open("QWRTY.json", "a") as f:
                    f.write(json.dumps(record) + "\n")

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved: {readable_time} | ${quote['close'][-1]}")
                
            except Exception as e:
                # If a specific loop fails, don't crash the whole script
                print("Polling... (Syncing with market data)")
            
            time.sleep(5) 

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    scrape_and_force_append()