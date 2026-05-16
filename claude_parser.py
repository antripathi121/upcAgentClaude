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


client = anthropic.Anthropic(api_key=_get_api_key())


def extract_product_with_claude(raw_text, retailer):

    if not raw_text:
        return None

    prompt = f"""You are a product data extraction system for CPG items.

Extract structured product information from the retailer text below.

Return ONLY valid JSON with exactly these fields:
- "brand": consumer-facing brand name printed on the product
- "product_name": full product name/title
- "size": size, weight, or volume (e.g. "12 oz", "500g", "1 lb")
- "quantity": pack count if applicable (e.g. "6-pack", "24 count"), otherwise null
- "description": 1-2 sentence product description
- "cpg_company": the manufacturer or parent CPG company name

Retailer source: {retailer}

TEXT:
{raw_text}

Respond with ONLY the JSON object, no markdown, no explanation."""

    response = client.messages.create(
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
