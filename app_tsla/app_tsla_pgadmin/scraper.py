import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
import psycopg2 
import time, json, random
from datetime import datetime

# --- AWS RDS DATABASE CONFIG ---
DB_CONFIG = {
    "dbname": "dyDATA_new",
    "user": "ehab.elnahas",
    "password": "test", # Ensure this matches your AWS password
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": "5432",
    "sslmode": "require"  # AWS RDS often requires SSL
}

def run_worker():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    
    driver = uc.Chrome(options=options, version_main=144)
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("🚀 Connected to AWS RDS successfully!")
    except Exception as e:
        print(f"❌ Database Connection Error: {e}")
        return

    print("🕵️ Scraper active. Monitoring TSLA...")

    try:
        while True:
            try:
                url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d"
                driver.get(url)
                
                raw_data = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_data)
                quote = data['chart']['result'][0]['indicators']['quote'][0]
                
                symbol = "TSLA"
                price_date = datetime.now()
                close = float(quote['close'][-1])
                open_p = float(quote['open'][-1])
                high = float(quote['high'][-1])
                low = float(quote['low'][-1])
                volume = int(quote['volume'][-1])

                insert_query = """
                INSERT INTO tsla (symbol, price_date, close, open, high, low, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                
                cursor.execute(insert_query, (symbol, price_date, close, open_p, high, low, volume))
                conn.commit()
                
                print(f"✅ AWS SQL Saved: {close} at {price_date.strftime('%H:%M:%S')}")

            except Exception as e:
                print(f"❌ Scraping Error: {e}")
                time.sleep(10)

            time.sleep(random.uniform(5, 8))
    finally:
        cursor.close()
        conn.close()
        driver.quit()

if __name__ == "__main__":
    run_worker()