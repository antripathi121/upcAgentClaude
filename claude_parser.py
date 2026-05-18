import anthropic
import os
import json
import re


def _get_api_key():
    try:
        import streamlit as st
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY", "")


def _client():
    return anthropic.Anthropic(api_key=_get_api_key())


def extract_product_with_claude(raw_text, retailer):

    if not raw_text:
        return None

    prompt = f"""You are a product data extraction system for CPG items.

Extract structured product information from the retailer text below.

Return ONLY valid JSON with exactly these fields:
- "brand": consumer-facing brand name printed on the product
- "product_name": full product name/title
- "size": net weight or volume of a single unit — extract from title, weight, or offer text (e.g. "12 oz", "10 oz", "500g"). Use null only if truly absent.
- "quantity": number of units or pack count — extract from title or offer text (e.g. "12 count", "6-pack", "24 ct"). Use null only if truly absent.
- "description": 1-2 sentence product description
- "cpg_company": the manufacturer or parent CPG company name

Retailer source: {retailer}

TEXT:
{raw_text}

Respond with ONLY the JSON object, no markdown, no explanation."""

    response = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"brand": None, "product_name": raw, "size": None, "quantity": None, "description": None, "cpg_company": None}


def claude_direct_upc_lookup(upc):
    """Use Claude's training knowledge to identify a product directly from its UPC."""

    prompt = f"""You are a product identification system with knowledge of CPG product barcodes.

UPC barcode: {upc}

Using your training knowledge:
1. Identify the manufacturer from the GS1 company prefix (the first 6-10 digits of the UPC)
2. If you recognise this specific UPC, provide full product details
3. If you only know the company prefix, provide the company info with low confidence

Return ONLY valid JSON with exactly these fields:
- "brand": consumer-facing brand name (or null if unknown)
- "product_name": product name (or null if unknown)
- "size": size/weight/volume (or null)
- "quantity": pack count (or null)
- "description": brief description (or null)
- "cpg_company": the manufacturer/parent company name
- "confidence": "high", "medium", or "low"

Return null (not JSON) only if you have absolutely no information about this UPC or its prefix."""

    response = _client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    if raw.lower().strip() in ("null", "none", ""):
        return None

    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
