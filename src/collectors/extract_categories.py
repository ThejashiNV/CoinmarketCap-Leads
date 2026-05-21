import pandas as pd
from bs4 import BeautifulSoup


def extract_categories():
    # Load saved HTML
    with open("data/categories_page.html", "r", encoding="utf-8") as f:
        html = f.read()

    soup = BeautifulSoup(html, "html.parser")

    categories = []

    # Extract category links
    for a in soup.find_all("a", href=True):
        href = a["href"]

        if "/view/" in href:
            full_url = "https://coinmarketcap.com" + href

            category_name = a.get_text(strip=True)

            if category_name:
                categories.append({
                    "Category Name": category_name,
                    "Category URL": full_url
                })

    # Remove duplicates
    df = pd.DataFrame(categories).drop_duplicates()

    # Save CSV
    df.to_csv("output/categories.csv", index=False)

    print(f"Extracted {len(df)} categories.")
    print("Saved to output/categories.csv")


if __name__ == "__main__":
    extract_categories()