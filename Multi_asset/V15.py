import asyncio, time, pytz, os, random, re, json, logging
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from waitress import serve  # Solution for Production Server

# --- LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Market] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Bot")

UTC = pytz.utc
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL"]]

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
        try:
            ua = random.choice(USER_AGENTS)
            url = f"https://finance.yahoo.com/quote/TSLA?guccounter=1&t={int(time.time())}"
            resp = await session.get(url, headers={**self.base_headers, "User-Agent": ua}, impersonate="chrome124", timeout=15)
            
            if "consent.yahoo.com" in resp.url:
                soup = BeautifulSoup(resp.text, 'html.parser')
                form = soup.find("form")
                if form:
                    action = urljoin(resp.url, form.get('action', ''))
                    payload = {i.get("name"): i.get("value") for i in form.find_all("input") if i.get("name")}
                    payload["agree"] = "agree"
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                    await session.post(action, data=payload, impersonate="chrome124", timeout=15)
            return True
        except: return False

    async def fetch_price(self, session, ticker):
        """Optimized dual-session extraction."""
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}/?p={ticker}&ts={int(time.time() * 1000)}&nc={random.random()}"
            headers = {**self.base_headers, "User-Agent": random.choice(USER_AGENTS), "Referer": f"https://finance.yahoo.com/quote/{ticker}"}
            
            resp = await session.get(url, headers=headers, impersonate="chrome124", timeout=10)
            if "consent.yahoo.com" in resp.url: return "RE-CLICK"
            if resp.status_code == 429: return "LIMIT"

            # Priority 1: Regex (Fastest)
            json_blob = re.search(rf'"{ticker}":\{{.*?}}', resp.text)
            if json_blob:
                data = json_blob.group(0)
                ov = re.search(r'"overnightPrice":\{"raw":([\d\.]+)', data)
                if ov: return float(ov.group(1))
                pm = re.search(r'"postMarketPrice":\{"raw":([\d\.]+)', data)
                if pm: return float(pm.group(1))

            # Priority 2: DOM test-ids
            soup = BeautifulSoup(resp.text, 'lxml') # Using lxml for faster parsing
            el = soup.find(attrs={"data-testid": "qsp-overnight-price"}) or \
                 soup.find(attrs={"data-testid": "qsp-post-price"})
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
        except: pass
        return None

    async def process_asset(self, asset):
        ticker = asset['ticker']
        while True:
            async with AsyncSession() as session:
                try:
                    if not await self.click_consent(session):
                        await asyncio.sleep(10); continue
                    
                    session_start = time.time()
                    while time.time() - session_start < 900:
                        # 1. SYNCHRONIZE TO TOP OF MINUTE
                        now = datetime.now(UTC)
                        wait_start = 60 - now.second - (now.microsecond / 1000000)
                        await asyncio.sleep(wait_start + 0.05)
                        
                        ts_val = datetime.now(UTC).strftime('%H:%M:00')
                        prices = []
                        minute_start_time = time.time()

                        # 2. RUN 6 ITERATIONS WITH DYNAMIC JITTER
                        for i in range(6):
                            p = await self.fetch_price(session, ticker)
                            
                            if p == "RE-CLICK":
                                await self.click_consent(session); break
                            if p == "LIMIT":
                                logger.error(f"LIMIT for {ticker}. Resting.")
                                await asyncio.sleep(300); break
                            
                            if isinstance(p, float): prices.append(p)

                            # CALCULATE DYNAMIC SLEEP
                            # We want to finish 6 requests by second 55
                            elapsed = time.time() - minute_start_time
                            remaining_time = 55 - elapsed
                            remaining_iters = 5 - i
                            
                            if remaining_iters > 0:
                                sleep_time = max(0.5, remaining_time / remaining_iters)
                                # Add a tiny bit of jitter to the calculated sleep
                                await asyncio.sleep(sleep_time + random.uniform(-0.2, 0.2))
                        
                        if prices:
                            o, h, l, c = prices[0], max(prices), min(prices), prices[-1]
                            print(f"{datetime.now().strftime('%H:%M:%S')} - [DATA] {ticker} O:{o:.2f} | H:{h:.2f} | L:{l:.2f} | C:{c:.2f} | TS:{ts_val}", flush=True)

                except Exception:
                    await asyncio.sleep(5)

async def main():
    worker = HardenedWorker()
    tasks = [asyncio.create_task(worker.process_asset(a)) for a in ASSETS]
    await asyncio.gather(*tasks)

app = Flask(__name__)
@app.route("/health")
def health(): return jsonify({"status": "running"}), 200

if __name__ == "__main__":
    import threading
    # SOLUTION: Using Waitress for production serving
    threading.Thread(target=lambda: serve(app, host="0.0.0.0", port=3989), daemon=True).start()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


nohup python3 max_assets.py > maxassets 2>&1 &
pkill -9 python3
tail -f -n+1 max_assets2.log

cat /proc/net/dev | grep eth0

ps -p $(pgrep -f assets15_db.py) -o etime,time,pcpu

top -b -d 5 -p $(pgrep -f assets15_db.py) | grep python3

top -p $(pgrep -f assets15_db.py)
###################################################################
###################################################################
###################################################################
# -o: etime (elapsed time), %cpu (avg cpu ratio), rss (actual RAM in KB), %mem (ram ratio)
ps -p $(pgrep -f latest.py) -o etime,%cpu,rss,%mem
%cpu (avg cpu ratio), rss (actual RAM in KB), %mem (ram ratio)
ps -p $(pgrep -f latest.py) -o etime,%cpu,rss,%mem
    ELAPSED %CPU   RSS %MEM
      51:12 13.4 226244  5.7


# 1. Grab initial bytes
START_NET=$(cat /proc/net/dev | grep eth0 | awk '{print $2}')
echo "Calculating network flow for 60 seconds (Using Python Math)..."
sleep 60

# 2. Grab ending bytes
END_NET=$(cat /proc/net/dev | grep eth0 | awk '{print $2}')

# 3. Use Python to do the math safely
python3 -c "
diff = $END_NET - $START_NET
mb_min = diff / 1048576
kb_sec = (diff / 1024) / 60
print('-' * 42)
print(f'VALUE:  {mb_min:.2f} MB used this minute')
print(f'FLOW:   {kb_sec:.2f} KB/s average speed')
print('-' * 42)
"