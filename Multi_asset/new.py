import asyncio, time, pytz, os, random, re, json, logging
import psutil
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- LOGGING: CRITICAL FOR NOHUP ---
# We force flush so 'tail -f nohup.out' shows data immediately
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Overnight] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL"]]

# Rotating User Agents to prevent fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

class HardenedWorker:
    def __init__(self):
        self.base_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"'
        }

    async def click_consent(self, session):
        """Self-healing consent bypass with timeout."""
        try:
            ua = random.choice(USER_AGENTS)
            # Use guccounter to trigger the wall
            url = f"https://finance.yahoo.com/quote/TSLA?guccounter=1&t={int(time.time())}"
            resp = await session.get(url, headers={**self.base_headers, "User-Agent": ua}, impersonate="chrome124", timeout=20)
            
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    payload["agree"] = "agree"
                    # Small delay to mimic human reaction
                    await asyncio.sleep(random.uniform(1, 2))
                    await session.post(action, data=payload, impersonate="chrome124", timeout=20)
            return True
        except Exception:
            return False

    async def fetch_price(self, session, ticker):
        """Targeted extraction with 'Cache-Busting'."""
        try:
            # Random param 'p' and timestamp 'ts' prevent Data Center caching
            url = f"https://finance.yahoo.com/quote/{ticker}/?p={ticker}&ts={int(time.time() * 1000)}&nc={random.random()}"
            headers = {
                **self.base_headers, 
                "User-Agent": random.choice(USER_AGENTS),
                "Referer": f"https://finance.yahoo.com/quote/{ticker}"
            }
            
            resp = await session.get(url, headers=headers, impersonate="chrome124", timeout=15)
            
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            if resp.status_code == 429: return "LIMIT"

            # Strict Ticker-Isolated Regex
            json_blob = re.search(rf'"{ticker}":\{{.*?}}', resp.text)
            if json_blob:
                data = json_blob.group(0)
                ov_match = re.search(r'"overnightPrice":\{"raw":([\d\.]+)', data)
                if ov_match: return float(ov_match.group(1))

            # DOM Fallback
            soup = BeautifulSoup(resp.text, 'html.parser')
            ov_el = soup.find(attrs={"data-testid": "qsp-overnight-price"})
            if ov_el and ov_el.text:
                return float(re.sub(r'[^\d.]', '', ov_el.text))
        except: pass
        return None

    async def process_asset(self, asset):
        ticker = asset['ticker']
        while True:
            # We recreate the session every 15 mins to clear potential 'dirty' cookies
            async with AsyncSession() as session:
                try:
                    if not await self.click_consent(session):
                        await asyncio.sleep(30); continue
                    
                    session_start = time.time()
                    first_run = True
                    
                    while time.time() - session_start < 900: # 15 min session life
                        if not first_run:
                            now = datetime.now(UTC)
                            # Precision sleep to hit the top of the minute
                            await asyncio.sleep(60 - now.second - (now.microsecond / 1000000) + 0.02)
                        
                        first_run = False
                        ts_val = datetime.now(UTC).strftime('%H:%M:00')
                        prices = []
                        
                        # 6 iterations with jitter to avoid pattern detection
                        for _ in range(6):
                            p = await self.fetch_price(session, ticker)
                            if p == "RE-CLICK":
                                await self.click_consent(session); break
                            if p == "LIMIT":
                                logger.error(f"IP BLOCKED for {ticker}. Resting 10 mins.")
                                await asyncio.sleep(600); break
                            
                            if isinstance(p, float) and p > 0:
                                prices.append(p)
                            
                            await asyncio.sleep(random.uniform(8.4, 9.2))
                        
                        if prices:
                            o, h, l, c = prices[0], max(prices), min(prices), prices[-1]
                            # Clean output for nohup logs
                            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - [Overnight] {ticker} O:{o:.2f} | H:{h:.2f} | L:{l:.2f} | C:{c:.2f} | TS:{ts_val}", flush=True)
                except Exception as e:
                    await asyncio.sleep(10)

async def main():
    worker = HardenedWorker()
    tasks = [asyncio.create_task(worker.process_asset(a)) for a in ASSETS]
    # Keep the main loop alive and monitor RAM
    while True:
        await asyncio.sleep(3600)

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "running", "uptime": "active"}), 200

if __name__ == "__main__":
    import threading
    # Run Flask in a background thread
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=3989, use_reloader=False), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


