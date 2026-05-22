import os
import re

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd


# -------------------------------
# Configuration
# -------------------------------
CHECKPOINT_FILE = "output/project_details_checkpoint.txt"

TIMEOUT = 15000


# -------------------------------
# URLs we do NOT want
# as official websites
# -------------------------------
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


# -------------------------------
# Checkpoint Functions
# -------------------------------
def load_checkpoint():

    if os.path.exists(CHECKPOINT_FILE):

        with open(
            CHECKPOINT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return set(
                line.strip()
                for line in f
            )

    return set()


def save_checkpoint(project_name):

    with open(
        CHECKPOINT_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(project_name + "\n")


# -------------------------------
# Validation Functions
# -------------------------------
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

    if "coinmarketcap" in lower_url:
        return False

    return "linkedin.com" in lower_url


def is_valid_telegram(url):

    lower_url = url.lower()

    if "coinmarketcapannouncements" in lower_url:
        return False

    return (
        "t.me" in lower_url
        or "telegram.me" in lower_url
    )


def is_valid_twitter(url):

    lower_url = url.lower()

    return (
        "twitter.com" in lower_url
        or "x.com" in lower_url
    )


def is_valid_discord(url):

    lower_url = url.lower()

    return (
        "discord.gg" in lower_url
        or "discord.com" in lower_url
    )


def is_valid_github(url):

    return "github.com" in url.lower()


# -------------------------------
# Main Extraction Function
# -------------------------------
def extract_project_details():

    projects_df = pd.read_csv(
        "output/projects.csv"
    )

    results = []

    completed = load_checkpoint()

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        for _, row in projects_df.iterrows():

            project_name = row["Project Name"]

            project_url = row["Project URL"]

            # Skip completed
            if project_name in completed:

                print(
                    f"Skipping completed: "
                    f"{project_name}"
                )

                continue

            print(f"\nProcessing: {project_name}")

            try:

                page.goto(
                    project_url,
                    wait_until="domcontentloaded",
                    timeout=TIMEOUT
                )

                try:

                    page.wait_for_load_state(
                        "networkidle",
                        timeout=5000
                    )

                except Exception:
                    pass

                html = page.content()

                soup = BeautifulSoup(
                    html,
                    "lxml"
                )

                # -------------------------------
                # Collect ALL links
                # -------------------------------
                all_links = set()

                # From anchor tags
                for a in soup.find_all(
                    "a",
                    href=True
                ):

                    href = a["href"].strip()

                    if href.startswith("//"):
                        href = "https:" + href

                    all_links.add(href)

                # Regex fallback
                regex_links = re.findall(
                    r'https?://[^\s"\'>]+',
                    html
                )

                for link in regex_links:
                    all_links.add(link)

                # -------------------------------
                # Social Containers
                # -------------------------------
                website_url = "N/A"

                linkedin_urls = set()

                telegram_urls = set()

                twitter_urls = set()

                discord_urls = set()

                github_urls = set()

                # -------------------------------
                # Process Links
                # -------------------------------
                for href in all_links:

                    # LinkedIn
                    if is_valid_linkedin(href):

                        linkedin_urls.add(href)

                        continue

                    # Telegram
                    if is_valid_telegram(href):

                        telegram_urls.add(href)

                        continue

                    # Twitter / X
                    if is_valid_twitter(href):

                        twitter_urls.add(href)

                        continue

                    # Discord
                    if is_valid_discord(href):

                        discord_urls.add(href)

                        continue

                    # Github
                    if is_valid_github(href):

                        github_urls.add(href)

                        continue

                    # Official Website
                    if (
                        website_url == "N/A"
                        and is_valid_website(href)
                    ):

                        website_url = href

                result = {

                    "Project Name":
                        project_name,

                    "CoinMarketCap URL":
                        project_url,

                    "Official Website URL":
                        website_url,

                    "LinkedIn URLs": (
                        "; ".join(
                            sorted(linkedin_urls)
                        )
                        if linkedin_urls
                        else "N/A"
                    ),

                    "Telegram URLs": (
                        "; ".join(
                            sorted(telegram_urls)
                        )
                        if telegram_urls
                        else "N/A"
                    ),

                    "Twitter URLs": (
                        "; ".join(
                            sorted(twitter_urls)
                        )
                        if twitter_urls
                        else "N/A"
                    ),

                    "Discord URLs": (
                        "; ".join(
                            sorted(discord_urls)
                        )
                        if discord_urls
                        else "N/A"
                    ),

                    "Github URLs": (
                        "; ".join(
                            sorted(github_urls)
                        )
                        if github_urls
                        else "N/A"
                    )
                }

                results.append(result)

                save_checkpoint(project_name)

                print(
                    f"Completed: "
                    f"{project_name}"
                )

            except Exception as e:

                print(
                    f"Error processing "
                    f"{project_name}: {e}"
                )

                results.append({

                    "Project Name":
                        project_name,

                    "CoinMarketCap URL":
                        project_url,

                    "Official Website URL":
                        "N/A",

                    "LinkedIn URLs":
                        "N/A",

                    "Telegram URLs":
                        "N/A",

                    "Twitter URLs":
                        "N/A",

                    "Discord URLs":
                        "N/A",

                    "Github URLs":
                        "N/A"
                })

        browser.close()

    # -------------------------------
    # Save Final CSV
    # -------------------------------
    df = pd.DataFrame(results)

    df = df.drop_duplicates(
        subset=["CoinMarketCap URL"]
    )

    df.to_csv(
        "output/project_details.csv",
        index=False
    )

    print(
        "\nSaved to "
        "output/project_details.csv"
    )

    print(
        f"Processed {len(df)} "
        f"projects successfully."
    )


if __name__ == "__main__":

    extract_project_details()