cat << 'EOF' > assets12.py
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
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "BABA", "COIN", "ARM"]]
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
                        if any(x in btn.get_text().lower() for x in ["Accepter tour", "akzeptieren", "agree", "accept", "alle"]):
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
            
            pattern = rf'"{ticker}":\{{.*?"postPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-post-price"})
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
        except: pass
        return None

    async def process_asset(self, asset, idx):
        ticker = asset['ticker']
        start_jitter = idx * 0.4 # Staggered entry for 12 assets
        
        while True:
            async with AsyncSession() as session:
                try:
                    await self.click_consent(session)
                    session_start = time.time()
                    
                    while time.time() - session_start < 900:
                        now = datetime.now(UTC)
                        wait_start = 60 - now.second - (now.microsecond / 1000000)
                        await asyncio.sleep(wait_start + start_jitter)
                        
                        ts_val = datetime.now(UTC).strftime('%H:%M:00')
                        prices = []
                        minute_start = time.time()

                        # Optimized timing to ensure capture is complete before min-end
                        target_times = [
                            random.uniform(0.5, 5),   # Point 1: Open
                            random.uniform(15, 25),  # Point 2: Mid
                            random.uniform(30, 42),  # Point 3: Mid
                            random.uniform(50, 54)   # Point 4: Close
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
                            # 1. Open and Close are exactly as captured
                            o, c = prices[0], prices[3]
                            # 2. High and Low are compared from the middle two only
                            h = max(prices[1], prices[2])
                            l = min(prices[1], prices[2])
                            
                            print(f"✅ FINAL {ts_val} | {ticker} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}", flush=True)

                except Exception:
                    await asyncio.sleep(5)

async def main():
    print("🚀 SCRAPER ACTIVE - 10 Assets | post Session | Jitter Enabled", flush=True)
    worker = HardenedWorker()
    tasks = [asyncio.create_task(worker.process_asset(a, i)) for i, a in enumerate(ASSETS)]
    await asyncio.gather(*tasks)

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt: pass
EOF