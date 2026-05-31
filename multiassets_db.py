import asyncpg
import asyncio, time, pytz, os, random, re, json, logging, sys
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve # more convinient for production than Flask's built-in server especially for our 7/24 long-running scraper

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Market] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("scraper_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
# Updated list to 15 assets & suitable for multi-schema
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOG", "META", "HPQ", "AMD", "BBVA", "GDX", "ARM", "EWT", "INTC", "VUG"]]

# choosing user_agents are limited and specific to suit 'pod' environment
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]
#USER_AGENTS = [
#    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
 #   "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
 #   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
 #   "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
#]

db_queue = asyncio.Queue()

class MultiAssetsScraper:
    def __init__(self, process_name):
        self.process_name = process_name
        self.current_ua = random.choice(USER_AGENTS)
        self.headers = {
            "User-Agent": self.current_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br", # CRITICAL: Tell Yahoo you can handle compressed data
            "Referer": "https://finance.yahoo.com/", # CRITICAL: Makes it look like internal navigation
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin", # CHANGE this from 'none' to 'same-origin' after warm-up
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }
        #self.headers = {
        #    "User-Agent": self.current_ua,
        #    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        #    "Accept-Language": "en-US,en;q=0.9",
        #    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        #    "Sec-Ch-Ua-Mobile": "?0",
        #    "Sec-Ch-Ua-Platform": '"Windows"',
        #    "Sec-Fetch-Dest": "document",
        #    "Sec-Fetch-Mode": "navigate",
        #    "Sec-Fetch-Site": "none",
        #    "Sec-Fetch-User": "?1",
        #    "Upgrade-Insecure-Requests": "1",
        #}

    async def warm_session(self, session):
        try:
            logger.info(f"[{self.process_name}] Warming up session identity...")
            await session.get("https://www.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            await asyncio.sleep(random.lognormvariate(0.6, 0.2)) 
            await session.get("https://finance.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            return True
        except Exception:
            return False
    # Handle cookie consent if it appears, with different values for different regions/languages
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
                    await asyncio.sleep(random.lognormvariate(1.2, 0.4)) 
                    await session.post(action, data=payload, impersonate="chrome124", timeout=10)
            return True
        except: return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}?guccounter=1"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=8)
            if resp.status_code == 403:
                logger.error(f" [IP BLOCK] Yahoo returned 403 for {ticker}.")
                return "BLOCK"
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            pattern = rf'"{ticker}":\{{.*?"regularMarketPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            soup = BeautifulSoup(resp.text, 'lxml')
            el = (soup.find(attrs={"data-testid": "qsp-price"}))
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
        except Exception as e:
            logger.debug(f"Fetch error for {ticker}: {e}")
        return None

    async def process_asset(self, asset, idx): # Each asset gets a unique offset to stagger requests and reduce simultaneous hits at minute mark   
        ticker = asset['ticker']
        asset_process_offset = idx * 0.4 # Stagger start times by 0.4 seconds to reduce simultaneous requests at minute mark
        
        while True:
            async with AsyncSession() as session:
                try:
                    await self.warm_session(session)
                    await self.Cookies_Handler(session)
                    session_born = time.time()
                    session_lifespan = random.uniform(900, 1200) 
                    
                    while (time.time() - session_born) < session_lifespan:
                        now = datetime.now(UTC)
                        wait_start = 60 - now.second - (now.microsecond / 1000000)
                        minute_sync_jitter = random.uniform(0.5, 1.5)
                        await asyncio.sleep(max(0, wait_start + asset_process_offset + minute_sync_jitter))
                        
                        ts_val = datetime.now(UTC).replace(second=0, microsecond=0)
                        date_val = ts_val.date()
                        prices = []
                        minute_loop_start = time.time()
                        schedule = [random.uniform(14, 18), random.uniform(29, 33), random.uniform(44, 48)]
                       #schedule = [15.0, 30.0, 45.0] # It is not static timing, downsides we add the jitter logic smartly to ensure we are not hitting the same schedule every time.

                        for i in range(4): # Open, H, L, Close - we attempt to fetch price 4 times within the minute with strategic timing to capture different market states
                            p = await self.fetch_price(session, ticker)
                            if p == "BLOCK":
                                await asyncio.sleep(60) 
                                continue
                            if p == "RE-CLICK":
                                await self.Cookies_Handler(session)
                                p = await self.fetch_price(session, ticker)
                            
                            prices.append(p if isinstance(p, float) else None)
                            if i < 3: # 0 is open, 1-2 are mid-minute, 3 is close - (== 4 not 3)
                                current_elapsed = time.time() - minute_loop_start
                                sleep_dur = (schedule[i] + random.uniform(-0.5, 0.5)) - current_elapsed # Add small jitter to schedule and account for fetch time
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)

                        if len(prices) == 4 and prices[0] and prices[3]: 
                            mid_points = [v for v in [prices[1], prices[2]] if v is not None]
                            if mid_points:
                                h, l = max(mid_points), min(mid_points)
                                print(f" [{self.process_name}] {ts_val.strftime('%H:%M:%S')} | {ticker} | O:{prices[0]:.2f} C:{prices[3]:.2f}", flush=True)
                                # Pass ticker and OHLC data to queue
                                await db_queue.put({
                                    "ticker": ticker,
                                    "data": (date_val, ts_val, prices[0], h, l, prices[3])
                                })
                except Exception as e:
                    logger.error(f" [process ERROR] {ticker} crashed: {e}")
                    await asyncio.sleep(15)

# --- DATABASE WORKER ---
async def db_worker():
    conn = None
    try:
        conn = await asyncpg.connect(
            user="YFS", 
            password="YFSpostgres2025", 
            database="dyDATA_new", 
            host="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com",
            port=5432   
        )
        logger.info("[DB] Connection Established.")
        
        while True:
            item = await db_queue.get()
            ticker = item['ticker']
            payload = item['data']            
            try:
              async with conn.transaction():
                # Dynamic table selection based on ticker schema
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
                logger.info(f"[DB] Inserted {ticker} into ASSET_{ticker} schema.")
            except Exception as e:
                logger.error(f"[DB ERROR] Failed {ticker}: {e}")
            finally:
                db_queue.task_done()
    except Exception as e:
        logger.error(f"[DB FATAL] {e}")
    finally:
        if conn: await conn.close()

async def main():
    print(" HARDENED CLOUD ENGINE ONLINE - MULTI-SCHEMA CONFIG", flush=True)
    # Start DB worker and scrapers
    tasks = [asyncio.create_task(db_worker())]
    
    worker_a = MultiAssetsScraper("Process-A")
    worker_b = MultiAssetsScraper("Process-B")
    mid = len(ASSETS) // 2
    
    for i, a in enumerate(ASSETS[:mid]): tasks.append(asyncio.create_task(worker_a.process_asset(a, i)))
    for i, a in enumerate(ASSETS[mid:]): tasks.append(asyncio.create_task(worker_b.process_asset(a, i)))
    
    await asyncio.gather(*tasks)

# --- FLASK HEALTH CHECK ---
app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "active"}), 200

# --- MAIN EXECUTION WITH TERMINATION DIAGNOSTICS ---
if __name__ == "__main__":
    import threading
    # Start Web Server
    # WAITRESS WAITRESS WAITRESS
    # more convinient for production than Flask's built-in server especially for our 7/24 long-running scraper
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

