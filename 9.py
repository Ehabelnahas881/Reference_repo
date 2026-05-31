import asyncio, time, pytz, os, random, re, json, logging
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
# Full list of 12 Assets
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "BABA", "COIN", "ARM"]]

# --- ANTI-BOT: USER AGENT POOL ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
]

class HardenedWorker:
    def __init__(self):
        self.current_ua = random.choice(USER_AGENTS)
        self.base_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1"
        }

    def get_headers(self):
        headers = self.base_headers.copy()
        headers["User-Agent"] = self.current_ua
        return headers

    async def click_consent(self, session):
        try:
            url = "https://finance.yahoo.com/quote/TSLA?guccounter=1"
            resp = await session.get(url, headers=self.get_headers(), impersonate="chrome124", timeout=15)
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    for btn in soup.find_all("button"):
                        if any(x in btn.get_text().lower() for x in ["agree", "akzeptieren", "accept", "alle"]):
                            if btn.get("name"): payload[btn.get("name")] = btn.get("value", "agree")
                    # Randomized jitter before clicking "Accept"
                    await asyncio.sleep(random.uniform(2.0, 5.0))
                    await session.post(action, data=payload, impersonate="chrome124", timeout=15)
            return True
        except Exception:
            return False

    async def fetch_price(self, session, ticker):
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}"
            resp = await session.get(url, headers=self.get_headers(), impersonate="chrome124", timeout=10)
            
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            
            # 1. Regex Match for raw JSON data
            pattern = rf'"{ticker}":\{{.*?"(?:post|overnight|regularMarket)Price":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            
            # 2. BeautifulSoup Fallback for specific qsp tags
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": re.compile(r"qsp-(post|overnight|price)")})
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
        except Exception:
            pass
        return None

    async def process_asset(self, asset, idx):
        ticker = asset['ticker']
        # Randomized start jitter to prevent all 12 assets hitting the server at the exact same second
        start_jitter = idx * random.uniform(0.3, 0.6) 
        
        while True:
            async with AsyncSession() as session:
                try:
                    await self.click_consent(session)
                    session_start = time.time()
                    
                    # Refresh session every 15 minutes to clear cookies/history
                    while time.time() - session_start < 900:
                        now = datetime.now(UTC)
                        wait_start = 60 - now.second - (now.microsecond / 1000000)
                        await asyncio.sleep(max(0, wait_start + start_jitter))
                        
                        ts_val = datetime.now(UTC).strftime('%H:%M:00')
                        prices = []
                        minute_start = time.time()

                        # Human-like capture points within the 60-second window
                        target_times = [
                            random.uniform(0.5, 8), 
                            random.uniform(15, 25),
                            random.uniform(30, 42),
                            random.uniform(49, 56) 
                        ]

                        for i in range(4):
                            p = await self.fetch_price(session, ticker)
                            if p == "RE-CLICK":
                                await self.click_consent(session)
                                p = await self.fetch_price(session, ticker)
                            
                            if isinstance(p, float):
                                prices.append(p)

                            if i < 3:
                                elapsed = time.time() - minute_start
                                sleep_dur = target_times[i+1] - elapsed
                                if sleep_dur > 0: await asyncio.sleep(sleep_dur)
                        
                        if len(prices) >= 1:
                            o, c, h, l = prices[0], prices[-1], max(prices), min(prices)
                            print(f"✅ [{ticker}] {ts_val} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f} (Pts:{len(prices)})", flush=True)

                except Exception as e:
                    logger.error(f"Worker {ticker} hit an error: {e}. Cooling down...")
                    # Rotate User-Agent on error
                    self.current_ua = random.choice(USER_AGENTS)
                    await asyncio.sleep(10)

async def main():
    print("🚀 CLOUD ENGINE ONLINE - 12 Assets | Jitter & UA Rotation Active", flush=True)
    worker = HardenedWorker()
    tasks = [asyncio.create_task(worker.process_asset(a, i)) for i, a in enumerate(ASSETS)]
    await asyncio.gather(*tasks)

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "active"}), 200

if __name__ == "__main__":
    import threading
    # Run Flask in a background thread for cloud health checks
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(" Manual shutdown initiated.")