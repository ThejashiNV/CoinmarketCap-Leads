from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd


# URLs we do NOT want as official websites
INVALID_WEBSITE_KEYWORDS = [
    "coinmarketcap.com",
    "certik-skynet.com",
    "docs.google.com",
    "forms.gle",
    "forum.",
    "medium.com",
    "linkedin.com",
    "t.me",
    "telegram.me",
    "twitter.com",
    "x.com",
]


def is_valid_website(url):
    if not url.startswith("http"):
        return False

    lower_url = url.lower()

    for keyword in INVALID_WEBSITE_KEYWORDS:
        if keyword in lower_url:
            return False

    return True


def is_valid_linkedin(url):
    lower_url = url.lower()

    # Remove CoinMarketCap's own LinkedIn
    if "coinmarketcap" in lower_url:
        return False

    return "linkedin.com" in lower_url


def is_valid_telegram(url):
    lower_url = url.lower()

    # Remove CoinMarketCap announcements
    if "coinmarketcapannouncements" in lower_url:
        return False

    return (
        "t.me" in lower_url
        or "telegram.me" in lower_url
    )


def extract_project_details():
    projects_df = pd.read_csv("output/projects.csv")

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for _, row in projects_df.iterrows():
            project_name = row["Project Name"]
            project_url = row["Project URL"]

            print(f"Processing: {project_name}")

            try:
                page.goto(
                    project_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )
                page.wait_for_timeout(5000)

                html = page.content()
                soup = BeautifulSoup(html, "lxml")

                website_url = "N/A"
                linkedin_urls = set()
                telegram_urls = set()

                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()

                    # LinkedIn
                    if is_valid_linkedin(href):
                        linkedin_urls.add(href)
                        continue

                    # Telegram
                    if is_valid_telegram(href):
                        if href.startswith("//"):
                            href = "https:" + href
                        telegram_urls.add(href)
                        continue

                    # Official Website
                    if website_url == "N/A" and is_valid_website(href):
                        website_url = href

                results.append({
                    "Project Name": project_name,
                    "CoinMarketCap URL": project_url,
                    "Official Website URL": website_url,
                    "LinkedIn URLs": (
                        "; ".join(sorted(linkedin_urls))
                        if linkedin_urls else "N/A"
                    ),
                    "Telegram URLs": (
                        "; ".join(sorted(telegram_urls))
                        if telegram_urls else "N/A"
                    )
                })

            except Exception as e:
                print(f"Error processing {project_name}: {e}")

                results.append({
                    "Project Name": project_name,
                    "CoinMarketCap URL": project_url,
                    "Official Website URL": "N/A",
                    "LinkedIn URLs": "N/A",
                    "Telegram URLs": "N/A"
                })

        browser.close()

    df = pd.DataFrame(results)
    df.to_csv("output/project_details.csv", index=False)

    print("Saved to output/project_details.csv")


if __name__ == "__main__":
    extract_project_details()