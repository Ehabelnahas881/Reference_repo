import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
import time
import json
import random

def scrape_tsla_hover_data():
    options = uc.ChromeOptions()
    # options.add_argument("--headless") # Headless can sometimes break canvas hovers
    
    # Use version 144 as established before
    driver = uc.Chrome(options=options, version_main=144)
    
    try:
        driver.get("https://finance.yahoo.com/quote/TSLA/")
        wait = WebDriverWait(driver, 20)

        # 1. Handle Cookie/Consent wall (essential for hover to work)
        try:
            consent_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@name='agree'] | //button[contains(@class, 'primary')]")))
            consent_btn.click()
            print("Cleared consent wall.")
        except:
            pass

        # 2. Locate Chart Area
        # Using the data-testid from your example for precision
        chart_container = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "section[data-testid='chart-container']")))
        driver.execute_script("arguments[0].scrollIntoView();", chart_container)
        time.sleep(5) # Delay for rendering

        chart_area = driver.find_element(By.CSS_SELECTOR, ".ciq-chart-area")
        width = chart_area.size['width']
        
        data_points = []
        actions = ActionChains(driver)

        # 3. Simulate Mouse Hover Steps
        # We move across the chart width to trigger the hu-tooltip table
        print(f"Starting hover sequence across {width}px...")
        
        # Taking 10 samples across the chart
        step_size = width // 10 
        for x_offset in range(10, width - 10, step_size):
            try:
                # Move mouse to the x position
                actions.move_to_element_with_offset(chart_area, x_offset, 100).perform()
                time.sleep(1.5) # Wait for tooltip to update

                # Scrape the table that appears on hover
                tooltip = driver.find_element(By.CSS_SELECTOR, "table.hu-tooltip")
                rows = tooltip.find_elements(By.TAG_NAME, "tr")
                
                point_data = {}
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) == 2:
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        point_data[key] = value
                
                if point_data:
                    data_points.append(point_data)
                    print(f"Captured: {point_data.get('Date', 'N/A')} - Close: {point_data.get('Close', 'N/A')}")
            except Exception as e:
                continue

        # 4. Format into your specific JSON structure
        final_output = {
            str(time.time()): {
                "data_points": data_points,
                "ranges": []
            }
        }

        # Save to QWERTY.json
        with open("QWERTY.json", "a") as f:
            f.write(json.dumps(final_output) + "\n")
            print("\nSuccessfully saved data to QWERTY.json")

    except Exception as e:
        print(f"Main Error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    # Run once for testing, can be wrapped in while True:
    scrape_tsla_hover_data()