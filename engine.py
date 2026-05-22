from retailers import (
    amazon_lookup,
    ebay_lookup,
    target_lookup,
    kroger_lookup,
    iherb_lookup,
    serpapi_amazon_lookup,
    walmart_lookup,
    walgreens_lookup,
    vitacost_lookup,
    usda_lookup,
    barcodelookup_lookup,
    whole_foods_lookup,
    goupc_lookup,
    duckduckgo_lookup,
    spoonacular_lookup,
    open_food_facts_lookup,
    nutritionix_lookup,
)
from claude_parser import extract_product_with_claude
from ai import similarity

# Fast API sources first, then Playwright scrapers, fallbacks last.
# eBay sandbox credentials are active — returns no data until switched to
# production keys (EBAY_CLIENT_ID without "SBX" prefix).
RETAILER_CHAIN = [
    ("Target",          target_lookup,          False),
    ("UPCitemdb",       amazon_lookup,          False),
    ("Open Food Facts", open_food_facts_lookup, False),
    ("Spoonacular",     spoonacular_lookup,     False),
    ("Barcode Lookup",  barcodelookup_lookup,   False),
    ("Go-UPC",          goupc_lookup,           False),
    ("Amazon",          serpapi_amazon_lookup,  False),
    ("Walmart",         walmart_lookup,         False),
    # ("Nutritionix",     nutritionix_lookup,     False),
    # ("iHerb",           iherb_lookup,           False),
    # ("Kroger",          kroger_lookup,          False),
    # ("eBay",            ebay_lookup,            False),
    # ("Walgreens",       walgreens_lookup,       False),
    # ("Vitacost",        vitacost_lookup,        False),
    # ("Whole Foods",     whole_foods_lookup,     False),
    # ("USDA FoodData",   usda_lookup,            True),
    # ("DuckDuckGo",      duckduckgo_lookup,      True),
]


def _normalize_upc(raw):
    s = str(raw).strip()
    if "." in s:
        s = s.split(".")[0]
    s = "".join(c for c in s if c.isdigit())
    return s.zfill(12)


def _cpg_match(cpg_provided, cpg_verified):
    if not cpg_provided or not cpg_verified:
        return "Not Found"
    score = similarity(cpg_provided, cpg_verified)
    return "Verified" if score >= 0.65 else "Differs"


def _brand_equals_cpg(brand, cpg_provided):
    if not brand or not cpg_provided:
        return "NA"
    score = similarity(brand, cpg_provided)
    if score >= 0.65:
        return "Yes"
    b = brand.lower()
    c = cpg_provided.lower()
    if b in c or c in b:
        return "Yes"
    return "No"


def _build_description(parsed):
    brand        = (parsed.get("brand") or "").strip()
    product_name = (parsed.get("product_name") or "").strip()
    quantity     = (parsed.get("quantity") or "").strip()
    size         = (parsed.get("size") or "").strip()

    # Skip brand prefix if product_name already contains it
    # e.g. brand="ZOA", product_name="ZOA Super Berry..." → don't prepend ZOA again
    if brand and product_name.lower().startswith(brand.lower()):
        name_part = product_name
    else:
        name_part = f"{brand} {product_name}".strip()

    # Format: "ZOA Super Berry Energy Drink 12/12 oz"
    if quantity and size:
        pack = f"{quantity}/{size}"
    else:
        pack = quantity or size

    parts = [p for p in [name_part, pack] if p]
    return " ".join(parts)


def _build_result(upc_raw, full_upc, cpg_provided, parsed, source_label):
    brand = parsed.get("brand") or ""

    return {
        "upc_input":           str(upc_raw),
        "full_upc":            full_upc,
        "cpg_provided":        cpg_provided,
        "cpg_verified":        parsed.get("cpg_company") or "",
        "cpg_match":           _cpg_match(cpg_provided, parsed.get("cpg_company") or ""),
        "brand":               brand,
        "product_description": _build_description(parsed),
        "sources":             source_label,
        "brand_equals_cpg":    _brand_equals_cpg(brand, cpg_provided),
        "relationship":        "Not Found",
        "status":              "Success",
    }


def process_upc(upc_raw, cpg_provided="", on_source_check=None):

    full_upc = _normalize_upc(upc_raw)

    for retailer_name, lookup_fn, is_fallback in RETAILER_CHAIN:
        if on_source_check:
            on_source_check(retailer_name)

        raw_text = lookup_fn(full_upc)
        if not raw_text:
            continue

        parsed = extract_product_with_claude(raw_text, retailer_name)
        if not parsed:
            continue

        source_label = f"{retailer_name} (fallback)" if is_fallback else retailer_name
        return _build_result(upc_raw, full_upc, cpg_provided, parsed, source_label)

    return {
        "upc_input":           str(upc_raw),
        "full_upc":            full_upc,
        "cpg_provided":        cpg_provided,
        "cpg_verified":        None,
        "cpg_match":           "Not Found",
        "brand":               None,
        "product_description": None,
        "sources":             None,
        "brand_equals_cpg":    "NA",
        "relationship":        "Not Found",
        "status":              "Not Found",
    }
