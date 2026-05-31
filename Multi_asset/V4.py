import asyncio, time, pytz, os, random, re, json, uuid
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
UTC = pytz.utc
# Add as many as you need; Async handles them easily
ASSETS = [
    {"ticker": "TSLA"},
    {"ticker": "AAPL"},
    {"ticker": "NVDA"}
]

def get_market_session_config():
    """Returns the priority list of IDs to check based on UTC time"""
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    
    # Logic based on your specific market windows
    if 8.0 <= curr < 13.5: 
        return ["qsp-pre-price", "qsp-post-price", "qsp-price"], "Pre-Market"
    elif 13.5 <= curr < 20.0: 
        return ["qsp-price"], "Regular"
    elif 20.0 <= curr <= 24.0: 
        return ["qsp-post-price", "qsp-price"], "Post-Market"
    else: 
        return ["qsp-overnight-price", "qsp-post-price", "qsp-price"], "Overnight"

class StealthOHLCWorker:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com/"
        }

    async def perform_digital_click(self, session):
        """Injects the 'Permission Slip' to bypass German Privacy Walls"""
        print("[SYSTEM] Establishing Session Identity...", flush=True)
        # Bypasses 'Ihre Datenschutzeinstellungen' instantly
        session.cookies.set("CONSENT", "YES+cb.20240116-07-p0.en+FX+999", domain=".yahoo.com")
        try:
            resp = await session.get("https://finance.yahoo.com/", headers=self.headers, impersonate="chrome124")
            print(f"[SUCCESS] Digital Click Bypass Active. Status: {resp.status_code}", flush=True)
            return True
        except Exception as e:
            print(f"[ERROR] Connection failed: {e}", flush=True)
            return False

    async def fetch_price(self, session, ticker):
        """The core scraper: Checks your specific ID priority list"""
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}/"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=10)
            
            if "consent.yahoo.com" in resp.url:
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')
            target_ids, _ = get_market_session_config()
            
            # 1. Targeted ID Check (Your preferred logic)
            for tid in target_ids:
                el = soup.find(attrs={"data-testid": tid})
                if el and el.text:
                    try:
                        val = float(el.text.replace(',', ''))
                        if val > 0: return val
                    except ValueError: continue
            
            # 2. JSON Fallback (Backup if HTML structure shifts)
            match = re.search(r'"regularMarketPrice":\{"raw":([\d\.]+)', resp.text)
            if match: return float(match.group(1))
                
        except Exception:
            pass
        return None

    async def process_asset(self, session, asset):
        """Independent 'Tab' worker for each asset"""
        ticker = asset['ticker']
        print(f"[LAUNCH] {ticker} Monitoring Active.", flush=True)

        while True:
            # Sync to the TOP of the next minute
            now = datetime.now(UTC)
            seconds_to_wait = 60 - now.second - (now.microsecond / 1000000)
            await asyncio.sleep(seconds_to_wait + 0.05)
            
            ts_label = datetime.now(UTC).strftime('%H:%M')
            _, session_name = get_market_session_config()
            prices = []
            
            # Collect 6 samples over the current minute
            for _ in range(6):
                p = await self.fetch_price(session, ticker)
                if p: prices.append(p)
                # Jitter: Staggering hits to look like a human browsing
                await asyncio.sleep(random.uniform(7.5, 9.5))
            
            if prices:
                o, h, l, c = prices[0], max(prices), min(prices), prices[-1]
                print(f"[{ts_label}] {ticker} | O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f} | ({session_name})", flush=True)
            else:
                print(f"[WARN] {ticker} - No data received for {ts_label}. Session might be stale.", flush=True)

async def main_engine():
    # One session handles all 'Tabs' = One IP, one identity, low detection
    async with AsyncSession() as session:
        engine = StealthOHLCWorker()
        
        # Initial click/cookie injection
        await engine.perform_digital_click(session)

        # Launch all assets concurrently
        tasks = [engine.process_asset(session, asset) for asset in ASSETS]
        await asyncio.gather(*tasks)

# --- FLASK INTERFACE ---
app = Flask(__name__)
@app.route("/")
def status(): return jsonify({"status": "active", "time_utc": datetime.now(UTC).isoformat()}), 200

if __name__ == "__main__":
    import threading
    # Run API on 3989 to satisfy Kubernetes/Pod health checks
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=3989, use_reloader=False), daemon=True).start()
    
    try:
        asyncio.run(main_engine())
    except KeyboardInterrupt:
        print("\n[STOP] Scraper shut down manually.")










