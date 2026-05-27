import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import subprocess
import sys
import os
import json
import hashlib
import datetime
import base64


@st.cache_resource(show_spinner=False)
def _install_playwright_browser():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
    )

_install_playwright_browser()

from engine import process_upc

# ── History helpers ────────────────────────────────────────────────────────────

HISTORY_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history")
HISTORY_INDEX = os.path.join(HISTORY_DIR, "index.json")

def _ensure_history():
    os.makedirs(HISTORY_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_INDEX):
        with open(HISTORY_INDEX, "w") as f:
            json.dump({}, f)

def _load_index():
    _ensure_history()
    with open(HISTORY_INDEX, "r") as f:
        return json.load(f)

def _save_run(file_hash, original_name, results):
    _ensure_history()
    ts        = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in original_name)
    csv_name  = f"{ts}_{safe_name}.csv"
    csv_path  = os.path.join(HISTORY_DIR, csv_name)
    pd.DataFrame(results).to_csv(csv_path, index=False)

    verified = sum(1 for r in results if r["cpg_match"] == "Verified")
    differs  = sum(1 for r in results if r["cpg_match"] == "Differs")
    errors   = sum(1 for r in results if r["status"]   == "Error")

    index = _load_index()
    index[file_hash] = {
        "original_name": original_name,
        "processed_at":  datetime.datetime.now().isoformat(),
        "csv_file":      csv_name,
        "total":         len(results),
        "verified":      verified,
        "differs":       differs,
        "errors":        errors,
    }
    with open(HISTORY_INDEX, "w") as f:
        json.dump(index, f, indent=2)
    return csv_path

def _file_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()

def _load_run(csv_name):
    path = os.path.join(HISTORY_DIR, csv_name)
    if os.path.exists(path):
        return pd.read_csv(path).to_dict("records")
    return None

def _auto_download(csv_bytes, filename):
    """Trigger browser download automatically via inline JS."""
    b64 = base64.b64encode(csv_bytes).decode()
    components.html(
        f'<a id="auto-dl" href="data:text/csv;base64,{b64}" download="{filename}"></a>'
        f'<script>document.getElementById("auto-dl").click();</script>',
        height=0,
    )

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="KACU UPC Enrichment Engine",
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

  .hist-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 10px;
    font-size: 0.82rem;
  }
  .hist-name { font-weight: 600; color: #e6edf3; word-break: break-all; }
  .hist-meta { color: #8b949e; margin-top: 3px; }

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

# ── Sidebar: processing history ────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Processing History")
    index = _load_index()
    if not index:
        st.markdown("<div style='color:#8b949e;font-size:0.82rem'>No runs yet.</div>", unsafe_allow_html=True)
    else:
        for fhash, meta in sorted(index.items(), key=lambda x: x[1]["processed_at"], reverse=True):
            ts_raw = meta["processed_at"]
            try:
                ts = datetime.datetime.fromisoformat(ts_raw).strftime("%b %d %Y  %H:%M")
            except Exception:
                ts = ts_raw[:16]

            st.markdown(f"""
            <div class="hist-card">
              <div class="hist-name">{meta['original_name']}</div>
              <div class="hist-meta">{ts} &nbsp;·&nbsp;
                {meta['total']} UPCs &nbsp;·&nbsp;
                <span style="color:#4ade80">{meta['verified']} verified</span> &nbsp;·&nbsp;
                <span style="color:#fbbf24">{meta['differs']} differs</span> &nbsp;·&nbsp;
                <span style="color:#f87171">{meta['errors']} errors</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

            hist_csv_path = os.path.join(HISTORY_DIR, meta["csv_file"])
            if os.path.exists(hist_csv_path):
                with open(hist_csv_path, "rb") as f:
                    hist_bytes = f.read()
                st.download_button(
                    label="⬇ Re-download",
                    data=hist_bytes,
                    file_name=meta["csv_file"],
                    mime="text/csv",
                    key=f"hist_{fhash}",
                )

# ── Main area ──────────────────────────────────────────────────────────────────

st.title("KACU UPC Enrichment Engine")
st.markdown("<div style='color:#8b949e;margin-bottom:1.5rem'>Upload an Excel file with UPC and CPG columns to enrich product data.</div>", unsafe_allow_html=True)

file = st.file_uploader("Upload Excel (.xlsx)", type=["xlsx"])


def _render_table(results):
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

    return display.style.map(style_match, subset=["CPG MATCH?"])


def _show_completed(results, total, auto_dl_filename=None):
    verified = sum(1 for r in results if r["cpg_match"] == "Verified")
    differs  = sum(1 for r in results if r["cpg_match"] == "Differs")
    errors   = sum(1 for r in results if r["status"]   == "Error")

    st.markdown(f"""
    <div style="display:flex;gap:12px;margin-bottom:18px;">
      <div class="stat-card" style="flex:1"><div class="stat-num">{total}</div><div class="stat-label">Total UPCs</div></div>
      <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#4ade80">{verified}</div><div class="stat-label">Verified</div></div>
      <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#60a5fa">{verified}</div><div class="stat-label">CPG Matched</div></div>
      <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#fbbf24">{differs}</div><div class="stat-label">CPG Differs</div></div>
      <div class="stat-card" style="flex:1"><div class="stat-num" style="color:#f87171">{errors}</div><div class="stat-label">Errors</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="progress-card" style="border-color:#238636">
      <div class="progress-title" style="color:#4ade80">✓ Processing complete — {total} UPCs processed</div>
      <div style="background:#21262d;border-radius:999px;height:6px;margin:8px 0">
        <div style="background:#238636;height:6px;border-radius:999px;width:100%"></div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.dataframe(_render_table(results), use_container_width=True, height=500)

    csv_bytes = pd.DataFrame(results).to_csv(index=False).encode("utf-8")
    filename  = auto_dl_filename or "cpg_enrichment_output.csv"

    if auto_dl_filename:
        _auto_download(csv_bytes, filename)

    st.download_button("⬇ Download CSV", csv_bytes, filename, "text/csv")


if file:
    file_bytes = file.getvalue()
    fhash      = _file_hash(file_bytes)

    # ── Already processed this exact file (session) ────────────────────────────
    if st.session_state.get("file_hash") == fhash and st.session_state.get("results"):
        _show_completed(st.session_state["results"], len(st.session_state["results"]))
        st.stop()

    # ── Already processed this exact file (history on disk) ───────────────────
    idx_entry = _load_index().get(fhash)
    if idx_entry:
        past_results = _load_run(idx_entry["csv_file"])
        if past_results:
            st.info(f"This file was already processed on {idx_entry['processed_at'][:16].replace('T', ' ')}. Showing saved results — no credits used.")
            st.session_state["file_hash"] = fhash
            st.session_state["results"]   = past_results
            _show_completed(past_results, idx_entry["total"])
            st.stop()

    # ── New file: process UPCs ─────────────────────────────────────────────────
    df = pd.read_excel(file)
    df.columns = df.columns.str.strip()

    upc_col = next((c for c in df.columns if c.upper() in ("UPC", "UPC INPUT", "UPC_INPUT")), None)
    cpg_col = next((c for c in df.columns if "CPG" in c.upper()), None)

    if upc_col is None:
        st.error(f"No UPC column found. Detected columns: {list(df.columns)}")
        st.stop()

    total = len(df)

    progress_box = st.empty()
    stats_box    = st.empty()
    table_box    = st.empty()

    results   = []
    verified  = 0
    matched   = 0
    differs   = 0
    errors    = 0

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

        def on_source(name, _idx=idx, _upc=upc_raw):
            progress_box.markdown(f"""
            <div class="progress-card">
              <div class="progress-title">Researching UPC {_idx + 1} of {total}...</div>
              <div style="background:#21262d;border-radius:999px;height:6px;margin:8px 0">
                <div style="background:#238636;height:6px;border-radius:999px;width:{round((_idx + 1) / total * 100)}%"></div>
              </div>
              <div class="progress-sub">{_upc} &nbsp;·&nbsp; Checking {name}...</div>
            </div>
            """, unsafe_allow_html=True)

        on_source("Target")

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

        results.append(result)
        render_stats()
        table_box.dataframe(_render_table(results), use_container_width=True, height=500)

    # ── Processing complete: save + auto-download ──────────────────────────────
    ts_str    = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in file.name)
    dl_name   = f"{ts_str}_{safe_name}.csv"

    _save_run(fhash, file.name, results)

    st.session_state["file_hash"] = fhash
    st.session_state["results"]   = results

    progress_box.empty()
    stats_box.empty()
    table_box.empty()

    _show_completed(results, total, auto_dl_filename=dl_name)
