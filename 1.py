cat << 'EOF' > production.py
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
ASSETS = [{"ticker": t} for t in ["TSLA", "AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "NFLX", "AMD", "BABA"]]
USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"]

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
                        if any(x in btn.get_text().lower() for x in ["agree", "akzeptieren", "accept", "alle"]):
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
            
            pattern = rf'"{ticker}":\{{.*?"overnightPrice":\{{"raw":([\d\.]+)'
            match = re.search(pattern, resp.text)
            if match: return float(match.group(1))
            
            soup = BeautifulSoup(resp.text, 'lxml')
            el = soup.find(attrs={"data-testid": "qsp-overnight-price"})
            if el and el.text:
                return float(re.sub(r'[^\d.]', '', el.text))
        except: pass
        return None

    async def process_asset(self, asset, idx):
        ticker = asset['ticker']
        start_jitter = idx * 0.15 # Staggered entry for 10 assets
        
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
                        
                        if len(prices) == 4:
                            # 1. Open and Close are exactly as captured
                            o, c = prices[0], prices[3]
                            # 2. High and Low are compared from the middle two only
                            h = max(prices[1], prices[2])
                            l = min(prices[1], prices[2])
                            
                            print(f"✅ FINAL {ts_val} | {ticker} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}", flush=True)

                except Exception:
                    await asyncio.sleep(5)

async def main():
    print("🚀 SCRAPER ACTIVE - 10 Assets | Overnight Session | Jitter Enabled", flush=True)
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


root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ nohup python -u production.py > production.log 2>&1 &
[1] 318
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ tail -f production.log
nohup: ignoring input
🚀 SCRAPER ACTIVE - 10 Assets | Overnight Session | Jitter Enabled
2026-04-16 03:45:44 - [Market] Serving on http://0.0.0.0:3989
✅ FINAL 03:46:00 | AAPL | O:266.70 H:266.70 L:266.70 C:266.70
✅ FINAL 03:46:00 | NFLX | O:107.93 H:107.94 L:107.93 C:107.93
✅ FINAL 03:46:00 | META | O:674.51 H:674.64 L:674.51 C:674.64
✅ FINAL 03:46:00 | GOOGL | O:338.65 H:338.66 L:338.65 C:338.69
✅ FINAL 03:46:00 | TSLA | O:395.50 H:395.55 L:395.55 C:395.57
✅ FINAL 03:46:00 | AMD | O:258.91 H:258.91 L:258.91 C:258.91
✅ FINAL 03:46:00 | NVDA | O:199.15 H:199.16 L:199.16 C:199.19
✅ FINAL 03:46:00 | AMZN | O:248.45 H:248.45 L:248.44 C:248.44
✅ FINAL 03:46:00 | BABA | O:137.51 H:137.53 L:137.52 C:137.53
✅ FINAL 03:46:00 | MSFT | O:418.16 H:418.16 L:418.11 C:418.19
✅ FINAL 03:47:00 | NVDA | O:199.19 H:199.17 L:199.17 C:199.19
✅ FINAL 03:47:00 | TSLA | O:395.57 H:395.60 L:395.57 C:395.57
✅ FINAL 03:47:00 | AMD | O:258.91 H:258.91 L:258.91 C:258.91
✅ FINAL 03:47:00 | AAPL | O:266.70 H:266.70 L:266.70 C:266.74
✅ FINAL 03:47:00 | GOOGL | O:338.69 H:338.69 L:338.68 C:338.66
✅ FINAL 03:47:00 | AMZN | O:248.44 H:248.43 L:248.42 C:248.43
✅ FINAL 03:47:00 | BABA | O:137.63 H:137.64 L:137.64 C:137.72
✅ FINAL 03:47:00 | META | O:674.64 H:674.64 L:674.64 C:674.64
✅ FINAL 03:47:00 | MSFT | O:418.19 H:418.40 L:418.31 C:418.32
✅ FINAL 03:47:00 | NFLX | O:107.93 H:107.94 L:107.94 C:107.94
✅ FINAL 03:48:00 | TSLA | O:395.55 H:395.63 L:395.57 C:395.72
✅ FINAL 03:48:00 | META | O:674.64 H:674.69 L:674.68 C:674.72
✅ FINAL 03:48:00 | AAPL | O:266.74 H:266.74 L:266.74 C:266.74
✅ FINAL 03:48:00 | BABA | O:137.72 H:137.67 L:137.62 C:137.62
✅ FINAL 03:48:00 | AMZN | O:248.43 H:248.44 L:248.43 C:248.44
✅ FINAL 03:48:00 | NFLX | O:107.94 H:107.98 L:107.94 C:107.93
✅ FINAL 03:48:00 | GOOGL | O:338.66 H:338.69 L:338.66 C:338.69
✅ FINAL 03:48:00 | MSFT | O:418.32 H:418.34 L:418.27 C:418.24
✅ FINAL 03:48:00 | NVDA | O:199.19 H:199.19 L:199.18 C:199.19
✅ FINAL 03:48:00 | AMD | O:258.88 H:258.88 L:258.88 C:258.91
✅ FINAL 03:49:00 | AAPL | O:266.74 H:266.75 L:266.75 C:266.75
✅ FINAL 03:49:00 | AMZN | O:248.44 H:248.44 L:248.44 C:248.44
✅ FINAL 03:49:00 | MSFT | O:418.31 H:418.27 L:418.27 C:418.26
✅ FINAL 03:49:00 | META | O:674.72 H:674.72 L:674.72 C:674.72
✅ FINAL 03:49:00 | TSLA | O:395.76 H:395.85 L:395.76 C:395.81
✅ FINAL 03:49:00 | BABA | O:137.56 H:137.56 L:137.53 C:137.53
✅ FINAL 03:49:00 | GOOGL | O:338.69 H:338.70 L:338.70 C:338.70
✅ FINAL 03:49:00 | NVDA | O:199.19 H:199.21 L:199.08 C:199.04
✅ FINAL 03:49:00 | NFLX | O:107.93 H:107.98 L:107.98 C:107.97
✅ FINAL 03:49:00 | AMD | O:258.95 H:258.95 L:258.95 C:258.95
✅ FINAL 03:50:00 | AAPL | O:266.75 H:266.75 L:266.75 C:266.75
✅ FINAL 03:50:00 | MSFT | O:418.24 H:418.28 L:418.27 C:418.30
✅ FINAL 03:50:00 | NVDA | O:199.11 H:199.13 L:199.11 C:199.13
✅ FINAL 03:50:00 | AMD | O:258.95 H:258.89 L:258.89 C:258.89
✅ FINAL 03:50:00 | BABA | O:137.53 H:137.56 L:137.53 C:137.56
✅ FINAL 03:50:00 | AMZN | O:248.45 H:248.45 L:248.45 C:248.45
✅ FINAL 03:50:00 | NFLX | O:107.97 H:107.97 L:107.97 C:107.97
✅ FINAL 03:50:00 | META | O:674.72 H:674.72 L:674.72 C:674.69
✅ FINAL 03:50:00 | TSLA | O:395.87 H:395.86 L:395.86 C:395.86
✅ FINAL 03:50:00 | GOOGL | O:338.69 H:338.70 L:338.70 C:338.70
✅ FINAL 03:51:00 | AAPL | O:266.75 H:266.74 L:266.72 C:266.74
✅ FINAL 03:51:00 | TSLA | O:395.91 H:395.79 L:395.72 C:395.77
✅ FINAL 03:51:00 | GOOGL | O:338.65 H:338.64 L:338.61 C:338.61
✅ FINAL 03:51:00 | META | O:674.69 H:674.69 L:674.65 C:674.65
✅ FINAL 03:51:00 | AMZN | O:248.45 H:248.45 L:248.45 C:248.45
✅ FINAL 03:51:00 | NVDA | O:199.13 H:199.13 L:199.12 C:199.10
✅ FINAL 03:51:00 | AMD | O:258.95 H:258.93 L:258.92 C:258.93
✅ FINAL 03:51:00 | BABA | O:137.56 H:137.58 L:137.58 C:137.56
✅ FINAL 03:51:00 | MSFT | O:418.30 H:418.27 L:418.25 C:418.24
✅ FINAL 03:51:00 | NFLX | O:107.97 H:107.95 L:107.94 C:107.94
✅ FINAL 03:52:00 | TSLA | O:395.77 H:395.75 L:395.71 C:395.64
✅ FINAL 03:52:00 | GOOGL | O:338.61 H:338.61 L:338.60 C:338.59
✅ FINAL 03:52:00 | AMZN | O:248.45 H:248.43 L:248.43 C:248.43
✅ FINAL 03:52:00 | BABA | O:137.59 H:137.61 L:137.59 C:137.59
✅ FINAL 03:52:00 | NVDA | O:199.10 H:199.10 L:199.10 C:199.08
✅ FINAL 03:52:00 | AMD | O:258.93 H:258.93 L:258.88 C:258.85
✅ FINAL 03:52:00 | MSFT | O:418.24 H:418.29 L:418.26 C:418.25
✅ FINAL 03:52:00 | AAPL | O:266.74 H:266.73 L:266.73 C:266.71
✅ FINAL 03:52:00 | NFLX | O:107.94 H:107.95 L:107.94 C:107.94
✅ FINAL 03:52:00 | META | O:674.65 H:674.56 L:674.56 C:674.55
✅ FINAL 03:53:00 | AAPL | O:266.71 H:266.71 L:266.71 C:266.74
✅ FINAL 03:53:00 | META | O:674.55 H:674.55 L:674.55 C:674.64
✅ FINAL 03:53:00 | BABA | O:137.59 H:137.50 L:137.50 C:137.44
✅ FINAL 03:53:00 | NFLX | O:107.94 H:107.97 L:107.97 C:107.97
✅ FINAL 03:53:00 | AMD | O:258.85 H:258.85 L:258.85 C:258.85
✅ FINAL 03:53:00 | TSLA | O:395.70 H:395.62 L:395.62 C:395.67
✅ FINAL 03:53:00 | AMZN | O:248.45 H:248.43 L:248.43 C:248.43
✅ FINAL 03:53:00 | NVDA | O:199.04 H:199.08 L:199.06 C:199.09
✅ FINAL 03:53:00 | MSFT | O:418.25 H:418.25 L:418.24 C:418.25
✅ FINAL 03:53:00 | GOOGL | O:338.60 H:338.60 L:338.60 C:338.60
✅ FINAL 03:54:00 | NVDA | O:199.07 H:199.12 L:199.07 C:199.12
✅ FINAL 03:54:00 | META | O:674.51 H:674.50 L:674.50 C:674.44
✅ FINAL 03:54:00 | AMZN | O:248.44 H:248.44 L:248.44 C:248.44
✅ FINAL 03:54:00 | TSLA | O:395.67 H:395.68 L:395.67 C:395.76
✅ FINAL 03:54:00 | NFLX | O:107.97 H:107.98 L:107.97 C:107.97
✅ FINAL 03:54:00 | AMD | O:258.85 H:258.85 L:258.85 C:258.87
✅ FINAL 03:54:00 | AAPL | O:266.70 H:266.70 L:266.70 C:266.70
✅ FINAL 03:54:00 | MSFT | O:418.24 H:418.23 L:418.23 C:418.23
✅ FINAL 03:54:00 | GOOGL | O:338.50 H:338.51 L:338.51 C:338.51
✅ FINAL 03:54:00 | BABA | O:137.44 H:137.50 L:137.44 C:137.52
✅ FINAL 03:55:00 | MSFT | O:418.24 H:418.24 L:418.24 C:418.24
✅ FINAL 03:55:00 | TSLA | O:395.80 H:395.81 L:395.80 C:395.84
✅ FINAL 03:55:00 | AMD | O:258.87 H:258.88 L:258.87 C:258.88
✅ FINAL 03:55:00 | NVDA | O:199.12 H:199.14 L:199.12 C:199.14
✅ FINAL 03:55:00 | BABA | O:137.52 H:137.50 L:137.50 C:137.54
✅ FINAL 03:55:00 | GOOGL | O:338.60 H:338.51 L:338.51 C:338.50
✅ FINAL 03:55:00 | AAPL | O:266.70 H:266.70 L:266.70 C:266.81
✅ FINAL 03:55:00 | META | O:674.44 H:674.59 L:674.59 C:674.59
✅ FINAL 03:55:00 | NFLX | O:107.97 H:107.97 L:107.97 C:107.94
✅ FINAL 03:56:00 | TSLA | O:395.85 H:395.82 L:395.76 C:395.78
✅ FINAL 03:56:00 | GOOGL | O:338.50 H:338.54 L:338.53 C:338.62
✅ FINAL 03:56:00 | NVDA | O:199.13 H:199.15 L:199.14 C:199.12
✅ FINAL 03:56:00 | META | O:674.59 H:674.59 L:674.59 C:674.59
✅ FINAL 03:56:00 | AAPL | O:266.81 H:266.81 L:266.81 C:266.75
✅ FINAL 03:56:00 | AMD | O:258.88 H:258.87 L:258.87 C:258.87
✅ FINAL 03:56:00 | MSFT | O:418.24 H:418.23 L:418.21 C:418.21
✅ FINAL 03:56:00 | NFLX | O:108.00 H:107.95 L:107.94 C:107.94
✅ FINAL 03:56:00 | BABA | O:137.51 H:137.51 L:137.51 C:137.51
✅ FINAL 03:57:00 | NVDA | O:199.12 H:199.13 L:199.12 C:199.14
✅ FINAL 03:57:00 | META | O:674.59 H:674.58 L:674.41 C:674.58
✅ FINAL 03:57:00 | AMZN | O:248.43 H:248.44 L:248.43 C:248.44
✅ FINAL 03:57:00 | TSLA | O:395.75 H:395.86 L:395.75 C:395.78
✅ FINAL 03:57:00 | NFLX | O:107.94 H:107.99 L:107.99 C:107.97
✅ FINAL 03:57:00 | GOOGL | O:338.62 H:338.62 L:338.62 C:338.61
✅ FINAL 03:57:00 | AAPL | O:266.75 H:266.78 L:266.75 C:266.78
✅ FINAL 03:57:00 | AMD | O:258.87 H:258.87 L:258.87 C:258.87
✅ FINAL 03:57:00 | MSFT | O:418.20 H:418.21 L:418.21 C:418.23
✅ FINAL 03:57:00 | BABA | O:137.48 H:137.51 L:137.51 C:137.51

root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ ps -p $(pgrep -f V15.py) -o etime,%cpu,rss,%mem
%cpu (avg cpu ratio), rss (actual RAM in KB), %mem (ram ratio)
ps -p $(pgrep -f V15.py) -o etime,%cpu,rss,%mem
error: process ID list syntax error

Usage:
 ps [options]

 Try 'ps --help <simple|list|output|threads|misc|all>'
  or 'ps --help <s|l|o|t|m|a>'
 for additional help text.

For more details see ps(1).
bash: syntax error near unexpected token `avg'
error: process ID list syntax error

Usage:
 ps [options]

 Try 'ps --help <simple|list|output|threads|misc|all>'
  or 'ps --help <s|l|o|t|m|a>'
 for additional help text.

For more details see ps(1).
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ ^C
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ ps -p $(pgrep -f production.py) -o etime,%cpu,rss,%mem
%cpu (avg cpu ratio), rss (actual RAM in KB), %mem (ram ratio)
ps -p $(pgrep -f production.py) -o etime,%cpu,rss,%mem
    ELAPSED %CPU   RSS %MEM
      15:59 14.1 206280  5.2
bash: syntax error near unexpected token `avg'
    ELAPSED %CPU   RSS %MEM
      15:59 14.1 206280  5.2
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ # 1. Grab initial bytes
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
Calculating network flow for 60 seconds (Using Python Math)...
------------------------------------------
VALUE:  14.63 MB used this minute
FLOW:   249.69 KB/s average speed
------------------------------------------
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ cat /proc/net/dev | grep eth0
  eth0: 311007244   66054    0    0    0     0          0         0  5059557   38227    0    1    0     0       0          0
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ ps -p $(pgrep -f V15.py) -o etime,time,pcpu
error: process ID list syntax error

Usage:
 ps [options]

 Try 'ps --help <simple|list|output|threads|misc|all>'
  or 'ps --help <s|l|o|t|m|a>'
 for additional help text.

For more details see ps(1).
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ ps -p $(pgrep -f production.py) -o etime,time,pcpu
    ELAPSED     TIME %CPU
      18:42 00:02:39 14.2
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ top -b -d 5 -p $(pgrep -f production.py) | grep python3
^C
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ top -p $(pgrep -f production.py)
top - 04:05:28 up  9:07,  0 users,  load average: 0.09, 0.24, 0.20
Tasks:   1 total,   0 running,   1 sleeping,   0 stopped,   0 zombie
%Cpu(s): 10.7 us,  0.3 sy,  0.0 ni, 89.0 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
MiB Mem :   3832.0 total,   1352.8 free,   1029.1 used,   1619.3 buff/cache
MiB Swap:      0.0 total,      0.0 free,      0.0 used.   2802.8 avail Mem

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND                                                             
    318 root      20   0 1299528 216788  19320 S  15.9   5.5   2:48.20 python
root@kpd-yfe-yahoo-finance-extractor-kub-tst-dta-kns-6f74d46b64q9xnp ():/kns-dta-data-kubernetes-namespace-tst-tst-kct/yfs$ 