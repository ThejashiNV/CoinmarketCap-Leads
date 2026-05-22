import os
import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd


# -------------------------------
# Configuration
# -------------------------------
CHECKPOINT_FILE = "output/project_details_checkpoint.txt"

TIMEOUT = 15000

EMAIL_REGEX = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

CONTACT_PATHS = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/support",
    "/team",
    "/careers",
]


# -------------------------------
# Invalid Website Keywords
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
    "discord.gg",
    "discord.com",
    "github.com",

    "dataseed",
    "alchemy",
    "infura",
    "rpc.",
    "api.",

    "etherscan",
    "bscscan",
    "snowtrace",
    "tracemove",
    "nansen",
    "explorer",

    "cdn.",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",

    "schema.org",

    "pbs.twimg",
    "youtube.com",
    "youtu.be",
    "reddit.com",

    "sodar",
    "adtrafficquality",
    "mintscan",
    "fantomscan",
    "bybit.com",
    "okx.com",
]


# -------------------------------
# Invalid Email Keywords
# -------------------------------
INVALID_EMAIL_KEYWORDS = [
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".js",
    "schema.org",
    "example.com",
]


# -------------------------------
# Bad Email Keywords
# -------------------------------
BAD_EMAIL_KEYWORDS = [
    "noreply",
    "no-reply",
    "donotreply",
    "notification",
    "notifications",
    "support@zendesk",
    "mailer",
    "admin",
]


# -------------------------------
# Personal Email Domains
# -------------------------------
PERSONAL_EMAIL_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "hotmail.com",
    "outlook.com",
    "protonmail.com",
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

    if not isinstance(url, str):
        return False

    if not url.startswith("http"):
        return False

    lower_url = url.lower()

    for keyword in INVALID_WEBSITE_KEYWORDS:

        if keyword in lower_url:
            return False

    BAD_EXTENSIONS = [
        ".jpg",
        ".jpeg",
        ".png",
        ".svg",
        ".gif",
        ".js",
        ".css",
        ".json",
        ".xml",
    ]

    for ext in BAD_EXTENSIONS:

        if lower_url.endswith(ext):
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
# Email Validation
# -------------------------------
def is_valid_email(email):

    lower_email = email.lower()

    for keyword in INVALID_EMAIL_KEYWORDS:

        if keyword in lower_email:
            return False

    for keyword in BAD_EMAIL_KEYWORDS:

        if keyword in lower_email:
            return False

    for domain in PERSONAL_EMAIL_DOMAINS:

        if lower_email.endswith(domain):
            return False

    return True


# -------------------------------
# Email Confidence
# -------------------------------
def get_email_confidence(email):

    lower = email.lower()

    high_keywords = [
        "contact",
        "hello",
        "info",
        "team",
        "partnership",
        "business",
        "marketing",
    ]

    for keyword in high_keywords:

        if keyword in lower:
            return "HIGH"

    return "MEDIUM"


# -------------------------------
# Extract Emails From HTML
# -------------------------------
def extract_emails_from_html(html):

    emails = set(
        re.findall(
            EMAIL_REGEX,
            html
        )
    )

    cleaned = []

    for email in emails:

        email = email.strip().lower()

        if is_valid_email(email):
            cleaned.append(email)

    return list(set(cleaned))


# -------------------------------
# Crawl Website Emails
# -------------------------------
def extract_emails_from_website(
    page,
    website_url
):

    collected_emails = set()

    urls_to_visit = [website_url]

    parsed = urlparse(website_url)

    base = f"{parsed.scheme}://{parsed.netloc}"

    for path in CONTACT_PATHS:
        urls_to_visit.append(
            urljoin(base, path)
        )

    for url in urls_to_visit:

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=TIMEOUT
            )

            try:
                page.wait_for_load_state(
                    "networkidle",
                    timeout=3000
                )
            except Exception:
                pass

            html = page.content()

            emails = extract_emails_from_html(
                html
            )

            for email in emails:
                collected_emails.add(email)

        except Exception:
            continue

    return list(collected_emails)


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

                for a in soup.find_all(
                    "a",
                    href=True
                ):

                    href = a["href"].strip()

                    if href.startswith("//"):
                        href = "https:" + href

                    all_links.add(href)

                regex_links = re.findall(
                    r'https?://[^\s"\'>]+',
                    html
                )

                for link in regex_links:
                    all_links.add(link)

                # -------------------------------
                # Containers
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

                    if is_valid_linkedin(href):

                        linkedin_urls.add(href)

                        continue

                    if is_valid_telegram(href):

                        telegram_urls.add(href)

                        continue

                    if is_valid_twitter(href):

                        twitter_urls.add(href)

                        continue

                    if is_valid_discord(href):

                        discord_urls.add(href)

                        continue

                    if is_valid_github(href):

                        github_urls.add(href)

                        continue

                    if (
                        website_url == "N/A"
                        and is_valid_website(href)
                    ):

                        website_url = href

                # -------------------------------
                # Email Extraction
                # -------------------------------
                official_email = "Not Found"

                email_source = "Not Found"

                email_confidence = "LOW"

                if website_url != "N/A":

                    emails = extract_emails_from_website(
                        page,
                        website_url
                    )

                    if emails:

                        official_email = "; ".join(
                            emails
                        )

                        email_source = "Official Website"

                        email_confidence = max(
                            [
                                get_email_confidence(
                                    email
                                )
                                for email in emails
                            ],
                            key=lambda x: (
                                x == "HIGH",
                                x == "MEDIUM"
                            )
                        )

                # -------------------------------
                # Final Result
                # -------------------------------
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
                            sorted(
                                list(twitter_urls)[:3]
                            )
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
                    ),

                    "Official Email ID":
                        official_email,

                    "Email Source":
                        email_source,

                    "Email Confidence":
                        email_confidence
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

        browser.close()

    # -------------------------------
    # Save CSV
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