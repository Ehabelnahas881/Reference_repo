import asyncio, time, pytz, os, random, re, json, logging, sys
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve 

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Market] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[logging.FileHandler("trading_bot.log"), logging.StreamHandler()]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
# Updated list to 15 assets
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "BABA", "COIN", "ARM", "PYPL", "INTC", "MU"]]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

class HardenedWorker:
    def __init__(self, channel_name):
        self.channel_name = channel_name
        self.current_ua = random.choice(USER_AGENTS)
        self.headers = {
            "User-Agent": self.current_ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

    async def warm_session(self, session):
        try:
            logger.info(f"[{self.channel_name}] Warming up session identity...")
            await session.get("https://www.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            await asyncio.sleep(random.lognormvariate(0.6, 0.2)) 
            await session.get("https://finance.yahoo.com", headers=self.headers, impersonate="chrome124", timeout=12)
            return True
        except Exception:
            return False

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
                    for btn in soup.find_all("button"):
                        if any(x in btn.get_text().lower() for x in ["agree", "accept", "alle", "akseptieren"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value", "agree")
                    await asyncio.sleep(random.lognormvariate(1.2, 0.4)) 
                    await session.post(action, data=payload, impersonate="chrome124", timeout=10)
            return True
        except: return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=8)
            
            if resp.status_code == 403:
                logger.error(f" [IP BLOCK] Yahoo returned 403 for {ticker}. Cloud IP may be flagged.")
                return "BLOCK"
            
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            
            pattern = rf'"{ticker}":\{{.*?"regularMarketPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-price"})
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
            else:
                logger.warning(f" [SELECTOR MISSING] Could not find price for {ticker}.")
                
        except Exception as e:
            logger.debug(f"Fetch error for {ticker}: {e}")
        return None

    async def process_asset(self, asset, idx):
        ticker = asset['ticker']
        # Disciplined offset for 15 assets (0.4s)
        asset_channel_offset = idx * 0.4 
        
        while True:
            async with AsyncSession() as session:
                try:
                    await self.warm_session(session)
                    await self.click_consent(session)
                    session_born = time.time()
                    session_lifespan = random.uniform(900, 1200) 
                    
                    while (time.time() - session_born) < session_lifespan:
                        now = datetime.now(UTC)
                        wait_start = 60 - now.second - (now.microsecond / 1000000)
                        # Tighter jitter for high-density
                        minute_sync_jitter = random.uniform(0.5, 1.5)
                        await asyncio.sleep(max(0, wait_start + asset_channel_offset + minute_sync_jitter))
                        
                        ts_val = datetime.now(UTC).strftime('%H:%M:00')
                        prices = []
                        minute_loop_start = time.time()
                        # Strict scheduling
                        schedule = [15.0, 30.0, 45.0] ##[random.uniform(14, 18), random.uniform(29, 33), random.uniform(44, 48)]

                        for i in range(4):
                            p = await self.fetch_price(session, ticker)
                            if p == "BLOCK":
                                await asyncio.sleep(60) 
                                continue

                            if p == "RE-CLICK":
                                await self.click_consent(session)
                                p = await self.fetch_price(session, ticker)
                            
                            prices.append(p if isinstance(p, float) else None)
                            
                            if i < 3:
                                current_elapsed = time.time() - minute_loop_start
                                sleep_dur = (schedule[i] + random.uniform(-0.5, 0.5)) - current_elapsed
                                #this row consume [random.uniform(14, 18), random.uniform(29, 33), random.uniform(44, 48)]
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)

                        if len(prices) >= 1:
                            o, c = prices[0], prices[3]
                            mid_points = [v for v in [prices[1], prices[2]] if v is not None]
                            if o and c and mid_points:
                                h, l = max(mid_points), min(mid_points)
                                print(f" [{self.channel_name}] {ts_val} | {ticker} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}", flush=True)

                except Exception as e:
                    logger.error(f" [CHANNEL ERROR] Asset {ticker} in {self.channel_name} crashed: {e}")
                    await asyncio.sleep(15)

async def main():
    print(" HARDENED CLOUD ENGINE ONLINE - 15 ASSET CONFIG", flush=True)
    worker_a = HardenedWorker("CH-A")
    worker_b = HardenedWorker("CH-B")
    
    mid = len(ASSETS) // 2
    group_a = ASSETS[:mid]
    group_b = ASSETS[mid:]
    
    tasks = []
    for i, a in enumerate(group_a): tasks.append(asyncio.create_task(worker_a.process_asset(a, i)))
    for i, a in enumerate(group_b): tasks.append(asyncio.create_task(worker_b.process_asset(a, i)))
    
    await asyncio.gather(*tasks)

# --- FLASK HEALTH CHECK ---
app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "active"}), 200

# --- MAIN EXECUTION WITH TERMINATION DIAGNOSTICS ---
if __name__ == "__main__":
    import threading
    # Start Web Server
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