import re
import time
import pandas as pd

from googlesearch import search
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# -----------------------------
# Helper Functions
# -----------------------------

def extract_email_from_page(driver):
    try:
        page_source = driver.page_source

        emails = re.findall(
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            page_source
        )

        ignored_domains = [
            "example.com",
            "wixpress.com",
            "sentry.io"
        ]

        for email in emails:
            email_lower = email.lower()

            if not any(domain in email_lower for domain in ignored_domains):
                return email

    except:
        pass

    return ""


def extract_linkedin_links(driver):
    linkedin_links = []

    try:
        links = driver.find_elements(By.TAG_NAME, "a")

        for link in links:
            href = link.get_attribute("href")

            if href and "linkedin.com" in href.lower():
                href_lower = href.lower()

                if (
                    "/company/" in href_lower
                    or "/in/" in href_lower
                ):
                    if href not in linkedin_links:
                        linkedin_links.append(href)

    except:
        pass

    return " | ".join(linkedin_links[:10])


def search_linkedin_on_google(project_name):
    """
    Fallback method:
    Search Google for the project's LinkedIn page.
    """
    try:
        query = f"{project_name} LinkedIn"

        for url in search(query, num_results=10):
            url_lower = url.lower()

            if (
                "linkedin.com/company/" in url_lower
                or "linkedin.com/in/" in url_lower
            ):
                return url

    except:
        pass

    return ""


def extract_telegram_links(driver):
    telegram_links = []

    try:
        links = driver.find_elements(By.TAG_NAME, "a")

        for link in links:
            href = link.get_attribute("href")

            if href and "telegram" in href.lower():
                href_lower = href.lower()

                # Ignore generic Telegram home/download pages
                if (
                    href_lower == "https://telegram.org/"
                    or "telegram.org/dl" in href_lower
                ):
                    continue

                if href not in telegram_links:
                    telegram_links.append(href)

    except:
        pass

    return " | ".join(telegram_links[:10])


def is_valid_website(href):
    if not href:
        return False

    href_lower = href.lower()

    blocked_domains = [
        "coinmarketcap.com",
        "twitter.com",
        "x.com",
        "telegram",
        "linkedin.com",
        "youtube.com",
        "facebook.com",
        "instagram.com",
        "medium.com",
        "docs.google.com",
        "sensors.saasexch.com"
    ]

    for domain in blocked_domains:
        if domain in href_lower:
            return False

    return href.startswith("http")


# -----------------------------
# Setup Chrome Driver
# -----------------------------

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install())
)

# -----------------------------
# Open CoinMarketCap New Listings
# -----------------------------

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

# -----------------------------
# Extract Project Details
# -----------------------------

coins = []

for link in project_links:
    try:
        driver.get(link)
        time.sleep(5)

        project_name = ""
        website = ""
        telegram = ""
        twitter = ""

        # Extract project name
        try:
            h1 = driver.find_element(By.TAG_NAME, "h1")
            project_name = h1.text.split("\n")[0]
        except:
            pass

        # Extract links from CoinMarketCap page
        all_links = driver.find_elements(By.TAG_NAME, "a")

        for item in all_links:
            href = item.get_attribute("href")

            if not href:
                continue

            href_lower = href.lower()

            if "telegram" in href_lower and telegram == "":
                telegram = href

            elif (
                ("twitter.com" in href_lower or "x.com" in href_lower)
                and twitter == ""
            ):
                twitter = href

            elif website == "" and is_valid_website(href):
                website = href

        # Initialize extracted fields
        official_email = ""
        linkedin_profiles = ""

        # Visit official website
        if website:
            try:
                driver.get(website)
                time.sleep(5)

                official_email = extract_email_from_page(driver)
                linkedin_profiles = extract_linkedin_links(driver)

                # If Telegram not found on CoinMarketCap page,
                # try to find it on the website
                if telegram == "":
                    telegram = extract_telegram_links(driver)

            except:
                pass

        # Fallback: search Google for LinkedIn
        if linkedin_profiles == "" and project_name:
            print(f"Searching LinkedIn for: {project_name}")
            linkedin_profiles = search_linkedin_on_google(project_name)

        # Save results
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

# -----------------------------
# Save Results
# -----------------------------

driver.quit()

df = pd.DataFrame(coins)

print(df)

df.to_csv("output/leads.csv", index=False)

print("Saved successfully!")