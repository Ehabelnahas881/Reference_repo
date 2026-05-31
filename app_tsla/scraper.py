import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from neo4j import GraphDatabase
import time, json, random
from datetime import datetime

# Connection info
URI = "neo4j+s://911d884c.databases.neo4j.io"
AUTH = ("neo4j", "yUlQfnahT3pYB6uL0YoH5Rk4HpJgBL9XxyMZsjYp5ec")

def run_worker():
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    
    db_driver = GraphDatabase.driver(URI, auth=AUTH)
    driver = uc.Chrome(options=options, version_main=144)
    
    print("🕵️ Scraper active. Pushing to Aura Cloud...")

    try:
        while True:
            try:
                url = "https://query1.finance.yahoo.com/v8/finance/chart/TSLA?interval=1m&range=1d"
                driver.get(url)
                
                raw_data = driver.find_element(By.TAG_NAME, "pre").text
                data = json.loads(raw_data)
                quote = data['chart']['result'][0]['indicators']['quote'][0]
                
                payload = {
                    "timestamp": time.time(),
                    "date": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "close": float(quote['close'][-1]),
                    "open": float(quote['open'][-1]),
                    "high": float(quote['high'][-1]),
                    "low": float(quote['low'][-1]),
                    "volume": str(quote['volume'][-1])
                }

                with db_driver.session(database="neo4j") as session:
                    session.run("""
                        MERGE (s:Stock {symbol: 'TSLA'})
                        CREATE (p:Price $props)
                        CREATE (s)-[:HAS_PRICE]->(p)
                    """, props=payload)
                
                print(f"✅ TSLA Price Saved: {payload['close']}")

            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(10)

            time.sleep(random.uniform(5, 8))
    finally:
        driver.quit()
        db_driver.close()

if __name__ == "__main__":
    run_worker()