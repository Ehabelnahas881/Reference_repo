cat << 'EOF' > assets15_db.py
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
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "META", "HPQ", "AMD", "BBVA", "GDX", "ARM", "EWT", "INTC", "VUG"]]
# --- FEATURE D: HEADER ENTROPY GROUPS ---
# Ensures UA, Platform, and Impersonate stay logically consistent
# --- UPDATED FINGERPRINTS (9 Groups) ---
FINGERPRINTS = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "platform": '"Windows"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0", "platform": '"Windows"', "impersonate": "chrome124"}, # Using Chrome impersonation for stability
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0", "platform": '"Windows"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "platform": '"macOS"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:126.0) Gecko/20100101 Firefox/126.0", "platform": '"macOS"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15", "platform": '"macOS"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "platform": '"Linux"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0", "platform": '"Linux"', "impersonate": "chrome124"},
    {"ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36", "platform": '"Linux"', "impersonate": "chrome124"}
]

db_queue = asyncio.Queue()
FAILOVER_FILE = "failoverdb.json"

class MultiAssetsScraper:
    def __init__(self, process_name, worker_index): # Added worker_index
        self.process_name = process_name
        self.worker_index = worker_index 
        # Start at their index, but they will rotate within their "third" of the list
        self.identity_ptr = worker_index 
        self.identity = FINGERPRINTS[self.identity_ptr]
        self.headers = {
            "User-Agent": self.identity["ua"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://finance.yahoo.com/",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": self.identity["platform"],
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    async def warm_session(self, session):
        try:
            logger.info(f"[{self.process_name}] Warming identity: {self.identity['platform']}...")
            await session.get("https://www.yahoo.com", headers=self.headers, impersonate=self.identity["impersonate"], timeout=12)
            await asyncio.sleep(random.uniform(1.0, 2.5)) 
            await session.get("https://finance.yahoo.com", headers=self.headers, impersonate=self.identity["impersonate"], timeout=12)
            return True
        except Exception as e:
            logger.error(f"Warmup failed: {e}")
            return False

    async def Cookies_Handler(self, session):
        try:
            url = "https://finance.yahoo.com/quote/TSLA?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate=self.identity["impersonate"], timeout=10)
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
                    await session.post(action, data=payload, impersonate=self.identity["impersonate"], timeout=10)
            return True
        except Exception as e:
            logger.error(f"Cookie handler error: {e}")
            return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate=self.identity["impersonate"], timeout=8)
            if resp.status_code == 403:
                logger.error(f" [IP BLOCK] 403 for {ticker}.")
                return "BLOCK"
            if resp.status_code == 500:
                return "NIMBUS_ERROR"
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = (soup.find(attrs={"data-testid": "qsp-overnight-price"}))
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
            
            pattern = rf'"{ticker}":\{{.*?"overnightPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
        except Exception as e:
            logger.debug(f"Fetch error for {ticker}: {e}")
        return None

    async def process_asset(self, asset, idx): 
        ticker = asset['ticker']
        await asyncio.sleep(idx * 1.5) 
        
        while True:
            # Refresh Identity for new session cycle
            # SEQUENTIAL ROTATION: Each worker jumps by 3 to stay in its own "lane"
            self.identity_ptr = (self.identity_ptr + 3) % len(FINGERPRINTS)
            self.identity = FINGERPRINTS[self.identity_ptr]
            
            self.headers["User-Agent"] = self.identity["ua"]
            self.headers["Sec-Ch-Ua-Platform"] = self.identity["platform"]

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
                        minute_sync_jitter = random.uniform(1.0, 3.0) 
                        await asyncio.sleep(max(0, wait_start + minute_sync_jitter))
                        
                        ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                        date_val = ts_val.date()
                        prices = []
                        minute_loop_start = time.time()
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
                                await db_queue.put({
                                    "ticker": ticker,
                                    "data": (date_val.isoformat(), ts_val.isoformat(), prices[0], h, l, prices[3])
                                })
                                log_msg = f"O:{prices[0]:.2f} | H:{h:.2f} | L:{l:.2f} | C:{prices[3]:.2f}"
                                current_ts = ts_val.strftime('%H:%M:%S')
                                print(f"[LIVE] {current_ts} | {ticker}: {log_msg} -> [Queued for DB]", flush=True)
                except Exception as e:
                    logger.error(f" [process ERROR] {ticker} crashed: {e}")
                    await asyncio.sleep(15)

# --- FEATURE A & B: CONNECTION POOLING & FAILOVER ---
async def db_worker():
    pool = None
    while True:
        try:
            # 1. ALWAYS get the item from the queue first
            item = await db_queue.get()
            ticker = item['ticker']
            p_raw = item['data']
            
            # Convert ISO strings to DB-ready objects
            payload = (
                datetime.fromisoformat(p_raw[0]).date(), 
                datetime.fromisoformat(p_raw[1]), 
                *p_raw[2:]
            )

            if pool is None:
                ## notice this is the main idea of storing  1 thread and 1 Pipe in it 
                pool = await asyncpg.create_pool(
                    user="YFS",
                    password="YFSpostgres2025",
                    database="dyDATA_new", 
                    host="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
                    port=5432,
                    min_size=2,
                    max_size=10
                )

            async with pool.acquire() as conn:
                # Use double quotes for "ASSET_{ticker}" to handle case sensitivity
                query = f'''
                    INSERT INTO "ASSET_{ticker}"."one_min_timeseries_data" (
                        "one_min_timeseries_date", "one_min_timeseries_timestamp", 
                        "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", 
                        "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price",
                        "one_min_timeseries_environment_PK"
                    ) VALUES ($1, $2, $3, $4, $5, $6, 4) ON CONFLICT DO NOTHING
                '''
                await conn.execute(query, *payload)
            
            db_queue.task_done()

        except Exception as e:
            logger.error(f"[DB FAILOVER] Saving {ticker} to local disk. Error: {e}")
            # Append to local JSON if DB write fails
            backlog = []
            if os.path.exists(FAILOVER_FILE):
                try:
                    with open(FAILOVER_FILE, "r") as f: backlog = json.load(f)
                except: backlog = []
            backlog.append(item)
            with open(FAILOVER_FILE, "w") as f: json.dump(backlog, f)
            db_queue.task_done()
            await asyncio.sleep(1) # Short pause if DB is struggling

async def main():
    print(" ENGINE ONLINE - 3-WORKER / 15-ASSET MODE", flush=True)
    asyncio.create_task(db_worker())
    
    worker_a = MultiAssetsScraper("Worker-A", 0)
    worker_b = MultiAssetsScraper("Worker-B", 1)
    worker_c = MultiAssetsScraper("Worker-C", 2)
    
    # Split 15 assets into 3 groups of 5
    tasks = []
    for i, a in enumerate(ASSETS[:5]): 
        tasks.append(asyncio.create_task(worker_a.process_asset(a, i)))
    for i, a in enumerate(ASSETS[5:10]): 
        tasks.append(asyncio.create_task(worker_b.process_asset(a, i)))
    for i, a in enumerate(ASSETS[10:]): 
        tasks.append(asyncio.create_task(worker_c.process_asset(a, i)))
    
    await asyncio.gather(*tasks)

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
EOF