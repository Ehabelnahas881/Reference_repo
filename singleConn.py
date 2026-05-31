import asyncpg
import asyncio, time, pytz, os, random, re, json, logging, sys
from datetime import datetime
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
# 12 Assets as per your previous stable config
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "HPQ", "AMD", "ARM", "INTC", "VUG"]]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# SEPARATED DB BUFFER: Scrapers drop data here and move on instantly
db_queue = asyncio.Queue()

class MultiAssetsScraper:
    def __init__(self, process_name):
        self.process_name = process_name
        # UA is now assigned per session-cycle for better stability
        self.current_ua = random.choice(USER_AGENTS)
        self.headers = {
            "User-Agent": self.current_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://finance.yahoo.com/",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    async def warm_session(self, session):
        try:
            logger.info(f"[{self.process_name}] Warming up session identity...")
            await session.get("https://www.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            await asyncio.sleep(random.uniform(1.0, 2.5)) 
            await session.get("https://finance.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            return True
        except Exception as e:
            logger.error(f"Warmup failed: {e}")
            return False

    async def Cookies_Handler(self, session):
        try:
            url = "https://finance.yahoo.com/quote/TSLA?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=10)
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
                    await session.post(action, data=payload, impersonate="chrome124", timeout=10)
            return True
        except Exception as e:
            logger.error(f"Cookie handler error: {e}")
            return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=8)
            
            if resp.status_code == 403:
                logger.error(f" [IP BLOCK] 403 for {ticker}.")
                return "BLOCK"
            if resp.status_code == 500:
                return "NIMBUS_ERROR"
                
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            
                        # Original BS4 Logic
            soup = BeautifulSoup(resp.text, 'lxml')
            el = (soup.find(attrs={"data-testid": "qsp-post-price"}))
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
            
            # Original Regex Logic
            pattern = rf'"{ticker}":\{{.*?"postMarketPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            
        except Exception as e:
            logger.debug(f"Fetch error for {ticker}: {e}")
        return None

    async def process_asset(self, asset, idx): 
        ticker = asset['ticker']
        # STAGGER START: idx * 1.5 avoids all 12 hitting at once
        await asyncio.sleep(idx * 1.5) 
        
        while True:
            # Sync UA to this session
            self.headers["User-Agent"] = random.choice(USER_AGENTS)
            async with AsyncSession() as session:
                try:
                    if not await self.warm_session(session):
                        await asyncio.sleep(10)
                        continue
                        
                    await self.Cookies_Handler(session)
                    session_born = time.time()
                    session_lifespan = random.uniform(900, 1200) 
                    
                    while (time.time() - session_born) < session_lifespan:
                        now = datetime.now(UTC)
                        wait_start = 60 - now.second - (now.microsecond / 1000000)
                        
                        # Minute Sync Jitter
                        minute_sync_jitter = random.uniform(1.0, 3.0) 
                        await asyncio.sleep(max(0, wait_start + minute_sync_jitter))
                        
                        ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                        date_val = ts_val.date()
                        prices = []
                        minute_loop_start = time.time()
                        
                        # Your Exact Schedule Logic
                        schedule = [random.uniform(14, 18), random.uniform(29, 33), random.uniform(44, 48)]

                        for i in range(4):
                            p = await self.fetch_price(session, ticker)
                            if p == "BLOCK":
                                await asyncio.sleep(300) 
                                break
                            if p == "NIMBUS_ERROR":
                                await asyncio.sleep(5) 
                                continue
                            if p == "RE-CLICK":
                                await self.Cookies_Handler(session)
                                p = await self.fetch_price(session, ticker)
                            
                            prices.append(p if isinstance(p, float) else None)
                            
                            if i < 3: 
                                current_elapsed = time.time() - minute_loop_start
                                sleep_dur = (schedule[i] + random.uniform(-0.5, 0.5)) - current_elapsed
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)

                        if len(prices) == 4 and prices[0] and prices[3]: 
                            mid_points = [v for v in [prices[1], prices[2]] if v is not None]
                            if mid_points:
                                h, l = max(mid_points), min(mid_points)
                                # FIRE AND FORGET: Push to DB worker queue
                                await db_queue.put({
                                    "ticker": ticker,
                                    "data": (date_val, ts_val, prices[0], h, l, prices[3])
                                })
                except Exception as e:
                    logger.error(f" [process ERROR] {ticker} crashed: {e}")
                    await asyncio.sleep(15)

# --- DATABASE WORKER: Runs in a dedicated background task ---
async def db_worker():
    conn = None
    while True:
        try:
            if conn is None:
                conn = await asyncpg.connect(
                    user="YFS", 
                    password="YFSpostgres2025", 
                    database="dyDATA_new", 
                    host="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
                    port=5432   
                )
                logger.info("[DB] Background connection established.")
            
            # Block until data is available in the queue
            item = await db_queue.get()
            ticker = item['ticker']
            payload = item['data']            
            
            try:
                query = f'''
                    INSERT INTO "ASSET_{ticker}"."one_min_timeseries_data" (
                        "one_min_timeseries_date", 
                        "one_min_timeseries_timestamp", 
                        "one_min_timeseries_OP_open_price", 
                        "one_min_timeseries_HP_high_price", 
                        "one_min_timeseries_LP_low_price", 
                        "one_min_timeseries_CP_close_price",
                        "one_min_timeseries_environment_PK"
                    ) VALUES ($1, $2, $3, $4, $5, $6, 4)
                    ON CONFLICT DO NOTHING
                '''
                await conn.execute(query, *payload)
            except Exception as e:
                logger.error(f"[DB ERROR] {ticker}: {e}")
                conn = None # Reset connection to refresh on next loop
            finally:
                db_queue.task_done()
        except Exception as e:
            logger.error(f"[DB FATAL] {e}")
            await asyncio.sleep(10)

async def main():
    print(" ENGINE ONLINE - PARALLEL DB MODE (Queue Buffer)", flush=True)
    # 1. Launch DB worker first
    asyncio.create_task(db_worker())
    
    worker_a = MultiAssetsScraper("Worker-A")
    worker_b = MultiAssetsScraper("Worker-B")
    mid = len(ASSETS) // 2
    
    tasks = []
    # 2. Launch 6 assets for each worker concurrently
    for i, a in enumerate(ASSETS[:mid]): tasks.append(asyncio.create_task(worker_a.process_asset(a, i)))
    for i, a in enumerate(ASSETS[mid:]): tasks.append(asyncio.create_task(worker_b.process_asset(a, i + mid)))
    
    await asyncio.gather(*tasks)

# --- FLASK HEALTH CHECK ---
app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "active"}), 200

if __name__ == "__main__":
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n [TERMINATION] Scraper stopped manually by user (KeyboardInterrupt).", flush=True)
    except ConnectionError:
        print("\n [TERMINATION] Internet connection lost or remote host closed connection.", flush=True)
    except SystemExit:
        print("\n [TERMINATION] The system/pod issued a shutdown command.", flush=True)
    except Exception as e:
        print(f"\n [CRITICAL FAILURE] Scraper stopped due to an unexpected error: {e}", flush=True)
    finally:
        print(" End of Session: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), flush=True)
        sys.exit(0)