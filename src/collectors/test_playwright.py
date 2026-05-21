from playwright.sync_api import sync_playwright


def test_playwright():
    print("Opening website...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto("https://coinmarketcap.com/cryptocurrency-category/")
        print("Getting HTML content...")

        html = page.content()

        with open("data/categories_page.html", "w", encoding="utf-8") as f:
            f.write(html)

        print("HTML saved successfully to data/categories_page.html")

        browser.close()


if __name__ == "__main__":
    test_playwright()