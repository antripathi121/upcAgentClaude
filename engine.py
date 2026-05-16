from retailers import (
    amazon_lookup,
    target_lookup,
    kroger_lookup,
    frysfood_lookup,
    iherb_lookup,
    walmart_lookup,
    walgreens_lookup,
    usda_lookup,
    barcodelookup_lookup,
    vitacost_lookup,
    open_food_facts_lookup,
)
from claude_parser import extract_product_with_claude
from ai import similarity

RETAILER_CHAIN = [
    ("Amazon",          amazon_lookup,          False),
    ("Target",          target_lookup,          False),
    ("Kroger",          kroger_lookup,          False),
    ("Frysfood",        frysfood_lookup,        False),
    ("iHerb",           iherb_lookup,           False),
    ("Walmart",         walmart_lookup,         False),
    ("Walgreens",       walgreens_lookup,       False),
    ("USDA FoodData",   usda_lookup,            True),
    ("Barcode Lookup",  barcodelookup_lookup,   False),
    ("Vitacost",        vitacost_lookup,        False),
    ("Open Food Facts", open_food_facts_lookup, True),
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

        brand        = parsed.get("brand") or ""
        product_name = parsed.get("product_name") or ""
        size         = parsed.get("size") or ""
        quantity     = parsed.get("quantity") or ""
        description  = parsed.get("description") or product_name
        cpg_verified = parsed.get("cpg_company") or ""

        source_label = f"{retailer_name} (fallback)" if is_fallback else retailer_name

        return {
            "upc_input":       str(upc_raw),
            "full_upc":        full_upc,
            "cpg_provided":    cpg_provided,
            "cpg_verified":    cpg_verified,
            "cpg_match":       _cpg_match(cpg_provided, cpg_verified),
            "brand":           brand,
            "size":            size,
            "quantity":        quantity,
            "product_description": description,
            "sources":         source_label,
            "brand_equals_cpg": _brand_equals_cpg(brand, cpg_provided),
            "relationship":    "Not Found",
            "status":          "Success",
        }

    return {
        "upc_input":       str(upc_raw),
        "full_upc":        full_upc,
        "cpg_provided":    cpg_provided,
        "cpg_verified":    None,
        "cpg_match":       "Not Found",
        "brand":           None,
        "size":            None,
        "quantity":        None,
        "product_description": None,
        "sources":         None,
        "brand_equals_cpg": "NA",
        "relationship":    "Not Found",
        "status":          "Not Found",
    }
