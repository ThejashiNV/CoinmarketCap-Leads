from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

url = "https://coinmarketcap.com/new/"

driver.get(url)

time.sleep(10)

coins = []

rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")

project_links = []

for row in rows[:15]:

    try:
        link_element = row.find_element(By.CSS_SELECTOR, "a[href*='/currencies/']")

        project_link = link_element.get_attribute("href")

        if project_link not in project_links:
            project_links.append(project_link)

    except:
        pass

print("Collected Project Links:")
print(project_links)

for link in project_links:

    try:
        driver.get(link)

        time.sleep(5)

        project_name = ""
        website = ""
        telegram = ""
        twitter = ""

        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            project_name = h1.text.split("\n")[0]
        except:
            pass

        all_links = driver.find_elements(By.TAG_NAME, "a")

        for item in all_links:

            href = item.get_attribute("href")

            if href:

                href_lower = href.lower()

                if "telegram" in href_lower:
                    telegram = href

                elif "twitter.com" in href_lower or "x.com" in href_lower:
                    twitter = href

                elif (
                    href.startswith("http")
                    and "coinmarketcap.com" not in href_lower
                    and "twitter" not in href_lower
                    and "telegram" not in href_lower
                ):
                    if website == "":
                        website = href

        coins.append({
            "Project Name": project_name,
            "Website": website,
            "Telegram": telegram,
            "Twitter": twitter,
            "CoinMarketCap Link": link
        })

        print(f"Completed: {project_name}")

    except Exception as e:
        print("Error:", e)

driver.quit()

df = pd.DataFrame(coins)

print(df)

df.to_csv("output/leads.csv", index=False)

print("Saved successfully!")