from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import pandas as pd
import re


def clean_project_name(name):
    """
    Remove duplicated ticker symbols from names.
    Example:
    'Lido Staked ETHstETH' -> 'Lido Staked ETH'
    'USDSUSDS' -> 'USDS'
    """
    if not name:
        return ""

    name = str(name).strip()

    # Remove repeated suffix like stETH, USDS, WBTC, etc.
    match = re.match(r"^(.*?)([A-Z][A-Za-z0-9]{1,10})$", name)

    if match:
        base = match.group(1).strip()
        suffix = match.group(2).strip()

        # If name is just repeated ticker (USDSUSDS -> USDS)
        if base == suffix:
            return suffix

        # If base already ends with same suffix, remove duplicate
        if base.endswith(suffix):
            return base

        # If base contains spaces, likely project name + ticker appended
        if " " in base:
            return base

    return name


def is_valid_project_name(name):
    if not name:
        return False

    name = str(name).strip()

    if len(name) < 2:
        return False

    if name.startswith("$"):
        return False

    if re.fullmatch(r"[\d,.$%+\- ]+", name):
        return False

    return True


def extract_projects():
    categories_df = pd.read_csv("output/categories.csv")
    category_url = categories_df.iloc[0]["Category URL"]

    print(f"Opening category: {category_url}")

    projects = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(
            category_url,
            wait_until="domcontentloaded",
            timeout=60000
        )
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "lxml")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        if not href.startswith("/currencies/"):
            continue

        path_parts = href.strip("/").split("/")
        if len(path_parts) != 2:
            continue

        if not is_valid_project_name(text):
            continue

        full_url = "https://coinmarketcap.com" + href

        if full_url in seen_urls:
            continue

        seen_urls.add(full_url)

        cleaned_name = clean_project_name(text)

        projects.append({
            "Project Name": cleaned_name,
            "Project URL": full_url,
            "Category URL": category_url
        })

    df = pd.DataFrame(projects)
    df.to_csv("output/projects.csv", index=False)

    print(f"Extracted {len(df)} projects.")
    print("Saved to output/projects.csv")


if __name__ == "__main__":
    extract_projects()