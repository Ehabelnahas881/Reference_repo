import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import psycopg2 
import time, json, random, pytz
from datetime import datetime

# --- AWS RDS DATABASE CONFIG ---
DB_CONFIG = {
    "dbname": "dyDATA_new",
    "user": "ehab.elnahas",
    "password": "test",
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": "5432",
    "sslmode": "require"
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

def get_market_status():
    ny_tz = pytz.timezone('US/Eastern')
    now = datetime.now(ny_tz)
    if now.weekday() >= 5: return "CLOSED"
    if now.hour >= 20 or now.hour < 4: return "QUIET"
    return "ACTIVE"

def run_worker():
    driver = None
    conn = None

    print("🚀 Turbo Stealth Scraper active. Monitoring TSLA...")

    try:
        while True:
            status = get_market_status()
            
            if status == "CLOSED":
                print(f"🛑 Weekend: Market closed. Sleeping for 1 hour...")
                if driver: 
                    driver.quit()
                    driver = None
                time.sleep(3600)
                continue

            # Feature: Jitter logic
            if status == "QUIET":
                wait_time = 1800 + random.uniform(-60, 60)
            else:
                wait_time = random.uniform(55, 65)

            try:
                if not driver:
                    options = uc.ChromeOptions()
                    options.add_argument("--headless")
                    
                    # --- ORIGINAL STEALTH & PERFORMANCE FLAGS ---
                    options.add_argument("--no-sandbox")
                    options.add_argument("--disable-dev-shm-usage")
                    options.add_argument("--disable-gpu")
                    options.add_argument("--incognito")
                    options.add_argument("--ignore-certificate-errors")
                    options.add_argument("--disable-notifications")
                    options.add_argument("--disable-extensions")
                    options.page_load_strategy = 'eager'
                    
                    # Block Images and CSS for speed
                    prefs = {
                        "profile.managed_default_content_settings.images": 2,
                        "profile.managed_default_content_settings.stylesheets": 2
                    }
                    options.add_experimental_option("prefs", prefs)
                    options.add_experimental_option("excludeSwitches", ["enable-automation"])
                    
                    # Feature: Identity Rotation
                    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
                    
                    driver = uc.Chrome(options=options)
                
                if not conn or conn.closed:
                    conn = psycopg2.connect(**DB_CONFIG)
                    cursor = conn.cursor()

                url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d"
                driver.get(url)
                
                # Small wait to ensure JSON is in <pre>
                time.sleep(random.uniform(0.2, 0.5))

                raw_data = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_data)
                quote = data['chart']['result'][0]['indicators']['quote'][0]
                
                # Extract and Save
                symbol = "TSLA"
                price_date = datetime.now()
                vals = (symbol, price_date, float(quote['close'][-1]), float(quote['open'][-1]), 
                        float(quote['high'][-1]), float(quote['low'][-1]), int(quote['volume'][-1]))

                insert_query = """INSERT INTO tsla_timered (symbol, price_date, close, open, high, low, volume)
                                  VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                cursor.execute(insert_query, vals)
                conn.commit()
                
                print(f"✅ [{status}] Saved: {vals[2]} at {price_date.strftime('%H:%M:%S')}")

            except Exception as e:
                print(f"❌ Error: {e}")
                if driver: driver.quit(); driver = None
                time.sleep(10)

            time.sleep(wait_time)

    finally:
        if 'cursor' in locals(): cursor.close()
        if conn: conn.close()
        if driver: driver.quit()

if __name__ == "__main__":
    run_worker()