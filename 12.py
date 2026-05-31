import asyncio, time, pytz, os, random, re, json, logging, sys
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve
import asyncpg  

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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

db_queue = asyncio.Queue()

class HardenedWorker:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
        }

    async def warm_session(self, session):
        try:
            await session.get("https://www.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            await asyncio.sleep(random.lognormvariate(0.6, 0.2)) 
            await session.get("https://finance.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            return True
        except: return False

    async def click_consent(self, session):
        try:
            url = "https://finance.yahoo.com/quote/TSLA?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=10)
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    await asyncio.sleep(random.lognormvariate(1.2, 0.4)) 
                    await session.post(action, data=payload, impersonate="chrome124", timeout=10)
            return True
        except: return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=8)
            if resp.status_code == 403: return "BLOCK"
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            
            pattern = rf'"{ticker}":\{{.*?"overnightPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-post-price"}) or soup.find(attrs={"data-testid": "qsp-overnight-price"})
            if el and el.text: return float(re.sub(r'[^\d.]', '', el.text))
        except: pass
        return None

    async def process_asset(self, asset, idx):
        ticker = asset['ticker']
        offset = idx * 0.6 
        while True:
            async with AsyncSession() as session:
                try:
                    await self.warm_session(session)
                    await self.click_consent(session)
                    session_born = time.time()
                    
                    while (time.time() - session_born) < random.uniform(900, 1200):
                        now = datetime.now(UTC)
                        wait = 60 - now.second - (now.microsecond / 1000000)
                        await asyncio.sleep(max(0, wait + offset + random.uniform(0.8, 2.5)))
                        
                        ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                        date_val = ts_val.date()
                        prices = []
                        loop_start = time.time()
                        schedule = [random.uniform(14, 18), random.uniform(29, 33), random.uniform(44, 48)]

                        for i in range(4):
                            p = await self.fetch_price(session, ticker)
                            if p == "BLOCK": await asyncio.sleep(60); continue
                            if p == "RE-CLICK": 
                                await self.click_consent(session)
                                p = await self.fetch_price(session, ticker)
                            
                            prices.append(p if isinstance(p, float) else None)
                            if i < 3:
                                sleep_dur = schedule[i] - (time.time() - loop_start)
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)

                        if len(prices) == 4 and prices[0] and prices[3]:
                            mid = [v for v in [prices[1], prices[2]] if v is not None]
                            if mid:
                                h, l = max(mid), min(mid)
                                logger.info(f" [{self.channel_name}] {ts_val.strftime('%H:%M:%S')} | {ticker} | O:{prices[0]:.2f} C:{prices[3]:.2f}")
                                # PACKET: 6 items to match the 6 columns in db_worker
                                await db_queue.put((date_val, ts_val, prices[0], h, l, prices[3]))
                except Exception as e:
                    logger.error(f" [CHANNEL ERROR] {ticker}: {e}")
                    await asyncio.sleep(15)

# --- DATABASE WORKER ---
async def db_worker():
    conn = None
    try:
        conn = await asyncpg.connect(
            user="ehab.elnahas", 
            password="test", 
            database="dyDATA_new", 
            host="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
        )
        logger.info("[DB] Connection Established.")
        
        while True:
            item = await db_queue.get()
            batch = [item]
            while not db_queue.empty() and len(batch) < 12:
                batch.append(db_queue.get_nowait())
            
            try:
                # Strictly inserting the 6 OHLC/Time features
                await conn.executemany('''
                    INSERT INTO "TEST_TSLA"."one_min_timeseries_data" (
                        "one_min_timeseries_date", 
                        "one_min_timeseries_timestamp", 
                        "one_min_timeseries_OP_open_price", 
                        "one_min_timeseries_HP_high_price", 
                        "one_min_timeseries_LP_low_price", 
                        "one_min_timeseries_CP_close_price"
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                ''', batch)
                logger.info(f"[DB] Successfully inserted batch of {len(batch)}")
            except Exception as e:
                logger.error(f"[DB ERROR] {e}")
            finally:
                for _ in range(len(batch)): db_queue.task_done()
    except Exception as e:
        logger.error(f"[DB FATAL] {e}")
    finally:
        if conn: await conn.close()

async def main():
    logger.info("ENGINE STARTING...")
    tasks = [asyncio.create_task(db_worker())]
    
    mid_point = len(ASSETS) // 2
    group_a, group_b = ASSETS[:mid_point], ASSETS[mid_point:]
    
    worker_a, worker_b = HardenedWorker("CH-A"), HardenedWorker("CH-B")
    for i, a in enumerate(group_a): tasks.append(asyncio.create_task(worker_a.process_asset(a, i)))
    for i, a in enumerate(group_b): tasks.append(asyncio.create_task(worker_b.process_asset(a, i)))
    
    await asyncio.gather(*tasks)

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "active"}), 200

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): pass
    finally:
        sys.exit(0)
        
(.venv) PS C:\Users\ehaba\OneDrive\scraper> & c:\Users\ehaba\OneDrive\scraper\.venv\Scripts\python.exe c:/Users/ehaba/OneDrive/scraper/12.py
2026-04-22 01:31:53 - [Market] ENGINE STARTING...
2026-04-22 01:31:53 - [Market] Serving on http://0.0.0.0:3989
2026-04-22 01:31:54 - [Market] [DB] Connection Established.
2026-04-22 01:35:00 - [Market]  [CH-A] 23:34:00 | GOOGL | O:334.74 C:334.88
2026-04-22 01:35:18 - [Market] [DB ERROR] permission denied for sequence one_minute_timeseries_data_seq
2026-04-22 01:35:50 - [Market]  [CH-B] 23:35:00 | AMD | O:286.45 C:286.39
2026-04-22 01:35:51 - [Market]  [CH-B] 23:35:00 | NFLX | O:92.90 C:92.90
2026-04-22 01:35:52 - [Market]  [CH-B] 23:35:00 | META | O:672.30 C:672.35
2026-04-22 01:35:53 - [Market]  [CH-A] 23:35:00 | NVDA | O:200.58 C:200.56
2026-04-22 01:35:54 - [Market]  [CH-A] 23:35:00 | TSLA | O:388.43 C:388.39
2026-04-22 01:35:54 - [Market]  [CH-A] 23:35:00 | AAPL | O:267.48 C:267.50
2026-04-22 01:35:55 - [Market]  [CH-B] 23:35:00 | ARM | O:176.70 C:176.70
2026-04-22 01:35:55 - [Market]  [CH-B] 23:35:00 | COIN | O:199.26 C:199.27
2026-04-22 01:35:56 - [Market]  [CH-A] 23:35:00 | AMZN | O:251.69 C:251.69
2026-04-22 01:35:56 - [Market]  [CH-A] 23:35:00 | MSFT | O:425.50 C:425.60
2026-04-22 01:36:03 - [Market] [DB ERROR] permission denied for sequence one_minute_timeseries_data_seq
2026-04-22 01:36:03 - [Market] [DB ERROR] permission denied for sequence one_minute_timeseries_data_seq
(.venv) PS C:\Users\ehaba\OneDrive\scraper> 

GRANT USAGE, SELECT ON SEQUENCE "TEST_TSLA".one_minute_timeseries_data_seq TO "ehab.elnahas";