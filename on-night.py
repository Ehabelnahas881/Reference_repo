import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import time
import json
import gc # Garbage collection to save memory
from datetime import datetime

def run_scraper():
    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    
    driver = uc.Chrome(options=options, version_main=144)
    driver.set_page_load_timeout(30)
    
    count = 0

    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Script Started. Keeping session alive...")
        
        while True:
            try:
                # Every 50 pulls, visit the main page to refresh cookies/session
                if count % 50 == 0:
                    driver.get("https://finance.yahoo.com/quote/TSLA/")
                    time.sleep(5)
                
                api_url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d&includePrePost=true"
                driver.get(api_url)
                time.sleep(1.5)
                
                raw_text = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_text)
                
                res = data['chart']['result'][0]
                ts = res['timestamp'][-1]
                quote = res['indicators']['quote'][0]
                
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
                
                with open("QWERTY.json", "a") as f:
                    f.write(json.dumps(record) + "\n")
                
                count += 1
                if count % 10 == 0: # Print status every 10 saves
                    print(f"--- Total Records Saved: {count} | Latest: {quote['close'][-1]} ---")
                
                # Prevent memory leaks
                if count % 100 == 0:
                    gc.collect()

            except Exception as e:
                print(f"Retrying... (Market or connection blip)")
                time.sleep(10) # Wait a bit longer if there's an error
            
            time.sleep(5) 

    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_scraper()