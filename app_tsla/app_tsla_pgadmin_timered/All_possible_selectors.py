cat << 'EOF' > selectors.py
    import time
    import os
    from curl_cffi import requests
    from bs4 import BeautifulSoup

    TICKER = "TSLA"
    URL = f"https://finance.yahoo.com/quote/{TICKER}/?p={TICKER}"

    print(f" Windows Home PC Mode: Testing All Selectors for {TICKER}...\n")

    while True:
        try:
            # ملاحظة: إذا استمر خطأ curl 6، تأكد من إغلاق أي VPN
            # سنحاول الاتصال مع مهلة أطول وتجاهل التحقق من الشهادات لضمان العبور
            session = requests.Session()
            r = session.get(
                URL, 
                impersonate="chrome120", 
                timeout=30, 
                verify=False
            )
            
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                print(f"\n---  Loop: {time.strftime('%H:%M:%S')} ---")

                # فحص كل الاستراتيجيات الممكنة
                strategies = {
                    "Method 1 (data-testid='qsp-price')": lambda: soup.find("span", {"data-testid": "qsp-price"}),
                    "Method 2 (Section Hierarchy)": lambda: soup.select_one('section[data-testid="price-statistic"] span'),
                    "Method 3 (Class 'price base')": lambda: soup.select_one("span.price.base"),
                    "Method 4 (Fin-Streamer)": lambda: soup.find("fin-streamer", {"data-symbol": TICKER, "data-field": "regularMarketPrice"}),
                    "Method 5 (Specific Class yf-1ommk34)": lambda: soup.select_one("span.yf-1ommk34"),
                    "Method 6 (Regex Search)": lambda: soup.find(string=lambda x: x and "." in x and x.strip().replace('.','').replace(',','').isdigit() and len(x.strip()) < 8)
                }

                for name, func in strategies.items():
                    try:
                        tag = func()
                        if tag:
                            # تنظيف النص المستخرج
                            text = tag.get_text() if hasattr(tag, 'get_text') else str(tag)
                            val = text.replace(',', '').strip()
                            print(f"    {name}: {val}")
                        else:
                            print(f"    {name}: Not Found")
                    except:
                        print(f"    {name}: Parse Error")

                print("-" * 40)
            else:
                print(f" FAIL: HTTP {r.status_code} - Website might be blocking you.")

        except Exception as e:
            # إذا استمر الخطأ، سنطبع رسالة تشخيصية واضحة
            err_msg = str(e)
            if "curl: (6)" in err_msg:
                print(f" DNS ERROR: Your PC cannot find 'finance.yahoo.com'.")
                print(" Fix: Try opening the link in Chrome first. If it works, restart your VS Code/Terminal.")
            else:
                print(f" ERROR: {err_msg[:60]}")

        # انتظر 15 ثانية قبل المحاولة التالية
        time.sleep(15) EOF
