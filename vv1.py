import asyncpg
import asyncio, time, pytz, os, random, re, json, logging, sys
from datetime import datetime, date
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve 
import threading

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Market] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("scraper_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "META", "AMD", "INTC", "VUG", "HPQ"]]

FINGERPRINTS = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36", "platform": '"Windows"', "impersonate": "chrome110"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36", "platform": '"macOS"', "impersonate": "chrome110"}
]

db_queue = asyncio.Queue()

class MarketEngine:
    def __init__(self, name, worker_idx, asset_list):
        self.name = name
        self.asset_list = asset_list
        self.identity = FINGERPRINTS[worker_idx % len(FINGERPRINTS)]
        self.headers = {
            "User-Agent": self.identity["ua"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua-Platform": self.identity["platform"],
            "Referer": "https://finance.yahoo.com/",
            "Upgrade-Insecure-Requests": "1"
        }

    # --- COOKIES HANDLER RE-INSTATED ---
    async def handle_cookies(self, session):
        try:
            # Check a standard quote page for the consent redirect
            resp = await session.get("https://finance.yahoo.com/quote/TSLA", headers=self.headers, timeout=12)
            if "consent.yahoo.com" in resp.url:
                logger.info(f"[{self.name}] Handling Yahoo Consent redirect...")
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    # Find the "Agree" button
                    for btn in soup.find_all("button"):
                        if any(x in btn.get_text().lower() for x in ["agree", "accept", "accepter", "akzeptieren"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value")
                    
                    await asyncio.sleep(random.uniform(2, 4))
                    await session.post(action, data=payload, timeout=12)
                    logger.info(f"[{self.name}] Cookies accepted.")
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Cookie handling failed: {e}")
            return False

    async def warm_up(self, session):
        try:
            logger.info(f"[{self.name}] Warming Session (Impersonating {self.identity['platform']})...")
            await session.get("https://www.yahoo.com", headers=self.headers, timeout=15)
            await asyncio.sleep(random.uniform(2, 5))
            # Run the specific cookie/consent check
            await self.handle_cookies(session)
            return True
        except Exception as e:
            logger.error(f"[{self.name}] Warmup failed: {e}")
            return False

    async def fetch(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}"
            resp = await session.get(url, headers=self.headers, timeout=12)
            
            if resp.status_code in [403, 429, 500, 503]:
                return "BLOCK"
            
            if "consent.yahoo.com" in resp.url:
                await self.handle_cookies(session)
                return await self.fetch(session, ticker)

            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-overnight-price"})
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
        except:
            pass
        return None

    async def run(self):
        if "B" in self.name: await asyncio.sleep(45) 

        while True:
            async with AsyncSession(impersonate=self.identity["impersonate"]) as session:
                if not await self.warm_up(session):
                    await asyncio.sleep(60)
                    continue

                while True:
                    now = datetime.now(UTC)
                    wait = 60 - now.second - (now.microsecond / 1000000)
                    await asyncio.sleep(max(0, wait + random.uniform(3, 7)))
                    
                    ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                    
                    for asset in self.asset_list:
                        ticker = asset['ticker']
                        price = await self.fetch(session, ticker)
                        
                        if price == "BLOCK":
                            logger.error(f"[{self.name}] IP Blocked. Cooling down 10m.")
                            await asyncio.sleep(600)
                            break 

                        if isinstance(price, float):
                            # Pass as actual objects; we fix formatting in the SQL query
                            await db_queue.put({
                                "ticker": ticker,
                                "data": (ts_val.date(), ts_val, price, price, price, price)
                            })
                            print(f"[SUCCESS] {ts_val.strftime('%H:%M')} | {ticker}: {price:.2f}")
                        
                        await asyncio.sleep(random.uniform(9, 16))

# --- DB WORKER ---
async def db_writer():
    pool = None
    while True:
        item = await db_queue.get()
        try:
            if pool is None:
                pool = await asyncpg.create_pool(
                    user="YFS", password="YFSpostgres2025", database="dyDATA_new", 
                    host="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com", 
                    port=5432
                )
            
            async with pool.acquire() as conn:
                t, p = item['ticker'], item['data']
                # Explicitly cast $1 to DATE in the query to avoid 'toordinal' errors
                query = f'''
                    INSERT INTO "ASSET_{t}"."one_min_timeseries_data" (
                        "one_min_timeseries_date", "one_min_timeseries_timestamp", 
                        "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", 
                        "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price",
                        "one_min_timeseries_environment_PK"
                    ) VALUES ($1::DATE, $2, $3, $4, $5, $6, 4) ON CONFLICT DO NOTHING
                '''
                await conn.execute(query, *p)
                await asyncio.sleep(0.4) 
        except Exception as e:
            logger.error(f"[DB ERROR] {e}")
        finally:
            db_queue.task_done()

async def main():
    logger.info("ENGINE ONLINE - 10 ASSET PERSISTENT MODE")
    asyncio.create_task(db_writer())
    w1 = MarketEngine("Worker-A", 0, ASSETS[:5])
    w2 = MarketEngine("Worker-B", 1, ASSETS[5:])
    await asyncio.gather(w1.run(), w2.run())

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "active"}), 200

if __name__ == "__main__":
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    asyncio.run(main())