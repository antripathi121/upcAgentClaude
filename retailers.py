import requests
from playwright.sync_api import sync_playwright

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _playwright_search(url, selectors, wait_ms=4000):
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=60000)
            page.wait_for_timeout(wait_ms)
            parts = []
            for sel in selectors:
                try:
                    el = page.locator(sel).first
                    if el.count() > 0:
                        text = el.inner_text().strip()
                        if text:
                            parts.append(text)
                except Exception:
                    pass
            browser.close()
            return "\n".join(parts) or None
    except Exception:
        return None


def amazon_lookup(upc):
    # Amazon blocks all headless scrapers; UPCitemdb is a reliable product database
    try:
        r = requests.get(
            f"https://api.upcitemdb.com/prod/trial/lookup?upc={upc}",
            headers={"User-Agent": USER_AGENT},
            timeout=10
        )
        data = r.json()
        if data.get("items"):
            item = data["items"][0]
            parts = [
                item.get("title", ""),
                item.get("brand", ""),
                item.get("description", ""),
                item.get("size", ""),
            ]
            text = "\n".join(v for v in parts if v)
            return text.strip() or None
    except Exception:
        pass
    return None


def target_lookup(upc):
    return _playwright_search(
        f"https://www.target.com/s?searchTerm={upc}",
        [
            "[data-test='product-title']",
            ".ProductCardVariantDefault-title",
            "h2[data-test='product-title']",
        ]
    )


def kroger_lookup(upc):
    return _playwright_search(
        f"https://www.kroger.com/search?query={upc}&searchType=default_search",
        [
            ".kds-ProductCard-title",
            ".product-details h2",
            ".kds-Text--title",
        ]
    )


def frysfood_lookup(upc):
    return _playwright_search(
        f"https://www.frysfood.com/search?query={upc}&searchType=default_search",
        [
            ".kds-ProductCard-title",
            ".product-details h2",
        ]
    )


def iherb_lookup(upc):
    return _playwright_search(
        f"https://www.iherb.com/search?kw={upc}",
        [
            ".product-title",
            ".ga-product-name",
            "h2.product-name",
        ]
    )


def walmart_lookup(upc):
    return _playwright_search(
        f"https://www.walmart.com/search?q={upc}",
        [
            "[data-automation-id='product-title']",
            ".sans-serif.normal.dark-gray.mb0",
            "span.f6.f5-l.normal.dib",
        ]
    )


def walgreens_lookup(upc):
    return _playwright_search(
        f"https://www.walgreens.com/search/results.jsp?Ntt={upc}",
        [
            ".product-title",
            ".wag-product-title",
            "h1.product-details-title",
        ]
    )


def usda_lookup(upc):
    try:
        r = requests.get(
            f"https://api.nal.usda.gov/fdc/v1/foods/search?query={upc}&api_key=DEMO_KEY",
            timeout=10
        )
        data = r.json()
        foods = data.get("foods", [])
        if foods:
            food = foods[0]
            parts = [
                food.get("description", ""),
                food.get("brandOwner", ""),
                food.get("brandName", ""),
                food.get("ingredients", ""),
            ]
            text = "\n".join(v for v in parts if v)
            return text.strip() or None
    except Exception:
        pass
    return None


def barcodelookup_lookup(upc):
    return _playwright_search(
        f"https://www.barcodelookup.com/{upc}",
        [
            ".product-title h4",
            "#product-name",
            ".product-meta-title",
        ]
    )


def vitacost_lookup(upc):
    return _playwright_search(
        f"https://www.vitacost.com/search?t={upc}",
        [
            ".product-name",
            "h2.product-title",
            ".ga-product-name",
        ]
    )


def open_food_facts_lookup(upc):
    try:
        r = requests.get(
            f"https://world.openfoodfacts.org/api/v2/product/{upc}.json",
            timeout=10
        )
        data = r.json()
        if data.get("status") == 1:
            p = data["product"]
            parts = [
                p.get("product_name", ""),
                p.get("brands", ""),
                p.get("quantity", ""),
                p.get("generic_name", ""),
                p.get("categories", ""),
            ]
            text = "\n".join(v for v in parts if v)
            return text.strip() or None
    except Exception:
        pass
    return None
