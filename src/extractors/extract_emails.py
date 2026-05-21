import logging
import re
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# -------------------------------
# Configuration
# -------------------------------
EMAIL_PATTERN = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
TARGET_KEYWORDS = ["contact", "about", "team", "careers"]
MAX_RETRIES = 3

# -------------------------------
# Logging Setup
# -------------------------------
logging.basicConfig(
    filename="logs/extraction.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


def extract_emails_from_html(html):
    """Extract unique email addresses from HTML."""
    html = html[:200000]
    matches = re.findall(EMAIL_PATTERN, html)
    return list(dict.fromkeys(matches))


def choose_best_email(emails):
    if not emails:
        return "N/A"

    priority_keywords = [
        "contact", "hello", "info", "business",
        "partnership", "partnerships",
        "sales", "bd", "marketing"
    ]

    avoid_keywords = [
        "noreply", "no-reply", "donotreply",
        "notification", "notifications",
        "privacy", "legal", "abuse", "security",
        "support", "help", "admin", "webmaster"
    ]

    for keyword in priority_keywords:
        for email in emails:
            if keyword in email.lower():
                return email

    for email in emails:
        if not any(keyword in email.lower() for keyword in avoid_keywords):
            return email

    return emails[0]


def get_priority_links(html, base_url):
    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(base_url).netloc

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(base_url, href)

        if urlparse(full_url).netloc != domain:
            continue

        lower_url = full_url.lower()

        if any(keyword in lower_url for keyword in TARGET_KEYWORDS):
            if full_url not in links:
                links.append(full_url)

    return links


def is_valid_website(url):
    if pd.isna(url):
        return False

    url = str(url).strip()

    if url == "" or url.upper() == "N/A":
        return False

    return url.startswith("http")


def safe_goto(page, url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logging.info(f"Opening {url} (Attempt {attempt})")
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )
            page.wait_for_timeout(5000)
            return True

        except Exception as e:
            logging.warning(
                f"Attempt {attempt} failed for {url}: {e}"
            )

            if attempt == MAX_RETRIES:
                logging.error(
                    f"Failed to open {url} after {MAX_RETRIES} attempts."
                )

    return False


def run_email_extraction():
    df = pd.read_csv("output/project_details.csv")
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        for _, row in df.iterrows():
            project_name = row["Project Name"]
            website_url = row["Official Website URL"]
            linkedin_urls = row.get("LinkedIn URLs", "N/A")

            print(f"\nProcessing: {project_name}")
            logging.info(f"Processing project: {project_name}")

            final_email = "N/A"
            email_source = "Not Found"

            if not is_valid_website(website_url):
                if (
                    isinstance(linkedin_urls, str)
                    and linkedin_urls.strip() not in ["", "N/A"]
                ):
                    email_source = "LinkedIn Fallback"

                row["Official Email ID"] = final_email
                row["Email Source"] = email_source
                results.append(row.to_dict())
                continue

            try:
                if safe_goto(page, website_url):
                    homepage_html = page.content()

                    emails = extract_emails_from_html(homepage_html)

                    if emails:
                        final_email = choose_best_email(emails)
                        email_source = "Website"
                    else:
                        priority_links = get_priority_links(
                            homepage_html,
                            website_url
                        )

                        for link in priority_links:
                            print(f"  Checking: {link}")

                            if safe_goto(page, link):
                                html = page.content()
                                emails = extract_emails_from_html(html)

                                if emails:
                                    final_email = choose_best_email(emails)
                                    email_source = "Website"
                                    break

                if final_email == "N/A":
                    if (
                        isinstance(linkedin_urls, str)
                        and linkedin_urls.strip() not in ["", "N/A"]
                    ):
                        email_source = "LinkedIn Fallback"

            except Exception as e:
                logging.exception(
                    f"Unexpected error while processing {project_name}: {e}"
                )

                if (
                    isinstance(linkedin_urls, str)
                    and linkedin_urls.strip() not in ["", "N/A"]
                ):
                    email_source = "LinkedIn Fallback"

            row["Official Email ID"] = final_email
            row["Email Source"] = email_source
            results.append(row.to_dict())

            logging.info(
                f"Completed {project_name} | "
                f"Email: {final_email} | "
                f"Source: {email_source}"
            )

        browser.close()

    output_df = pd.DataFrame(results)
    output_df.to_csv("output/final_leads.csv", index=False)

    logging.info(
        "Extraction completed successfully. "
        f"Total projects processed: {len(output_df)}"
    )

    print("\nSaved to output/final_leads.csv")
    print(f"Processed {len(output_df)} projects successfully.")
    print("Logs saved to logs/extraction.log")


if __name__ == "__main__":
    run_email_extraction()