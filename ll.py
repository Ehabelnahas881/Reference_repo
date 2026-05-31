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
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36", "platform": '"Windows"', "impersonate": "chrome110"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36", "platform": '"macOS"', "impersonate": "chrome110"},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36", "platform": '"Linux"', "impersonate": "chrome110"}
]

# NEW: Dictionary of thread-safe queues (one per ticker)
asset_queues = {a['ticker']: queue.Queue() for a in ASSETS}

class MultiAssetsScraper:
    def __init__(self, process_name):
        self.process_name = process_name
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com/",
            "Sec-Ch-Ua": '"Chromium";v="110", "Google Chrome";v="110", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Upgrade-Insecure-Requests": "1",
        }

    async def warm_session(self, session, impersonate_key):
        try:
            logger.info(f"[{self.process_name}] Warming up session identity...")
            await session.get("https://www.yahoo.com", headers=self.headers, impersonate=impersonate_key, timeout=12)
            await asyncio.sleep(random.uniform(1.0, 2.5)) 
            await session.get("https://finance.yahoo.com", headers=self.headers, impersonate=impersonate_key, timeout=12)
            return True
        except Exception: return False

    async def Cookies_Handler(self, session, impersonate_key):
        try:
            resp = await session.get("https://finance.yahoo.com/quote/TSLA?guccounter=1", headers=self.headers, impersonate=impersonate_key, timeout=10)
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    for btn in soup.find_all("button"):
                        if any(x in btn.get_text().lower() for x in ["agree", "accept", "alle", "akseptieren"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value", "agree")
                    await asyncio.sleep(random.uniform(2.0, 4.0)) 
                    await session.post(action, data=payload, impersonate=impersonate_key, timeout=10)
            return True
        except Exception: return False

    async def fetch_price(self, session, ticker, impersonate_key):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate=impersonate_key, timeout=8)
            if resp.status_code == 403: return "BLOCK"
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-post-price"})
            
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
            return None
        except Exception: return None

    async def process_asset(self, asset, idx): 
        ticker = asset['ticker']
        await asyncio.sleep(idx * 5) 
        
        while True:
            fp = random.choice(FINGERPRINTS)
            self.headers["User-Agent"] = fp["ua"]
            self.headers["Sec-Ch-Ua-Platform"] = fp["platform"]
            impersonate_key = fp["impersonate"]

            async with AsyncSession(impersonate=impersonate_key) as session:
                try:
                    if not await self.warm_session(session, impersonate_key):
                        await asyncio.sleep(10); continue
                        
                    await self.Cookies_Handler(session, impersonate_key)
                    session_born = time.time()
                    session_lifespan = random.uniform(1800, 2700) 
                    
                    # Pick a unique randomized schedule for the life of this session
                    session_schedule = [
                        random.randint(13, 17), 
                        random.randint(28, 32), 
                        random.randint(43, 47), 
                        58
                    ]
                    
                    logger.info(f"[{ticker}] WORKER LIVE. Schedule: {session_schedule}")

                    while (time.time() - session_born) < session_lifespan:
                        now = datetime.now(UTC)
                        wait_to_sync = 60 - now.second - (now.microsecond / 1000000)
                        await asyncio.sleep(max(0, wait_to_sync + random.uniform(0.5, 1.5)))
                        
                        ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                        prices = []
                        minute_loop_start = time.time()

                        for i in range(4):
                            p = await self.fetch_price(session, ticker, impersonate_key)
                            if p == "BLOCK":
                                logger.warning(f"[{ticker}] 403. Cooling down...")
                                await asyncio.sleep(300); break
                            
                            prices.append(p if isinstance(p, float) else None)
                            if i < 3: 
                                sleep_dur = session_schedule[i] - (time.time() - minute_loop_start)
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)

                        valid_prices = [v for v in prices if v is not None]
                        # Verify we have enough data (Open, Middle1, Middle2, Close)
                        if len(valid_prices) == 4:
                            asset_queues[ticker].put({
                                "ticker": ticker,
                                "data": (
                                    ts_val.date(), 
                                    ts_val, 
                                    valid_prices[0],             # Open
                                    max(valid_prices[1:3]),      # High (max of middle two)
                                    min(valid_prices[1:3]),      # Low (min of middle two)
                                    valid_prices[3]              # Close
                                ),
                                "attempts": 0
                            })
                            logger.info(f"[{ticker}] Queued for Thread-Writer {ts_val.strftime('%H:%M')}")
                            logger.info(f"[{ticker}] Prices: {valid_prices}")

                except Exception as e:
                    logger.error(f"[{ticker}] Runtime Error: {e}")
                    await asyncio.sleep(15)

# NEW: The dedicated Writer logic adapted for a traditional thread
def start_asset_db_thread(ticker):
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
                        logger.info(f"[THREAD-{ticker}] DB Connected.")

                    item = q.get() # Thread blocks here until data arrives
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
                    logger.info(f"[THREAD-{ticker}] Data Stored.")
                    q.task_done()

                except Exception as e:
                    logger.error(f"[THREAD-{ticker}] DB ERROR: {e}")
                    conn = None # Reset connection on error
                    await asyncio.sleep(5)

        loop.run_until_complete(run_db())

    t = threading.Thread(target=db_worker_thread, daemon=True)
    t.start()

async def main():
    logger.info("ENGINE ONLINE - MULTI-THREADED ISOLATION ENABLED")
    
    # Launch one dedicated thread for every asset
    for asset in ASSETS:
        start_asset_db_thread(asset['ticker'])

    worker_a = MultiAssetsScraper("Worker-A")
    worker_b = MultiAssetsScraper("Worker-B")
    mid = len(ASSETS) // 2
    
    tasks = []
    for i, a in enumerate(ASSETS[:mid]): tasks.append(asyncio.create_task(worker_a.process_asset(a, i)))
    for i, a in enumerate(ASSETS[mid:]): tasks.append(asyncio.create_task(worker_b.process_asset(a, i + mid)))
    
    await asyncio.gather(*tasks)

app = Flask(__name__)
@app.route("/health")
def health(): 
    # Summary of all queue depths
    total_depth = sum(q.qsize() for q in asset_queues.values())
    return jsonify({"status": "active", "total_queue_depth": total_depth}), 200

if __name__ == "__main__":
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Engine Crash: {e}")
        sys.exit(1)