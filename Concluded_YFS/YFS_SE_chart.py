import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import time, json, random, os, pytz, re
from datetime import datetime

CHROME_VERSION = 146
TARGET_URL = "https://finance.yahoo.com/quote/TSLA/"
JSON_FILE = "CHART_ULTRA_OHLC.jsonl"
NY_TZ = pytz.timezone('America/New_York')

def get_session_name():
    now = datetime.now(NY_TZ)
    h_m = now.hour + now.minute / 60.0
    day = now.weekday()
    if day >= 5: return "WEEKEND"
    if 4.0 <= h_m < 9.5: return "PRE_MARKET"
    if 9.5 <= h_m < 16.0: return "REGULAR"
    if 16.0 <= h_m < 20.0: return "POST_MARKET"
    return "OVERNIGHT"

def init_driver():
    # STABILITY
    options = uc.ChromeOptions()
    options.add_argument("--headless") 
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-features=CalculateNativeWinOcclusion")
    options.page_load_strategy = 'eager'
    driver = uc.Chrome(version_main=CHROME_VERSION, options=options)
    driver.set_page_load_timeout(30)
    return driver

def scrape_ohlc_from_chart(driver):
    try:
        wait = WebDriverWait(driver, 25)
        
        chart_container = wait.until(EC.presence_of_element_located((
            By.CSS_SELECTOR, "section[data-testid='chart-container'], .chart-container, #render-target-default"
        )))
        
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", chart_container)
        time.sleep(5)

        # Searcher
        canvases = driver.find_elements(By.TAG_NAME, "canvas")
        if not canvases:
            canvases = driver.find_elements(By.CSS_SELECTOR, ".drawing-canvas, .ciq-chart-area canvas")
        
        if not canvases: return None
        
        # Page initlization
        canvas = max(canvases, key=lambda x: x.size['width'] * x.size['height'])
        rect = canvas.rect
        
        # CLICKS
        actions = ActionChains(driver)
        actions.move_to_element_with_offset(canvas, 10, 10).click().perform()
        time.sleep(1)
        
        # cursor movements 
        actions.move_to_element_with_offset(canvas, int(rect['width'] * 0.98), int(rect['height'] * 0.4)).perform()
        time.sleep(3)

        # chart search for tooltip text (try multiple selectors to be robust)
        raw_text = driver.execute_script("""
            let selectors = ['.hu-tooltip', '.chart-tooltip', '.stx-tooltip', 'div[class*="tooltip"]'];
            for (let s of selectors) {
                let tt = document.querySelector(s);
                if (tt && tt.innerText.length > 5) return tt.innerText;
            }
            return "";
        """)

        if not raw_text: return None

        ohlc = {}
        patterns = {
            "open": r"Open[:\s]+([\d\.,]+)",
            "high": r"High[:\s]+([\d\.,]+)",
            "low": r"Low[:\s]+([\d\.,]+)",
            "close": r"Close[:\s]+([\d\.,]+)",
            "volume": r"Vol(?:ume)?[:\s]+([\d\.,MK]+)"
        }
        
        text_clean = raw_text.replace(',', '')
        for key, pat in patterns.items():
            match = re.search(pat, text_clean, re.IGNORECASE)
            if match:
                val = match.group(1).upper()
                if 'M' in val: ohlc[key] = float(val.replace('M', '')) * 1e6
                elif 'K' in val: ohlc[key] = float(val.replace('K', '')) * 1e3
                else: ohlc[key] = float(val)
        
        return ohlc
    except Exception as e:
        print(f" Chart Detail: {str(e).splitlines()[0]}")
        return None

def main():
    print(" FOREVER BACKGROUND CHART RECORDER 💎")
    driver = init_driver()
    
    while True:
        try:
            session = get_session_name()
            now_ny = datetime.now(NY_TZ)
            print(f"\n [{now_ny.strftime('%H:%M:%S')}] Refreshing: {TARGET_URL}")
            
            driver.get(TARGET_URL)
            time.sleep(7) 

            data = scrape_ohlc_from_chart(driver)
            
            if data and "close" in data:
                record = {"dt": now_ny.strftime('%Y-%m-%d %H:%M:%S'), "session": session, "symbol": "TSLA", **data}
                with open(JSON_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
                print(f" SAVED: {data}")
            else:
                print(" Data capture failed. Retrying...")
                driver.save_screenshot("background_debug.png")

            time.sleep(60)

        except Exception as e:
            print(f" Restarting Driver... {e}")
            try: driver.quit()
            except: pass
            time.sleep(5)
            driver = init_driver()

if __name__ == "__main__":
    main()
