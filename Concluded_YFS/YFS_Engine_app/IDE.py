import threading
import time
import random
import uuid
import logging
import psycopg2
# استبدال requests بـ curl_cffi
from curl_cffi import requests 
import pytz
import os
import re
import json
from bs4 import BeautifulSoup, SoupStrainer
from datetime import datetime, timedelta
from psycopg2.extras import execute_values
from logging.handlers import TimedRotatingFileHandler
import settings

# --- CONFIGURATION ---
UTC = pytz.utc
# كوكيز محدثة وأكثر استقراراً
BASE_COOKIES = {
    "A3": "d=AQABBAE1qmkcEAf_Tt8_pPFYFEgABCAHYsWngAeANylMA9qMCAAdATWqac_pPFY&S=AQAAAhpgeBDsfqp1GQXTrpvdhiQ",
    "CONSENT": "YES+cb.20240116-07-p0.en+FX+999",
}

# بصمات متصفحات حقيقية متوافقة مع curl-cffi
IMPERSONATE_TYPES = ["chrome110", "chrome116", "chrome120", "edge101", "safari15"]

def get_market_session_config(ticker=""):
    now_utc = datetime.now(UTC)
    curr = now_utc.hour + (now_utc.minute / 60)
    is_weekend = now_utc.weekday() >= 5 

    if any(x in ticker.upper() for x in ["BTC", "USD", "ETH"]):
        return "qsp-price", "Regular", 3
    if is_weekend:
        return "qsp-price", "Weekend-Test", 4

    if 0.0 <= curr < 8.0: 
        return "qsp-overnight-price", "Overnight", 1
    elif 8.0 <= curr < 13.5: 
        return "qsp-post-price", "Pre-Market", 2 
    elif 13.5 <= curr < 20.0: 
        return "qsp-price", "Regular", 3
    else: 
        return "qsp-post-price", "Post-Market", 4

class DataWorker:
    def __init__(self, ticker, table_name):
        self.ticker = ticker
        self.table_name = table_name
        self.logger = self.create_logger()
        
        # إعداد جلسة curl_cffi مع انتحال شخصية عشوائي
        self.browser_type = random.choice(IMPERSONATE_TYPES)
        self.session = requests.Session(impersonate=self.browser_type)
        self.session.cookies.update(BASE_COOKIES)
        
        self.conn = None
        self.buffer = []
        self.connect_db()

    def create_logger(self):
        if not os.path.exists('logs'): os.makedirs('logs')
        logger = logging.getLogger(f"{self.ticker}_Scraper")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = TimedRotatingFileHandler(f"logs/{self.ticker}.log", when="midnight", interval=1, backupCount=1)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(handler)
        return logger

    def connect_db(self):
        try:
            if self.conn:
                try: self.conn.close()
                except: pass
            self.conn = psycopg2.connect(
                host=settings.DATABASE_HOST, user=settings.USER,
                password=settings.PASSWORD, database=settings.DBNAME,
                port=settings.DATABASE_PORT, connect_timeout=10
            )
            self.conn.autocommit = False 
            return True
        except Exception as e:
            self.logger.error(f"DB Error: {e}")
            return False

    def fetch_price(self):
        target_id, s_name, _ = get_market_session_config(self.ticker)
        try:
            # تحديث الجلسة بمتصفح جديد عشوائياً لكسر نمط البوت
            if random.random() > 0.8:
                self.session = requests.Session(impersonate=random.choice(IMPERSONATE_TYPES))
                self.session.cookies.update(BASE_COOKIES)

            url = f"https://finance.yahoo.com/quote/{self.ticker}/?p={self.ticker}&ts={time.time()}"
            
            # إرسال الطلب عبر محرك curl الأصلي
            resp = self.session.get(url, timeout=15)
            
            if resp.status_code != 200: 
                self.logger.error(f"Fetch failed: HTTP {resp.status_code}")
                return None

            # استراتيجية هجينة: جلب البيانات من JSON الصفحة أولاً (أدق) ثم BS4 كبديل
            # البحث عن السعر داخل كود JavaScript الخاص بياهو
            price_match = re.search(r'"' + target_id + r'":{"raw":([\d\.]+)', resp.text)
            if price_match:
                return float(price_match.group(1))

            # Fallback لـ BeautifulSoup
            strainer = SoupStrainer(attrs={"data-testid": target_id})
            soup = BeautifulSoup(resp.text, 'lxml', parse_only=strainer)
            el = soup.find(attrs={"data-testid": target_id})
            
            if not el:
                el = soup.find(attrs={"data-testid": "qsp-price"})
            
            return float(el.text.replace(',', '').strip()) if el and el.text else None
            
        except Exception as e:
            self.logger.error(f"Fetch error: {e}")
            return None

    def flush_buffer(self):
        if not self.buffer: return
        try:
            if not self.conn or self.conn.closed:
                if not self.connect_db(): return
            
            query = f'INSERT INTO {self.table_name} ("one_min_timeseries_date", "one_min_timeseries_timestamp", "one_min_timeseries_OP_open_price", "one_min_timeseries_HP_high_price", "one_min_timeseries_LP_low_price", "one_min_timeseries_CP_close_price", "one_min_timeseries_PK", "one_min_timeseries_UUID", "one_min_timeseries_creation_date_time", "one_min_timeseries_activity_status", "one_min_timeseries_financial_data_source_PK", "one_min_timeseries_ID") VALUES %s'
            data_to_save = []
            for rec in self.buffer:
                pk = int(time.time()*1000) + random.randint(0,999)
                data_to_save.append((rec['ts'].date(), rec['ts'], rec['o'], rec['h'], rec['l'], rec['c'], pk, str(uuid.uuid4()), datetime.now(UTC), 1, 1, rec['s_id']))
            
            with self.conn.cursor() as cur:
                execute_values(cur, query, data_to_save)
                self.conn.commit()
            self.logger.info(f"[{self.ticker}] FLUSHED {len(self.buffer)} record(s) to RDS.")
            self.buffer.clear()
        except Exception as e:
            if self.conn: self.conn.rollback()
            self.logger.error(f"Flush Failed: {e}")

    def run(self):
        self.logger.info(f"Worker Online (curl-cffi Mode) for {self.ticker}")
        next_min = (datetime.now(UTC) + timedelta(minutes=1)).replace(second=0, microsecond=0)
        while True:
            try:
                wait = (next_min - datetime.now(UTC)).total_seconds()
                if wait > 0: time.sleep(wait)
                curr_ts = next_min
                next_min += timedelta(minutes=1)
                
                _, s_name, s_id = get_market_session_config(self.ticker)
                
                m_open = self.fetch_price()
                if m_open is None: continue

                m_high, m_low, m_close = m_open, m_open, m_open
                # تقليل عدد الطلبات قليلاً لتجنب كشف AWS
                for _ in range(5): 
                    time.sleep(random.uniform(8.0, 10.0)) 
                    tick = self.fetch_price()
                    if tick:
                        m_high = max(m_high, tick)
                        m_low = min(m_low, tick)
                        m_close = tick

                self.buffer.append({'ts': curr_ts, 'o': m_open, 'h': m_high, 'l': m_low, 'c': m_close, 's_id': s_id})
                self.logger.info(f"[{self.ticker}] {s_name} Buffered: {curr_ts.strftime('%H:%M')}")
                
                if len(self.buffer) >= 1:
                    self.flush_buffer()
                    
            except Exception as e:
                self.logger.error(f"Loop Error: {e}")
                time.sleep(5)

# دالة التكامل مع المشروع الضخم
def resolve_IDE(obj, info, financial_asset_list, environment_pk):
    asset_mapping = {
        1: ("TSLA", '"TEST_TSLA"."one_min_timeseries_data"')
    }
    def _start_background():
        for asset_id in financial_asset_list:
            if asset_id in asset_mapping:
                ticker, table = asset_mapping[asset_id]
                worker = DataWorker(ticker, table)
                # تشغيل كخيط منفصل لعدم تعطيل المشروع الرئيسي
                threading.Thread(target=worker.run, daemon=True).start()
    
    threading.Thread(target=_start_background, daemon=True).start()
    return "Scrapers Started Successfully"
