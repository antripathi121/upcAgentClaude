import streamlit as st
import pandas as pd
import subprocess
import sys


@st.cache_resource(show_spinner=False)
def _install_playwright_browser():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
    )

_install_playwright_browser()

from engine import process_upc

st.set_page_config(
    page_title="CPG Product Enrichment Engine",
    layout="wide",
    page_icon="🔍",
)

st.markdown("""
<style>
  .stApp { background-color: #0d1117; color: #e6edf3; }
  section[data-testid="stSidebar"] { background-color: #161b22; }
  .block-container { padding-top: 2rem; }

  .stat-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 18px 22px;
    text-align: center;
  }
  .stat-num  { font-size: 2.2rem; font-weight: 700; line-height: 1.1; }
  .stat-label{ font-size: 0.78rem; color: #8b949e; margin-top: 4px; text-transform: uppercase; letter-spacing: .05em; }

  .progress-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 18px 24px;
    margin-bottom: 18px;
  }
  .progress-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 6px; }
  .progress-sub   { font-size: 0.8rem; color: #8b949e; margin-top: 8px; font-family: monospace; }

  .badge-verified { background:#166534; color:#4ade80; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; }
  .badge-differs  { background:#78350f; color:#fbbf24; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; }
  .badge-notfound { background:#1f2937; color:#9ca3af; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:600; }

  div[data-testid="stDataFrame"] { border: 1px solid #30363d; border-radius: 8px; }
  .stDataFrame thead th { background:#161b22 !important; color:#8b949e !important; font-size:.72rem; text-transform:uppercase; }
  .stDataFrame tbody tr:hover td { background:#1c2128 !important; }

  h1 { color:#e6edf3 !important; }
  .stFileUploader label { color:#e6edf3 !important; }
  [data-testid="stMetricValue"] { color:#e6edf3 !important; }
</style>
""", unsafe_allow_html=True)

st.title("KACU UPC Enrichment Engine")
st.markdown("<div style='color:#8b949e;margin-bottom:1.5rem'>Upload an Excel file with UPC and CPG columns to enrich product data.</div>", unsafe_allow_html=True)

file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])

if file:
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()

    # --- locate columns ---
    upc_col = next((c for c in df.columns if c.upper() in ("UPC", "UPC INPUT", "UPC_INPUT")), None)
    cpg_col = next((c for c in df.columns if "CPG" in c.upper()), None)

    if upc_col is None:
        st.error(f"No UPC column found. Detected columns: {list(df.columns)}")
        st.stop()

    total = len(df)

    # --- layout: progress + stats ---
    progress_box = st.empty()
    stats_box    = st.empty()
    table_box    = st.empty()

    results   = []
    verified  = 0
    matched   = 0
    differs   = 0
    errors    = 0
    not_found = 0

    RETAILER_LABELS = "Amazon · Target · Kroger · iHerb · Fry's Food · Walmart · Walgreens · USDA · Barcode Lookup · Vitacost · Open Food Facts"

    def render_stats():
        stats_box.markdown(f"""
        <div style="display:flex;gap:12px;margin-bottom:18px;">
          <div class="stat-card" style="flex:1"><div class="stat-num">{total}</div><div class="stat-label">Total UPCs</div></div>
          <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#4ade80">{verified}</div><div class="stat-label">Verified</div></div>
          <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#60a5fa">{matched}</div><div class="stat-label">CPG Matched</div></div>
          <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#fbbf24">{differs}</div><div class="stat-label">CPG Differs</div></div>
          <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#f87171">{errors}</div><div class="stat-label">Errors</div></div>
        </div>
        """, unsafe_allow_html=True)

    render_stats()

    for idx, row in df.iterrows():
        upc_raw      = row[upc_col]
        cpg_provided = str(row[cpg_col]).strip() if cpg_col else ""

        current_source = {"name": "Amazon"}

        def on_source(name):
            current_source["name"] = name
            progress_box.markdown(f"""
            <div class="progress-card">
              <div class="progress-title">Researching UPC {idx + 1} of {total}...</div>
              <div style="background:#21262d;border-radius:999px;height:6px;margin:8px 0">
                <div style="background:#238636;height:6px;border-radius:999px;width:{round((idx + 1) / total * 100)}%"></div>
              </div>
              <div class="progress-sub">{upc_raw} &nbsp;·&nbsp; Checking {name}...</div>
            </div>
            """, unsafe_allow_html=True)

        on_source("Amazon")

        try:
            result = process_upc(upc_raw, cpg_provided, on_source_check=on_source)
        except Exception as e:
            result = {
                "upc_input": str(upc_raw), "full_upc": str(upc_raw),
                "cpg_provided": cpg_provided, "cpg_verified": None,
                "cpg_match": "Error", "brand": None,
                "product_description": str(e),
                "sources": None, "brand_equals_cpg": "NA",
                "relationship": "Not Found", "status": "Error",
            }
            errors += 1

        if result["status"] != "Error":
            if result["cpg_match"] == "Verified":
                verified += 1
                matched  += 1
            elif result["cpg_match"] == "Differs":
                differs  += 1
            elif result["status"] == "Not Found":
                not_found += 1

        results.append(result)
        render_stats()

        # Build display dataframe
        display = pd.DataFrame(results)
        display.index = range(1, len(display) + 1)
        display.index.name = "#"

        display = display.rename(columns={
            "upc_input":           "UPC INPUT",
            "full_upc":            "FULL UPC",
            "cpg_provided":        "CPG PROVIDED",
            "cpg_verified":        "CPG VERIFIED",
            "cpg_match":           "CPG MATCH?",
            "brand":               "BRAND",
            "product_description": "PRODUCT DESCRIPTION",
            "sources":             "SOURCES",
            "brand_equals_cpg":    "BRAND = CPG?",
            "relationship":        "RELATIONSHIP",
        })

        cols_order = ["UPC INPUT","FULL UPC","CPG PROVIDED","CPG VERIFIED",
                      "CPG MATCH?","BRAND","PRODUCT DESCRIPTION","SOURCES",
                      "BRAND = CPG?","RELATIONSHIP"]
        display = display[[c for c in cols_order if c in display.columns]]

        def style_match(val):
            if val == "Verified":
                return "background-color:#166534; color:#4ade80; font-weight:600; border-radius:4px; padding:2px 6px;"
            if val == "Differs":
                return "background-color:#78350f; color:#fbbf24; font-weight:600; border-radius:4px; padding:2px 6px;"
            if val == "Not Found":
                return "color:#6b7280;"
            return ""

        styled = display.style.map(style_match, subset=["CPG MATCH?"])
        table_box.dataframe(styled, use_container_width=True, height=500)

    # Final progress cleared, show completion
    progress_box.markdown(f"""
    <div class="progress-card" style="border-color:#238636">
      <div class="progress-title" style="color:#4ade80">✓ Processing complete — {total} UPCs processed</div>
      <div style="background:#21262d;border-radius:999px;height:6px;margin:8px 0">
        <div style="background:#238636;height:6px;border-radius:999px;width:100%"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Download
    final_df = pd.DataFrame(results)
    csv = final_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇ Download CSV", csv, "cpg_enrichment_output.csv", "text/csv")
