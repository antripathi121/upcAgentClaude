import re


# -----------------------------
# CLEAN TEXT
# -----------------------------
def clean(text):
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# -----------------------------
# BRAND EXTRACTION (simple heuristic)
# -----------------------------
def extract_brand(product_text):

    text = clean(product_text)
    words = text.split()

    if len(words) == 0:
        return "Unknown"

    # first word is usually brand in retail titles
    return words[0].title()


# -----------------------------
# MAIN FUNCTION (THIS IS WHAT APP NEEDS)
# -----------------------------
def normalize_product(amazon, target, kroger, iherb):

    candidates = [
        amazon,
        target,
        kroger,
        iherb
    ]

    best = None

    for c in candidates:
        if c and "no" not in c.lower() and "error" not in c.lower():
            best = c
            break

    if not best:
        return {
            "product_name": "Not Found",
            "brand": "Unknown",
            "source": "None"
        }

    return {
        "product_name": best,
        "brand": extract_brand(best),
        "source": "Retailer"
    }