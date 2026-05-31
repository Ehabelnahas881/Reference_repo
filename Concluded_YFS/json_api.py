import requests
import json
import time
from datetime import datetime

def get_market_data(ticker="TSLA"):
    ### The includePrePost=true flag ensures we get all three sessions
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d&includePrePost=true"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.yahoo.com/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        meta = result['meta']
        
        # Session boundaries (Unix timestamps)
        sessions = meta['currentTradingPeriod']
        pre_start = sessions['pre']['start']
        reg_start = sessions['regular']['start']
        post_start = sessions['post']['start']
        post_end = sessions['post']['end']

        all_records = []

        for i, ts in enumerate(timestamps):
            # Determine session type
            if ts < reg_start:
                session_type = "PRE"
            elif ts < post_start:
                session_type = "REGULAR"
            else:
                session_type = "POST"

            # Skip null values (common in low-liquidity pre/post)
            if quote['close'][i] is None:
                continue

            record = {
                "Time": datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'),
                "Session": session_type,
                "Open": round(quote['open'][i], 2),
                "High": round(quote['high'][i], 2),
                "Low": round(quote['low'][i], 2),
                "Close": round(quote['close'][i], 2),
                "Volume": quote['volume'][i]
            }
            all_records.append(record)

        # Save to file
        output = {str(time.time()): {"data_points": all_records}}
        with open("QWERTY_RECAP.json", "a") as f:
            f.write(json.dumps(output) + "\n")
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Saved {len(all_records)} total points for {ticker}")

    except Exception as e:
        print(f"Error fetching data: {e}")

if __name__ == "__main__":
    while True:
        get_market_data("TSLA")
        time.sleep(60) # 1-minute interval is sufficient for 1m data
