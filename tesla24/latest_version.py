import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import time
import json
import gc 
import random # Feature 1: Random Jitter
from datetime import datetime

# Feature 2: User-Agent Pool for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

def scrape_and_force_append():
    options = uc.ChromeOptions()
    options.page_load_strategy = 'eager'
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    
    # --- Feature 2: Identity Rotation ---
    random_ua = random.choice(USER_AGENTS)
    options.add_argument(f"--user-agent={random_ua}")
    
    # --- Feature 3: Proxy Support ---
    # To use a proxy, uncomment the line below and add your proxy details
    # options.add_argument('--proxy-server=http://your_proxy_ip:port')
    
    driver = uc.Chrome(options=options, version_main=144)
    driver.set_page_load_timeout(30)
    
    count = 0 

    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing Stealth Session...")
        
        try:
            driver.get("https://finance.yahoo.com/quote/TSLA/")
        except:
            pass 
            
        time.sleep(5)

        print("--- STARTING CONTINUOUS APPEND WITH STEALTH ---")
        while True:
            try:
                if count > 0 and count % 100 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Refreshing Session Token...")
                    driver.get("https://finance.yahoo.com/quote/TSLA/")
                    time.sleep(5)
                    gc.collect() 

                api_url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d&includePrePost=true"
                
                driver.get(api_url)
                
                # --- Feature 1: Internal Jitter ---
                # Adds a tiny, random human-like pause (0.1s to 0.8s) before reading data
                time.sleep(random.uniform(0.1, 0.8)) 
                
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
                            "Open": str(round(quote['open!'][-1], 2) if 'open' in quote else "N/A"),
                            "High": str(round(quote['high'][-1], 2)),
                            "Low": str(round(quote['low'][-1], 2)),
                            "Volume": "{:,}".format(quote['volume'][-1])
                        }],
                        "ranges": []
                    }
                }
                
                # FIXED: Only writing to the file ONCE per loop to avoid duplicates
                with open("qaz.json", "a") as f:
                    f.write(json.dumps(record) + "\n")
                
                count += 1
                
                if count % 5 == 0:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Records: {count} | Market: {readable_time}")
                
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Connection blip. Retrying...")
                time.sleep(10)
            
            # --- Feature 1: Main Loop Jitter ---
            # Instead of exactly 5s, we wait between 4.5s and 6.5s 
            # This maintains your "rate" but breaks the robotic pattern.
            time.sleep(random.uniform(4.5, 6.5)) 

    except KeyboardInterrupt:
        print("\nStopping script...")
    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    scrape_and_force_append()