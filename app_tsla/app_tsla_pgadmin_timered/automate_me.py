import subprocess
import time
import sys
import os

TARGET_FILE = "newlogic.py" 

print(f"🛡️ Scraper Guardian Active. Monitoring: {TARGET_FILE}")

while True:
    print(f"\n--- Starting New Sync: {time.strftime('%H:%M:%S')} ---")
    
    try:
        # Runs the scraper logic as a separate process
        subprocess.run([sys.executable, TARGET_FILE], check=False)
    except Exception as e:
        print(f"⚠️ Guardian caught a system error: {e}")

    print("😴 Waiting 60 seconds for next update...")
    time.sleep(30)