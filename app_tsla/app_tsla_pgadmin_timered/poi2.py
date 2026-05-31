import asyncpg
import asyncio, time, pytz, os, random, re, json, logging, sys
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve 
import threading
import queue

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Market] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("scraper_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "HPQ", "AMD", "ARM"]]

FINGERPRINTS = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36", "platform": '"Windows"'},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36", "platform": '"macOS"'},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36", "platform": '"Linux"'}
]

# Thread-safe queues for the Hybrid Model
asset_queues = {a['ticker']: queue.Queue() for a in ASSETS}

class MultiAssetsScraper:
    def __init__(self, process_name):
        self.process_name = process_name

    def get_headers(self, fp):
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com/",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": fp["ua"],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Ch-Ua-Platform": fp["platform"]
        }

    async def warm_session(self, session, fp):
        try:
            h = self.get_headers(fp)
            await session.get("https://www.yahoo.com", headers=h, impersonate="chrome", timeout=15)
            await asyncio.sleep(random.uniform(1.5, 3)) 
            resp = await session.get("https://finance.yahoo.com/quote/TSLA?guccounter=1", headers=h, impersonate="chrome", timeout=15)
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    for btn in soup.find_all("button"):
                        if any(k in btn.get_text().lower() for k in ["akseptieren", "agree", "accept", "alle"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value", "agree")
                    await asyncio.sleep(random.uniform(2, 4))
                    await session.post(action, data=payload, headers=h, impersonate="chrome", timeout=15)
            return True
        except Exception: return False

    async def fetch_price(self, session, ticker, fp):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}?guccounter=1"
            resp = await session.get(url, headers=self.get_headers(fp), impersonate="chrome", timeout=10)
            if resp.status_code == 403: return "BLOCK"
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-post-price"})
            return float(re.sub(r'[^\d.]', '', el.text)) if el else None
        except Exception: return None

    async def run_worker_loop(self, assets_subset):
        while True:
            fp = random.choice(FINGERPRINTS)
            async with AsyncSession(impersonate="chrome") as session:
                if not await self.warm_session(session, fp):
                    await asyncio.sleep(30); continue
                
                # Hybrid: Map each asset to the shared session
                tasks = [self.process_asset_in_session(session, a['ticker'], fp) for a in assets_subset]
                await asyncio.gather(*tasks)

    async def process_asset_in_session(self, session, ticker, fp): 
        while True:
            now = datetime.now(UTC)
            wait_to_sync = 60 - now.second - (now.microsecond / 1000000)
            await asyncio.sleep(max(0, wait_to_sync + random.uniform(0.1, 2.0)))
            
            ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
            # LOGIC: Randomized 4-fetch schedule per minute
            random_schedule = sorted([random.uniform(1, 56) for _ in range(4)])
            prices, start_time = [], time.time()

            for target in random_schedule:
                elapsed = time.time() - start_time
                await asyncio.sleep(max(0, target - elapsed))
                p = await self.fetch_price(session, ticker, fp)
                if p == "BLOCK": return 
                prices.append(p if isinstance(p, float) else None)

            valid_prices = [v for v in prices if v is not None]
            if valid_prices:
                # HYBRID: Push to Threaded Queue instead of direct DB write
                asset_queues[ticker].put({
                    "ticker": ticker,
                    "data": (ts_val.date(), ts_val, valid_prices[0], max(valid_prices), min(valid_prices), valid_prices[-1])
                })
                logger.info(f"[{ticker}] Synced to Threaded-Writer: {ts_val.strftime('%H:%M')}")

def start_asset_db_thread(ticker):
    """The 'Threaded Database Worker' side of the Hybrid Model."""
    def db_worker_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def run_db():
            conn = None
            q = asset_queues[ticker]
            while True:
                try:
                    if conn is None:
                        conn = await asyncpg.connect(
                            user="YFS", password="YFSpostgres2025", 
                            database="dyDATA_new", host="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com", port=5432
                        )
                    item = q.get() 
                    payload = item['data']
                    query = f'''
                        INSERT INTO "ASSET_{ticker}"."one_min_timeseries_data" (
                            "one_min_timeseries_date", "one_min_timeseries_timestamp", 
                            "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", 
                            "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price",
                            "one_min_timeseries_environment_PK"
                        ) VALUES ($1, $2, $3, $4, $5, $6, 4)
                        ON CONFLICT DO NOTHING
                    '''
                    await conn.execute(query, *payload)
                    q.task_done()
                except Exception as e:
                    logger.error(f"[DB-THREAD-{ticker}] Error: {e}")
                    conn = None
                    await asyncio.sleep(5)
        loop.run_until_complete(run_db())
    threading.Thread(target=db_worker_thread, daemon=True).start()

async def main():
    logger.info("HYBRID ENGINE STARTING...")
    for asset in ASSETS:
        start_asset_db_thread(asset['ticker'])

    worker_a = MultiAssetsScraper("Worker-A")
    worker_b = MultiAssetsScraper("Worker-B")
    mid = len(ASSETS) // 2
    
    await asyncio.gather(
        worker_a.run_worker_loop(ASSETS[:mid]),
        worker_b.run_worker_loop(ASSETS[mid:])
    )

app = Flask(__name__)
@app.route("/health")
def health(): 
    return jsonify({"status": "active", "queue_backlog": sum(q.qsize() for q in asset_queues.values())}), 200

if __name__ == "__main__":
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)