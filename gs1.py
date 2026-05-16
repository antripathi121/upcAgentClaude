from playwright.sync_api import sync_playwright
import time
import re


def gs1_lookup(upc):

    try:
        with sync_playwright() as p:

            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            url = f"https://www.gs1.org/search?query={upc}"
            page.goto(url, timeout=60000)

            time.sleep(5)

            html = page.content()

            browser.close()

            # -----------------------------
            # SIMPLE CLEANING (BASIC EXTRACTION)
            # -----------------------------

            text = re.sub('<[^<]+?>', ' ', html)  # remove HTML tags
            text = re.sub('\s+', ' ', text)       # clean spaces

            # Try to detect company-like patterns (basic heuristic)
            keywords = ["Company", "Manufacturer", "Brand", "Owner"]

            extracted = []

            for word in keywords:
                if word in text:
                    extracted.append(word)

            if extracted:
                return "GS1 Data Found"
            else:
                return "GS1 No Structured Data"

    except Exception as e:
        return f"GS1 Error: {str(e)}"