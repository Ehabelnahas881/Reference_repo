import time, pytz, os, random, uuid, logging, psycopg2, threading, re, json
from datetime import datetime
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from curl_cffi import requests
from bs4 import BeautifulSoup
from psycopg2.extras import execute_values

UTC = pytz.utc
DB_CONFIG = {
   "host": "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com", 
    "user": "ehab.elnahas", "password": "test", "database": "dyDATA_new", "port": "5432"
}

# FRESH GERMAN COOKIES AS PER THE POD(DATA CENTER) IS LAUNCHED FROM GERMANY
MY_COOKIES = {
    "A1": "d=AQABBNnKuGkCEMIvFhTud_rbWqXe4XYZYlQFEgABCAEZumnjaeANyiMA9qMCAAcI1Mq4aXfQzd0&S=AQAAAi0PR7nmfDoGBULUrreTsvU",
    "A1S": "d=AQABBNnKuGkCEMIvFhTud_rbWqXe4XYZYlQFEgABCAEZumnjaeANyiMA9qMCAAcI1Mq4aXfQzd0&S=AQAAAi0PR7nmfDoGBULUrreTsvU",
    "A3": "d=AQABBNnKuGkCEMIvFhTud_rbWqXe4XYZYlQFEgABCAEZumnjaeANyiMA9qMCAAcI1Mq4aXfQzd0&S=AQAAAi0PR7nmfDoGBULUrreTsvU",
    "GUC": "AQABCAFpuhlp40IlyAVs&s=AQAAAAWyT4T7&g=abjK4w",
    "CONSENT": "YES+cb.20240116-07-p0.en+FX+999"
}

def get_market_session_config():
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    if 1.0 <= curr < 9.5: return "qsp-overnight-price", "Overnight", 1
    elif 9.5 <= curr < 14.5: return "qsp-post-price", "Pre-Market", 2
    elif 14.5 <= curr < 21.0: return "qsp-post-price", "Regular", 3
    else: return "qsp-post-price", "Post-Market", 4

class DataWorker:
    def __init__(self, ticker, table_name):
        self.ticker, self.table_name = ticker, table_name
        self.session = requests.Session(impersonate="chrome124")
        self.session.cookies.update(MY_COOKIES)
        self.buffer = []
        self.conn = None

    def fetch_price(self):
        try:
            url = f"https://finance.yahoo.com/quote/{self.ticker}/"
            resp = self.session.get(url, timeout=15)
            if "Ihre Datenschutzeinstellungen" in resp.text:
                print("Cookie rejected by Yahoo Germany.")
                return None
            
            # JSON Strategy
            match = re.search(r'root\.App\.main\s*=\s*(\{.*?\});', resp.text)
            if match:
                data = json.loads(match.group(1))
                store = data['context']['dispatcher']['stores']['QuoteSummaryStore']['price']
                for k in ['overnightPrice', 'postMarketPrice', 'preMarketPrice', 'regularMarketPrice']:
                    val = store.get(k, {}).get('raw')
                    if val: return float(val)
            
            # BS4 SEARCH & FETCH
            soup = BeautifulSoup(resp.text, 'html.parser')
            tid, _, _ = get_market_session_config()
            el = soup.find(attrs={"data-testid": tid})
            if el: return float(el.text.replace(',', ''))
        except Exception as e: print(f"Fetch Error: {e}")
        return None

    def run(self):
        print(f"Scraper thread started for {self.ticker}")
        while True:
            now = datetime.now(UTC)
            time.sleep(60 - now.second - (now.microsecond / 1000000) + 0.5)
            ts = datetime.now(UTC).replace(second=0, microsecond=0)
            _, _, sid = get_market_session_config()
            
            price = self.fetch_price()
            if not price: continue
            
            # Sample for 1 minute (RANGE IS DYNAMIC HOWEVER I PREFER 5LOOPS NOT TO BE DETECTED AS BOT)
            h, l, c = price, price, price
            for _ in range(5):
                #JITTER TO AVOID BOT DETECTION AND IT IS IMPORTANT LIKEWISE CURL 
                time.sleep(random.uniform(7,9))
                t = self.fetch_price()
                if t: h, l, c = max(h, t), min(l, t), t
            # Quick DB Flush MIN BY MINUTE to avoid data loss AND DB OVERHELMING(flush maybe every 5 records=every 5 minutes to reduce DB overhelming by the way db conn failure)
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                with conn.cursor() as cur:
                    pk = int(time.time()*1000) + random.randint(0,999)
                    cur.execute(f'INSERT INTO {self.table_name} ("one_min_timeseries_date", "one_min_timeseries_timestamp", "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price", "one_min_timeseries_PK", "one_min_timeseries_UUID", "one_min_timeseries_creation_date_time", "one_min_timeseries_activity_status", "one_min_timeseries_financial_data_source_PK", "one_min_timeseries_ID") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', (ts.date(), ts, price, h, l, c, pk, str(uuid.uuid4()), datetime.now(UTC), 1, 1, sid))
                    conn.commit()
                conn.close()
                print(f"Flushed {self.ticker} for {ts}")
            except Exception as e: print(f"DB Error: {e}")

type_defs = "type Query { status: String }"
query = ObjectType("Query")
@query.field("status")
def resolve_status(*_): return "Online"
schema = make_executable_schema(type_defs, [query])
app = Flask(__name__)

@app.route("/graphql", methods=["POST"])
def graphql_server():
    success, result = graphql_sync(schema, request.get_json())
    return jsonify(result), 200

if __name__ == "__main__":
    # Start PORT , CALL SCRAPPER
    threading.Thread(target=DataWorker("TSLA", '"TEST_TSLA"."one_min_timeseries_data"').run, daemon=True).start()
    # Run Flask on all interfaces
    app.run(host="0.0.0.0", port=3989)
