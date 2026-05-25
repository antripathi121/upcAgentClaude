import os
import random
import requests

# Playwright and stealth are optional — API-based sources still work without them.
try:
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    _STEALTH = Stealth(navigator_webdriver=True)
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    _STEALTH = None

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]
USER_AGENT = USER_AGENTS[1]

# Text that indicates a blocked page or a non-product result
_SKIP_TEXT = {
    "shop on ebay", "new listing", "sponsored", "access denied",
    "captcha", "verify you are human", "robot", "just a moment",
}

_BLOCK_TITLES = ("access denied", "captcha", "robot", "just a moment", "are you human", "security check")


def _playwright_search(url, selectors, wait_ms=4000):
    if not _PLAYWRIGHT_AVAILABLE:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                ],
            )
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "DNT": "1",
                },
            )
            page = context.new_page()
            _STEALTH.apply_stealth_sync(page)

            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            # Mimic human scroll before waiting for content
            page.evaluate("window.scrollBy(0, window.innerHeight / 3)")
            page.wait_for_timeout(wait_ms)

            if any(s in page.title().lower() for s in _BLOCK_TITLES):
                browser.close()
                return None

            parts = []
            for sel in selectors:
                try:
                    elements = page.locator(sel).all()
                    for el in elements[:10]:
                        text = el.inner_text().strip()
                        if text and text.lower() not in _SKIP_TEXT:
                            parts.append(text)
                            break
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

            # Pull offer titles — often contain "12 oz", "16 ct" etc.
            offer_titles = " | ".join(
                o.get("title", "") for o in (item.get("offers") or [])[:3] if o.get("title")
            )

            parts = [
                item.get("title", ""),
                item.get("brand", ""),
                item.get("description", ""),
                item.get("size", ""),
                item.get("weight", ""),
                offer_titles,
            ]
            text = "\n".join(v for v in parts if v)
            return text.strip() or None
    except Exception:
        pass
    return None


def _target_credentials():
    try:
        import streamlit as st
        return st.secrets.get("TARGET_VISITOR_ID", ""), st.secrets.get("TARGET_API_KEY", "")
    except Exception:
        pass
    return os.environ.get("TARGET_VISITOR_ID", ""), os.environ.get("TARGET_API_KEY", "")


def target_lookup(upc):
    visitor_id, api_key = _target_credentials()
    if not visitor_id or not api_key:
        return None
    try:
        r = requests.get(
            "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2",
            params={
                "keyword":            upc,
                "count":              5,
                "channel":            "WEB",
                "page":               f"/s/{upc}",
                "visitor_id":         visitor_id,
                "pricing_store_id":   "3991",
                "inventory_store_ids":"3991",
                "platform":           "desktop",
            },
            headers={
                "User-Agent": USER_AGENT,
                "Accept":     "application/json",
                "x-api-key":  api_key,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return None

        products = r.json().get("data", {}).get("search", {}).get("products", [])
        if not products:
            return None

        # Target's primary_barcode field is never populated via this endpoint.
        # A 12-digit UPC is specific enough that the first result is correct.
        item  = products[0].get("item", {})
        desc  = item.get("product_description", {})
        title = desc.get("title", "").strip()

        # soft_bullets are plain text; bullet_descriptions have HTML tags
        soft  = desc.get("soft_bullets", {}).get("bullets", [])
        blurb = soft[0].strip() if soft else ""

        parts = [v for v in [title, blurb] if v]
        return "\n".join(parts) or None
    except Exception:
        return None


def _kroger_token():
    try:
        import streamlit as st
        client_id     = st.secrets.get("KROGER_CLIENT_ID", "")
        client_secret = st.secrets.get("KROGER_CLIENT_SECRET", "")
    except Exception:
        client_id     = os.environ.get("KROGER_CLIENT_ID", "")
        client_secret = os.environ.get("KROGER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        return None

    r = requests.post(
        "https://api.kroger.com/v1/connect/oauth2/token",
        data={"grant_type": "client_credentials", "scope": "product.compact"},
        auth=(client_id, client_secret),
        timeout=10,
    )
    return r.json().get("access_token")


def kroger_lookup(upc):
    try:
        token = _kroger_token()
        if not token:
            return None

        r = requests.get(
            "https://api.kroger.com/v1/products",
            params={"filter.term": upc, "filter.limit": 1},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=10,
        )
        products = r.json().get("data", [])
        if not products:
            return None

        # Kroger's filter.term is a text search, not a barcode lookup.
        # Only accept results where the returned item UPC matches to avoid
        # false positives. Normalise both to digits-only for comparison.
        upc_clean = "".join(c for c in upc if c.isdigit())
        for p in products:
            items     = p.get("items", [{}])
            item_upc  = "".join(c for c in (items[0].get("upc") or "") if c.isdigit())
            # Strip leading zeros for comparison
            if item_upc and item_upc.lstrip("0") == upc_clean.lstrip("0"):
                brand       = p.get("brand", "")
                description = p.get("description", "")
                size        = items[0].get("size", "")
                categories  = ", ".join(p.get("categories", []))
                parts = [brand, description, size, categories]
                return "\n".join(v for v in parts if v) or None

        return None
    except Exception:
        return None


def google_shopping_lookup(upc):
    """UPC lookup via SerpAPI Google Shopping — aggregates listings from many
    retailers. More reliable than site-specific searches because product listings
    often include the UPC as a model/part number in their metadata.
    """
    api_key = _serpapi_key()
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={
                "engine":        "google_shopping",
                "q":             upc,
                "google_domain": "google.com",
                "api_key":       api_key,
            },
            timeout=15,
        )
        if r.status_code != 200:
            return None

        results = r.json().get("shopping_results", [])
        if not results:
            return None

        # Filter out noisy/unrelated listings — keep results where the title
        # doesn't look like a completely different product category
        _noise = ("chocolate cream", "friskies", "fry's chocolate",
                  "cocoa powder", "boot", "shoe", "cable", "hdmi")
        clean = [i for i in results
                 if not any(n in i.get("title", "").lower() for n in _noise)]
        item  = (clean or results)[0]

        title = item.get("title", "").strip()
        brand = (item.get("brand") or "").strip()
        parts = [v for v in [brand, title] if v]
        return "\n".join(parts) or None
    except Exception:
        return None


def foodland_lookup(upc):
    """Foodland Super Market (Hawaii) — shop.foodland.com UPC search via Playwright.
    Products render client-side; h3 elements containing 'Open product description'
    are the product tiles. No stealth needed — site has no bot protection.
    """
    try:
        from playwright.sync_api import sync_playwright as _sync_playwright
        with _sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = ctx.new_page()
            page.goto(
                f"https://shop.foodland.com/sm/planning/rsid/11/results?q={upc}",
                timeout=60000,
                wait_until="networkidle",
            )
            page.wait_for_timeout(3000)

            if any(s in page.title().lower() for s in _BLOCK_TITLES):
                browser.close()
                return None

            h3s = page.locator("h3").all()
            for el in h3s:
                try:
                    text = el.inner_text().strip()
                    if "Open product description" in text:
                        name = text.replace("\nOpen product description", "").strip()
                        if name:
                            browser.close()
                            return name
                except Exception:
                    pass

            browser.close()
            return None
    except Exception:
        return None


def iherb_lookup(upc):
    """iHerb UPC search — plain HTTP request, no Playwright needed.
    iHerb renders search results server-side; product titles sit in
    class='product-title' elements in the raw HTML.
    """
    try:
        r = requests.get(
            f"https://www.iherb.com/search?kw={upc}",
            headers={
                "User-Agent":      USER_AGENT,
                "Accept":          "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=12,
        )
        if r.status_code != 200:
            return None

        import re
        # Product titles are in class="product-title" spans inside the listing
        matches = re.findall(
            r'class="product-title[^"]*"[^>]*>\s*(?:<[^>]+>)?\s*(.*?)\s*(?:<|$)',
            r.text, re.DOTALL
        )
        titles = [re.sub(r"<[^>]+>", "", m).strip() for m in matches if m.strip()]
        if not titles:
            return None

        return titles[0]
    except Exception:
        return None


def _serpapi_key():
    try:
        import streamlit as st
        return st.secrets.get("SERPAPI_KEY", "")
    except Exception:
        return os.environ.get("SERPAPI_KEY", "")


def serpapi_amazon_lookup(upc):
    """Product lookup via SerpAPI Amazon engine — searches Amazon.com by UPC."""
    api_key = _serpapi_key()
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "amazon", "k": upc, "api_key": api_key},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("organic_results", [])
        if not results:
            return None
        item  = results[0]
        title = item.get("title", "").strip()
        brand = (item.get("brand") or "").strip()
        parts = [v for v in [brand, title] if v]
        return "\n".join(parts) or None
    except Exception:
        return None


def walmart_lookup(upc):
    """Product lookup via SerpAPI Google search restricted to walmart.com.
    Walmart stores UPCs as 'model number' on product pages.
    """
    api_key = _serpapi_key()
    if not api_key:
        return None
    try:
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": f"site:walmart.com {upc}", "api_key": api_key},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("organic_results", [])
        if not results:
            return None
        item    = results[0]
        title   = item.get("title", "").strip()
        snippet = (item.get("snippet") or "").strip()
        parts   = [v for v in [title, snippet] if v]
        return "\n".join(parts) or None
    except Exception:
        return None


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
    """USDA FoodData Central — branded food lookup by GTIN/UPC.
    Free API; DEMO_KEY works but is rate-limited. Set USDA_FDC_API_KEY in
    secrets for higher limits (free key at https://fdc.nal.usda.gov/api-guide).
    """
    try:
        import streamlit as st
        api_key = st.secrets.get("USDA_FDC_API_KEY", "") or "DEMO_KEY"
    except Exception:
        api_key = os.environ.get("USDA_FDC_API_KEY", "DEMO_KEY")

    try:
        # USDA FDC is inconsistent: some products are indexed as GTIN-14 (14 digits,
        # "00" prefix), others as GTIN-12. Try both to maximise hit rate.
        gtin14  = upc.zfill(14)
        upc_key = upc.lstrip("0")
        match   = None
        for query in (gtin14, upc):
            r = requests.get(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                params={
                    "query":    query,
                    "dataType": "Branded",
                    "pageSize": 5,
                    "api_key":  api_key,
                },
                timeout=10,
            )
            if r.status_code != 200:
                continue
            foods = r.json().get("foods", [])
            match = next((f for f in foods if f.get("gtinUpc", "").lstrip("0") == upc_key), None)
            if match:
                break
        if match is None:
            return None
        parts = [
            match.get("description", ""),
            match.get("brandName", ""),
            match.get("brandOwner", ""),
        ]
        return "\n".join(v for v in parts if v).strip() or None
    except Exception:
        return None


def barcodelookup_lookup(upc):
    """barcodelookup.com — confirmed working; custom extraction for name + manufacturer."""
    if not _PLAYWRIGHT_AVAILABLE:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            ctx = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = ctx.new_page()
            _STEALTH.apply_stealth_sync(page)
            page.goto(f"https://www.barcodelookup.com/{upc}", timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            if any(s in page.title().lower() for s in _BLOCK_TITLES):
                browser.close()
                return None

            data = page.evaluate("""() => {
                const name = document.querySelector('.product-details h4');
                const labels = [...document.querySelectorAll('.product-text-label')];
                const getText = (prefix) => {
                    const label = labels.find(l => l.innerText.includes(prefix));
                    if (!label) return '';
                    const sib = label.nextElementSibling;
                    return sib ? sib.innerText.trim() : '';
                };
                return {
                    name: name ? name.innerText.trim() : '',
                    manufacturer: getText('Manufacturer'),
                    brand: getText('Brand'),
                    description: getText('Description'),
                };
            }""")

            parts = [v for v in [
                data.get("name", ""),
                data.get("brand", "") or data.get("manufacturer", ""),
                data.get("description", ""),
            ] if v]
            browser.close()
            return "\n".join(parts) or None
    except Exception:
        return None


def vitacost_lookup(upc):
    return _playwright_search(
        f"https://www.vitacost.com/search?t={upc}",
        [
            ".product-name",
            "h2.product-title",
            ".ga-product-name",
        ]
    )


# --- eBay Catalog API (OAuth + GTIN barcode lookup) ---
# Uses eBay Catalog API product_summary/search with gtin for exact UPC match.
# Requires "commerce.catalog.readonly" scope enabled in your eBay Developer app:
#   developer.ebay.com → My APIs → UPC research → OAuth Scopes → add that scope.
# Falls back to Browse API item search if catalog scope is not yet enabled.

_ebay_token_cache: dict = {}  # keyed by (client_id, scope)


def _ebay_credentials():
    try:
        import streamlit as st
        return st.secrets.get("EBAY_CLIENT_ID", ""), st.secrets.get("EBAY_CERT_ID", "")
    except Exception:
        pass
    return os.environ.get("EBAY_CLIENT_ID", ""), os.environ.get("EBAY_CERT_ID", "")


def _ebay_token(client_id, cert_id, scope):
    import base64, time
    cache_key = f"{client_id}:{scope}"
    cached = _ebay_token_cache.get(cache_key, {})
    if cached.get("token") and cached.get("expires_at", 0) > time.time() + 60:
        return cached["token"]

    sandbox = "SBX" in client_id
    base    = "https://api.sandbox.ebay.com" if sandbox else "https://api.ebay.com"
    creds   = base64.b64encode(f"{client_id}:{cert_id}".encode()).decode()

    r = requests.post(
        f"{base}/identity/v1/oauth2/token",
        data={"grant_type": "client_credentials", "scope": scope},
        headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    data    = r.json()
    token   = data.get("access_token")
    expires = data.get("expires_in", 7200)
    if token:
        _ebay_token_cache[cache_key] = {"token": token, "expires_at": time.time() + expires}
    return token


def ebay_lookup(upc):
    """eBay UPC lookup — two strategies tried in order:

    1. Browse API item_summary/search?q={upc}  (basic scope, always available)
       Searches live listings by UPC as keyword; picks the listing whose title
       most likely represents the canonical product.

    2. Catalog API product_summary/search?gtin={upc}  (commerce.catalog.readonly)
       Exact GTIN match against eBay's product catalog.  Requires the scope to
       be enabled on the app by eBay Developer Support.
    """
    client_id, cert_id = _ebay_credentials()
    if not client_id or not cert_id:
        return None
    try:
        sandbox  = "SBX" in client_id
        base     = "https://api.sandbox.ebay.com" if sandbox else "https://api.ebay.com"
        h_base   = {"X-EBAY-C-MARKETPLACE-ID": "EBAY_US", "Accept": "application/json"}

        # ── Strategy 1: Browse API (basic scope — no special access needed) ──
        browse_scope = "https://api.ebay.com/oauth/api_scope"
        browse_token = _ebay_token(client_id, cert_id, browse_scope)
        if browse_token:
            h = {**h_base, "Authorization": f"Bearer {browse_token}"}
            r = requests.get(
                f"{base}/buy/browse/v1/item_summary/search",
                params={"q": upc, "limit": "5"},
                headers=h,
                timeout=10,
            )
            if r.status_code == 200:
                items = r.json().get("itemSummaries", [])
                # Filter out noisy listings (accessories, "for", "compatible with")
                _noise = ("for ", "compatible", "case for", "replacement", "repair")
                clean  = [i for i in items if not any(n in i.get("title", "").lower() for n in _noise)]
                pick   = (clean or items)[:1]
                if pick:
                    item  = pick[0]
                    title = item.get("title", "").strip()
                    brand_raw = item.get("brand")
                    brand = brand_raw.get("brandName", "").strip() if isinstance(brand_raw, dict) else str(brand_raw or "").strip()
                    parts = [v for v in [title, brand] if v]
                    if parts:
                        return "\n".join(parts)

        # ── Strategy 2: Catalog API (commerce.catalog.readonly scope) ──
        cat_scope = "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly"
        cat_token = _ebay_token(client_id, cert_id, cat_scope)
        if not cat_token:
            return None

        h = {**h_base, "Authorization": f"Bearer {cat_token}"}
        r_search = requests.get(
            f"{base}/commerce/catalog/v1_beta/product_summary/search",
            params={"gtin": upc},
            headers=h,
            timeout=10,
        )
        if r_search.status_code != 200:
            return None

        prods = r_search.json().get("productSummaries", [])
        if not prods:
            return None

        epid = prods[0].get("epid")
        if not epid:
            p     = prods[0]
            parts = [v for v in [p.get("title", ""), p.get("brand", "")] if v]
            return "\n".join(parts) or None

        r_detail = requests.get(
            f"{base}/commerce/catalog/v1_beta/product/{epid}",
            headers=h,
            timeout=10,
        )
        if r_detail.status_code != 200:
            p     = prods[0]
            parts = [v for v in [p.get("title", ""), p.get("brand", "")] if v]
            return "\n".join(parts) or None

        prod  = r_detail.json()
        title = prod.get("title", "").strip()
        brand = prod.get("brand", "").strip()
        desc  = prod.get("description", "").strip()

        aspect_parts = []
        for asp in (prod.get("aspects") or [])[:5]:
            name = asp.get("localizedName", "")
            vals = asp.get("localizedValues", [])
            if name and vals and len(vals[0]) < 40:
                aspect_parts.append(f"{name}: {', '.join(vals[:2])}")

        parts = [v for v in [title, brand, desc] if v]
        if aspect_parts:
            parts.append(" | ".join(aspect_parts))
        return "\n".join(parts) or None

    except Exception:
        return None


def whole_foods_lookup(upc):
    """Whole Foods UPC search via Playwright.
    Works when running locally with a US IP. From non-US servers, Cloudflare
    redirects all traffic to the UK site regardless of headers or geolocation,
    so this will return None gracefully in that environment.
    """
    return _playwright_search(
        f"https://www.wholefoodsmarket.com/search?text={upc}",
        [
            ".w-pie--product-tile__title",
            "h2.product-name",
            "[data-testid='product-title']",
        ]
    )


def goupc_lookup(upc):
    """go-upc.com — free, no auth, broad UPC database."""
    if not _PLAYWRIGHT_AVAILABLE:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )
            page = context.new_page()
            _STEALTH.apply_stealth_sync(page)

            page.goto(f"https://go-upc.com/search?q={upc}", timeout=30000, wait_until="domcontentloaded")
            page.evaluate("window.scrollBy(0, 200)")
            page.wait_for_timeout(3000)

            parts = []
            for sel in ["h1", ".product-name", "[class*='brand']", "[class*='description']"]:
                try:
                    texts = page.locator(sel).all_inner_texts()
                    for t in texts:
                        t = t.strip()
                        if t and t not in parts:
                            parts.append(t)
                            break
                except Exception:
                    pass

            browser.close()
            return "\n".join(parts) or None
    except Exception:
        return None


def duckduckgo_lookup(upc):
    """DuckDuckGo HTML search — free, no auth.
    The Instant Answers API returns nothing for raw UPCs (it only handles named
    entities). The HTML endpoint surfaces UPC-specific pages as top results and
    is parseable with plain regex.
    """
    try:
        import re
        r = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": f"{upc} UPC"},
            headers={
                "User-Agent":      USER_AGENT,
                "Accept":          "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=12,
        )
        if r.status_code != 200:
            return None

        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text, re.DOTALL)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', r.text, re.DOTALL)

        from html import unescape
        title   = unescape(re.sub(r"<[^>]+>", "", titles[0])).strip()   if titles   else ""
        snippet = unescape(re.sub(r"<[^>]+>", "", snippets[0])).strip() if snippets else ""

        parts = [v for v in [title, snippet] if v]
        return "\n".join(parts) or None
    except Exception:
        return None


def spoonacular_lookup(upc):
    try:
        import streamlit as st
        api_key = st.secrets.get("SPOONACULAR_API_KEY", "")
    except Exception:
        api_key = os.environ.get("SPOONACULAR_API_KEY", "")

    if not api_key:
        return None

    try:
        r = requests.get(
            f"https://api.spoonacular.com/food/products/upc/{upc}",
            params={"apiKey": api_key},
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if r.status_code != 200:
            return None

        data = r.json()
        parts = [
            data.get("title", ""),
            data.get("brand", ""),
            data.get("description", ""),
        ]
        # Pull serving/package size from nutrition info if available
        serving = data.get("servings", {})
        if serving.get("size") and serving.get("unit"):
            parts.append(f"{serving['size']} {serving['unit']}")

        return "\n".join(v for v in parts if v) or None
    except Exception:
        return None


def open_food_facts_lookup(upc):
    try:
        r = requests.get(
            f"https://world.openfoodfacts.org/api/v0/product/{upc}.json",
            headers={"User-Agent": "CPGEnrichmentEngine/1.0"},
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


def nutritionix_lookup(upc):
    """Nutritionix food database — UPC-native lookup, accurate brand + serving info.
    Register free at https://www.nutritionix.com/business/api (200 UPC calls/day).
    Add NUTRITIONIX_APP_ID and NUTRITIONIX_APP_KEY to .streamlit/secrets.toml.
    """
    try:
        import streamlit as st
        app_id  = st.secrets.get("NUTRITIONIX_APP_ID", "")
        app_key = st.secrets.get("NUTRITIONIX_APP_KEY", "")
    except Exception:
        app_id  = os.environ.get("NUTRITIONIX_APP_ID", "")
        app_key = os.environ.get("NUTRITIONIX_APP_KEY", "")

    if not app_id or not app_key:
        return None

    try:
        r = requests.get(
            "https://trackapi.nutritionix.com/v2/search/item",
            params={"upc": upc},
            headers={
                "x-app-id":  app_id,
                "x-app-key": app_key,
                "User-Agent": USER_AGENT,
            },
            timeout=10,
        )
        if r.status_code != 200:
            return None

        foods = r.json().get("foods", [])
        if not foods:
            return None

        f = foods[0]
        food_name  = f.get("food_name", "").strip()
        brand_name = f.get("brand_name", "").strip()
        qty        = f.get("serving_qty", "")
        unit       = f.get("serving_unit", "").strip()
        size       = f"{qty} {unit}".strip() if qty and unit else ""

        parts = [v for v in [brand_name, food_name, size] if v]
        return "\n".join(parts) or None
    except Exception:
        return None
