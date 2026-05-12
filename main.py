import re
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# ---------- Helper Functions ----------

def extract_email_from_page(driver):
    """Extract the first email address found in the page source."""
    try:
        page_source = driver.page_source
        emails = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            page_source
        )

        # Filter out obvious non-contact emails
        for email in emails:
            email_lower = email.lower()
            if not any(
                bad in email_lower
                for bad in ["example.com", "wixpress.com", "sentry.io"]
            ):
                return email

    except:
        pass

    return ""


def extract_linkedin_links(driver):
    """Extract all unique LinkedIn URLs found on the page."""
    linkedin_links = []

    try:
        links = driver.find_elements(By.TAG_NAME, "a")

        for link in links:
            href = link.get_attribute("href")

            if href and "linkedin.com" in href.lower():
                if href not in linkedin_links:
                    linkedin_links.append(href)

    except:
        pass

    return " | ".join(linkedin_links)


# ---------- Setup Chrome Driver ----------

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install())
)

# ---------- Open CoinMarketCap New Listings ----------

url = "https://coinmarketcap.com/new/"
driver.get(url)

time.sleep(10)

project_links = []

rows = driver.find_elements(By.CSS_SELECTOR, "tbody tr")

for row in rows[:15]:  # Process first 15 projects
    try:
        link_element = row.find_element(
            By.CSS_SELECTOR,
            "a[href*='/currencies/']"
        )

        project_link = link_element.get_attribute("href")

        if project_link not in project_links:
            project_links.append(project_link)

    except:
        pass

print("Collected Project Links:")
print(project_links)

# ---------- Extract Project Details ----------

coins = []

for link in project_links:
    try:
        driver.get(link)
        time.sleep(5)

        project_name = ""
        website = ""
        telegram = ""
        twitter = ""

        # Get project name
        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            project_name = h1.text.split("\n")[0]
        except:
            pass

        # Get all links from CoinMarketCap project page
        all_links = driver.find_elements(By.TAG_NAME, "a")

        for item in all_links:
            href = item.get_attribute("href")

            if not href:
                continue

            href_lower = href.lower()

            if "telegram" in href_lower:
                telegram = href

            elif "twitter.com" in href_lower or "x.com" in href_lower:
                twitter = href

            elif (
                href.startswith("http")
                and "coinmarketcap.com" not in href_lower
                and "twitter.com" not in href_lower
                and "x.com" not in href_lower
                and "telegram" not in href_lower
                and "linkedin.com" not in href_lower
                and "youtube.com" not in href_lower
                and "facebook.com" not in href_lower
                and "instagram.com" not in href_lower
                and "medium.com" not in href_lower
                and "sensors.saasexch.com" not in href_lower
            ):
                if website == "":
                    website = href

        # Initialize fields
        official_email = ""
        linkedin_profiles = ""

        # Visit official website and extract email + LinkedIn
        if website:
            try:
                driver.get(website)
                time.sleep(5)

                official_email = extract_email_from_page(driver)
                linkedin_profiles = extract_linkedin_links(driver)

            except:
                pass

        # Save result
        coins.append({
            "Project Name": project_name,
            "Project Website URL": website,
            "Official Email ID": official_email,
            "LinkedIn Profiles of Team Members": linkedin_profiles,
            "Telegram ID / Group / Channel": telegram,
            "Twitter": twitter,
            "CoinMarketCap Link": link
        })

        print(f"Completed: {project_name}")

    except Exception as e:
        print("Error:", e)

# ---------- Save to CSV ----------

driver.quit()

df = pd.DataFrame(coins)

print(df)

df.to_csv("output/leads.csv", index=False)

print("Saved successfully!")