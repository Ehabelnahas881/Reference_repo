import asyncio, time, pytz, os, random, re, json, logging
from datetime import datetime
from flask import Flask, jsonify
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

# --- LOGGER CONFIGURATION (Exact Format Fix) ---
logging.basicConfig(
    level=logging.INFO,
    # This matches your requested date and separator format: 2026-03-31 21:54:30,217 - 
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler("market_data.log"), 
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Scraper")

UTC = pytz.utc
ASSETS = [{"ticker": "TSLA"}, {"ticker": "AAPL"}, {"ticker": "NVDA"}]

def get_market_session_config():
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    # Using your specific timeframe logic
    if 8.0 <= curr < 13.5: return ["qsp-pre-price", "qsp-post-price", "qsp-price"], "Pre-Market"
    elif 13.5 <= curr < 20.0: return ["qsp-price"], "Regular"
    elif 20.0 <= curr <= 24.0: return ["qsp-post-price", "qsp-price"], "Post-Market"
    else: return ["qsp-overnight-price", "qsp-post-price", "qsp-price"], "Overnight"

class StealthOHLCWorker:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://finance.yahoo.com/"
        }

    async def perform_digital_click(self, session):
        """Bypasses German Privacy Wall"""
        session.cookies.set("CONSENT", "YES+cb.20240116-07-p0.en+FX+999", domain=".yahoo.com")
        try:
            resp = await session.get("https://finance.yahoo.com/", headers=self.headers, impersonate="chrome124", timeout=15)
            return resp.status_code == 200
        except: return False

    async def fetch_price(self, session, ticker):
        """Scrapes targeted ID with fallback"""
        try:
            url = f"https://finance.yahoo.com/quote/{ticker}/"
            resp = await session.get(url, headers=self.headers, impersonate="chrome124", timeout=10)
            if resp.status_code != 200: return None

            soup = BeautifulSoup(resp.text, 'html.parser')
            target_ids, _ = get_market_session_config()
            
            for tid in target_ids:
                el = soup.find(attrs={"data-testid": tid})
                if el and el.text:
                    try: return float(el.text.replace(',', ''))
                    except: continue
            
            # Regex Fallback
            match = re.search(r'"regularMarketPrice":\{"raw":([\d\.]+)', resp.text)
            if match: return float(match.group(1))
        except: pass
        return None

    async def process_asset(self, session, asset):
        ticker = asset['ticker']
        # Logger info for startup
        logger.info(f"Worker for {ticker} initialized.")

        while True:
            try:
                # Sync to top of next minute
                now = datetime.now(UTC)
                await asyncio.sleep(60 - now.second - (now.microsecond / 1000000) + 0.1)
                
                # Market TS (HH:MM:SS)
                market_ts = datetime.now(UTC).strftime('%H:%M:00')
                _, session_name = get_market_session_config()
                prices = []
                
                # Aggregation Loop (6 hits per minute)
                for _ in range(6):
                    p = await self.fetch_price(session, ticker)
                    if p: prices.append(p)
                    await asyncio.sleep(random.uniform(7.5, 9.2))
                
                if prices:
                    o, h, l, c = prices[0], max(prices), min(prices), prices[-1]
                    
                    # EXACT FORMATTED OUTPUT:
                    # [Regular] O:372.19 | H:372.27 | L:371.50 | C:371.64 | TS:19:52:00
                    logger.info(f"[{session_name}] {ticker} O:{o:.2f} | H:{h:.2f} | L:{l:.2f} | C:{c:.2f} | TS:{market_ts}")
                else:
                    logger.info(f"[MISSING] {ticker} - No data captured for TS:{market_ts}")

            except Exception as e:
                logger.info(f"[ERROR] {ticker} loop crash: {e}. Restarting in 30s...")
                await asyncio.sleep(30)

async def main_engine():
    async with AsyncSession() as session:
        engine = StealthOHLCWorker()
        while not await engine.perform_digital_click(session):
            await asyncio.sleep(60)
        
        tasks = [engine.process_asset(session, asset) for asset in ASSETS]
        await asyncio.gather(*tasks)

# --- FLASK ---
app = Flask(__name__)
@app.route("/")
def status(): return jsonify({"status": "active"}), 200

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=3989, use_reloader=False), daemon=True).start()
    asyncio.run(main_engine())