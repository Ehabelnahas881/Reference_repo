import asyncio, time, pytz, os, random, re, json, logging
import asyncpg  # Faster, async-native driver for PostgreSQL
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve 

# --- CONFIGURATION ---
DB_CONFIG = {
    "user": "ehab.elnahas",
    "password": "test",
    "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
    "port": "5432",
    "database": "dyDATA_new"
}
TABLE_NAME = '"TEST_TSLA"."one_min_timeseries_data"'

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Market] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "BABA", "COIN", "ARM"]]
USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]

# Global Queue for DB writing
db_queue = asyncio.Queue()

class DatabaseManager:
    """Handles persistent connection pooling and batch writing."""
    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(**DB_CONFIG, min_size=5, max_size=10)
        logger.info("Connected to AWS RDS Pool.")

    async def writer_task(self):
        """Background task that drains the queue and saves to DB."""
        while True:
            data = await db_queue.get()
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(f"""
                        INSERT INTO {TABLE_NAME} (
                            "one_min_timeseries_date",
                            "one_min_timeseries_timestamp",
                            "one_min_timeseries_OP_open_price",
                            "one_min_timeseries_HP_high_price",
                            "one_min_timeseries_LP_low_price",
                            "one_min_timeseries_CP_close_price",
                            "one_min_timeseries_PK",
                            "one_min_timeseries_creation_date_time",
                            "one_min_timeseries_last_modification_date_time"
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """, *data)
                # logger.info(f"DB Insert Success: {data[6]}") # PK tracking
            except Exception as e:
                logger.error(f"DB Write Error: {e}")
            finally:
                db_queue.task_done()

class HardenedWorker:
    def __init__(self):
        self.base_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none"
        }

    async def click_consent(self, session):
        try:
            url = "https://finance.yahoo.com/quote/TSLA?guccounter=1"
            resp = await session.get(url, headers={**self.base_headers, "User-Agent": random.choice(USER_AGENTS)}, impersonate="chrome124", timeout=15)
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    for btn in soup.find_all("button"):
                        if any(x in btn.get_text().lower() for x in ["agree", "accept", "accepter", "alle"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value", "agree")
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    await session.post(action, data=payload, impersonate="chrome124", timeout=15)
            return True
        except: return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}"
            resp = await session.get(url, headers={**self.base_headers, "User-Agent": random.choice(USER_AGENTS)}, impersonate="chrome124", timeout=10)
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            
            # Strict Ticker-Specific Pattern
            pattern = rf'"{ticker}":\{{.*?"(postMarket|overnight|regularMarket)Price":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(2))
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": re.compile(r"qsp-(post|overnight|price)")})
            if el and el.text: return float(re.sub(r'[^\d.]', '', el.text))
        except: pass
        return None

    async def process_asset(self, asset, idx):
        ticker = asset['ticker']
        start_jitter = idx * 0.4 
        
        while True:
            async with AsyncSession() as session:
                try:
                    await self.click_consent(session)
                    session_start = time.time()
                    
                    while time.time() - session_start < 900:
                        now_utc = datetime.now(UTC)
                        wait_start = 60 - now_utc.second - (now_utc.microsecond / 1000000)
                        await asyncio.sleep(wait_start + start_jitter)
                        
                        ts_val = datetime.now(UTC).strftime('%H:%M:00')
                        prices = []
                        minute_start = time.time()

                        target_times = [0.5, 18.0, 36.0, 52.0]

                        for i in range(4):
                            p = await self.fetch_price(session, ticker)
                            if p == "RE-CLICK":
                                await self.click_consent(session)
                                p = await self.fetch_price(session, ticker)
                            
                            if isinstance(p, float): prices.append(p)
                            if i < 3:
                                elapsed = time.time() - minute_start
                                sleep_dur = target_times[i+1] - elapsed
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)
                        
                        if len(prices) >= 2:
                            o, c = prices[0], prices[-1]
                            h, l = max(prices), min(prices)
                            
                            now_stamp = datetime.now(UTC)
                            pk = f"{ticker}_{now_stamp.strftime('%Y%m%d%H%M')}"
                            
                            # Prepare data for DB matching your table columns
                            db_row = (
                                now_stamp.date(),                # date
                                now_stamp.time(),                # timestamp
                                float(o), float(h), float(l), float(c), # OHLC
                                pk,                              # PK (Ticker + Time)
                                now_stamp,                       # creation
                                now_stamp                        # modification
                            )
                            
                            await db_queue.put(db_row)
                            print(f"✅ {ts_val} | {ticker} | O:{o:.2f} C:{c:.2f} >> QUEUED", flush=True)

                except Exception as e:
                    logger.error(f"Worker Error [{ticker}]: {e}")
                    await asyncio.sleep(10)

async def main():
    db_manager = DatabaseManager()
    await db_manager.connect()
    
    # Start the single background writer
    asyncio.create_task(db_manager.writer_task())
    
    worker = HardenedWorker()
    tasks = [asyncio.create_task(worker.process_asset(a, i)) for i, a in enumerate(ASSETS)]
    await asyncio.gather(*tasks)

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "healthy", "queue_size": db_queue.qsize()}), 200

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt: pass