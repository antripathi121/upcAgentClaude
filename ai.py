import re
from difflib import SequenceMatcher


# -----------------------------
# CLEAN TEXT
# -----------------------------
def clean(text):

    text = str(text).lower()

    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


# -----------------------------
# SIMILARITY
# -----------------------------
def similarity(a, b):

    a = clean(a)
    b = clean(b)

    return SequenceMatcher(None, a, b).ratio()


# -----------------------------
# BRAND CHECK
# -----------------------------
def brand_match(expected_cpg, text):

    expected_cpg = clean(expected_cpg)
    text = clean(text)

    if expected_cpg in text:
        return True

    score = similarity(expected_cpg, text)

    return score >= 0.65


# -----------------------------
# VERIFICATION ENGINE
# -----------------------------
def ai_score(expected_cpg, gs1, amazon, target, kroger, iherb):

    evidence = [
        gs1,
        amazon,
        target,
        kroger,
        iherb
    ]

    total_score = 0
    matched_sources = []

    for e in evidence:

        if not e:
            continue

        score = similarity(expected_cpg, e)

        if score >= 0.65:
            total_score += score
            matched_sources.append(e)

    # -----------------------------
    # DECISION LOGIC
    # -----------------------------
    if total_score >= 2:
        label = "VERIFIED MATCH"

    elif total_score >= 1:
        label = "PARTIAL MATCH"

    else:
        label = "MISMATCH"

    confidence = round(min(total_score / 2, 1) * 100, 2)

    return confidence, label