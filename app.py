import hashlib
import html
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import streamlit as st

from verifact.client import MODEL, make_client
from verifact.extract import extract_claims
from verifact.verify import Verdict, verify_claim

MAX_PDF_MB = 20
WORKERS = 6
SAMPLE_PDF = Path(__file__).parent / "samples" / "trap_document.pdf"

# verdict -> (css modifier, icon, label)
VERDICT_STYLE = {
    "False": ("false", "✕", "False"),
    "Inaccurate": ("inaccurate", "!", "Inaccurate"),
    "Verified": ("verified", "✓", "Verified"),
    "Error": ("error", "–", "Could not check"),
}
ORDER = {"False": 0, "Inaccurate": 1, "Error": 2, "Verified": 3}

st.set_page_config(page_title="VeriFact · PDF Fact-Checker", page_icon="🔎", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
  --vf-ink: #0f172a;
  --vf-muted: #64748b;
  --vf-line: #e2e8f0;
  --vf-surface: #ffffff;
  --vf-soft: #f8fafc;
  --vf-accent: #4f46e5;
  --vf-verified: #15803d;  --vf-verified-bg: #f0fdf4;
  --vf-inaccurate: #c2410c; --vf-inaccurate-bg: #fff7ed;
  --vf-false: #b91c1c;     --vf-false-bg: #fef2f2;
  --vf-error: #64748b;     --vf-error-bg: #f1f5f9;
}
.stApp { font-family: 'Inter', sans-serif; background: var(--vf-soft); color: var(--vf-ink); }
.stApp p, .stApp label, .stApp li, .stApp h3, .stApp button, .stApp input,
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"] { font-family: 'Inter', sans-serif; }
[data-testid="stMainBlockContainer"], .block-container { max-width: 1080px; padding-top: 4.5rem; }
[data-testid="stHeader"] { background: transparent; }
footer, [data-testid="stAppDeployButton"] { display: none; }

/* Hero */
.vf-hero {
  background: radial-gradient(1200px 400px at 85% -20%, rgba(129,140,248,.45), transparent 60%),
              linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
  border-radius: 20px; padding: 40px 44px 34px; color: #fff; margin-bottom: 28px;
}
.vf-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #a5b4fc; }
.vf-hero h1 { font-size: 46px; font-weight: 800; margin: 6px 0 10px; color: #fff; letter-spacing: -.02em; padding: 0; }
.vf-hero h1 span { color: #a5b4fc; }
.vf-lead { font-size: 21px; font-weight: 600; margin: 0 0 6px; color: #fff; }
.vf-sub { font-size: 16px; line-height: 1.6; color: #cbd5e1; max-width: 680px; margin: 0; }
.vf-steps { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
.vf-step { display: flex; align-items: center; gap: 10px; background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.14); border-radius: 999px; padding: 7px 16px 7px 7px; font-size: 14px; color: #e2e8f0; }
.vf-step b { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
  background: #818cf8; color: #0f172a; font-size: 12px; }

/* Section titles */
.vf-section { font-size: 13px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
  color: var(--vf-muted); margin: 8px 0 10px; }

/* Uploader */
[data-testid="stFileUploaderDropzone"] { background: var(--vf-surface); border: 2px dashed #c7d2fe; border-radius: 14px; padding: 28px; }
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--vf-accent); }
.stButton > button[kind="primary"] { border-radius: 10px; font-weight: 600; padding: .6rem 1rem; }

/* Stat tiles */
.vf-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 8px 0 22px; }
.vf-stat { background: var(--vf-surface); border: 1px solid var(--vf-line); border-radius: 14px; padding: 16px 18px; }
.vf-stat .n { font-size: 30px; font-weight: 800; line-height: 1.1; }
.vf-stat .l { font-size: 13px; color: var(--vf-muted); font-weight: 500; margin-top: 2px; }
.vf-stat.verified .n { color: var(--vf-verified); }
.vf-stat.inaccurate .n { color: var(--vf-inaccurate); }
.vf-stat.false .n { color: var(--vf-false); }
@media (max-width: 640px) { .vf-stats { grid-template-columns: repeat(2, 1fr); } .vf-hero { padding: 28px 22px; } .vf-hero h1 { font-size: 36px; } }

/* Claim cards */
.vf-card { background: var(--vf-surface); border: 1px solid var(--vf-line); border-left: 5px solid var(--vf-error);
  border-radius: 14px; padding: 18px 22px; margin-bottom: 14px; }
.vf-card.verified { border-left-color: var(--vf-verified); }
.vf-card.inaccurate { border-left-color: var(--vf-inaccurate); }
.vf-card.false { border-left-color: var(--vf-false); }
.vf-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.vf-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; border-radius: 999px; padding: 3px 12px 3px 4px; }
.vf-badge i { font-style: normal; display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; color: #fff; font-size: 12px; }
.vf-badge.verified { background: var(--vf-verified-bg); color: var(--vf-verified); } .vf-badge.verified i { background: var(--vf-verified); }
.vf-badge.inaccurate { background: var(--vf-inaccurate-bg); color: var(--vf-inaccurate); } .vf-badge.inaccurate i { background: var(--vf-inaccurate); }
.vf-badge.false { background: var(--vf-false-bg); color: var(--vf-false); } .vf-badge.false i { background: var(--vf-false); }
.vf-badge.error { background: var(--vf-error-bg); color: var(--vf-error); } .vf-badge.error i { background: var(--vf-error); }
.vf-meta { font-size: 13px; color: var(--vf-muted); }
.vf-quote { font-size: 16px; line-height: 1.55; color: var(--vf-ink); border-left: 3px solid var(--vf-line); padding: 2px 0 2px 14px; margin: 0 0 12px; }
.vf-fact { border-radius: 10px; padding: 10px 14px; font-size: 15px; line-height: 1.5; margin-bottom: 8px; }
.vf-fact .k { display: block; font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; margin-bottom: 2px; }
.vf-card.verified .vf-fact { background: var(--vf-verified-bg); } .vf-card.verified .vf-fact .k { color: var(--vf-verified); }
.vf-card.inaccurate .vf-fact { background: var(--vf-inaccurate-bg); } .vf-card.inaccurate .vf-fact .k { color: var(--vf-inaccurate); }
.vf-card.false .vf-fact { background: var(--vf-false-bg); } .vf-card.false .vf-fact .k { color: var(--vf-false); }
.vf-why { font-size: 14px; color: #475569; line-height: 1.55; margin: 0 0 10px; }
.vf-sources { display: flex; flex-wrap: wrap; gap: 8px; }
.vf-sources a { font-size: 13px; text-decoration: none; color: var(--vf-accent); background: #eef2ff; border-radius: 8px;
  padding: 4px 10px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vf-sources a:hover { background: #e0e7ff; }

.vf-empty { text-align: center; padding: 36px 20px; background: var(--vf-surface); border: 1px solid var(--vf-line); border-radius: 14px; color: var(--vf-muted); }
.vf-footer { text-align: center; color: var(--vf-muted); font-size: 13px; margin: 40px 0 10px; }
</style>
"""

HERO = """
<div class="vf-hero">
  <div class="vf-eyebrow">AI fact-checker for marketing content</div>
  <h1>Veri<span>Fact</span></h1>
  <p class="vf-lead">Catch outdated stats and made-up numbers before your audience does.</p>
  <p class="vf-sub">Upload any PDF. VeriFact finds every statistic, date and figure, checks each one against the
  live web, and shows you the correct fact with its source.</p>
  <div class="vf-steps">
    <div class="vf-step"><b>1</b>Extract claims</div>
    <div class="vf-step"><b>2</b>Verify on the live web</div>
    <div class="vf-step"><b>3</b>Flag &amp; correct with sources</div>
  </div>
</div>
"""

FOOTER = '<div class="vf-footer">VeriFact · Built for Cog Culture, Gurugram · Powered by Claude with live web search</div>'


def configured_api_key() -> str | None:
    """The owner's key, from Streamlit secrets or the environment."""
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:  # no secrets.toml locally
        key = None
    return key or os.getenv("ANTHROPIC_API_KEY")


def run_pipeline(pdf_bytes: bytes, max_claims: int, api_key: str) -> list[Verdict]:
    client = make_client(api_key)

    with st.status("Reading the PDF and extracting claims…", expanded=True) as status:
        claims = extract_claims(client, pdf_bytes, max_claims)
        if not claims:
            status.update(label="No checkable claims found.", state="complete")
            return []
        status.write(f"Found **{len(claims)}** checkable claims. Searching the live web for each…")

        progress = st.progress(0.0, text=f"0 / {len(claims)} claims checked")
        results: list[Verdict] = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(verify_claim, client, c) for c in claims]
            for done, future in enumerate(as_completed(futures), start=1):
                results.append(future.result())
                progress.progress(done / len(claims), text=f"{done} / {len(claims)} claims checked")
        status.update(label=f"Done. Checked {len(claims)} claims.", state="complete", expanded=False)

    return sorted(results, key=lambda v: (ORDER[v.verdict], v.claim.id))


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def source_links(sources: list[dict]) -> str:
    links = []
    for s in sources:
        url = s.get("url", "")
        if not url.startswith(("http://", "https://")):
            continue
        links.append(f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer" title="{esc(url)}">'
                     f'↗ {esc(s.get("title") or url)}</a>')
    return f'<div class="vf-sources">{"".join(links)}</div>' if links else ""


def card_html(v: Verdict) -> str:
    mod, icon, label = VERDICT_STYLE[v.verdict]
    meta = [f"Claim #{v.claim.id}", v.claim.category.capitalize()]
    if v.claim.page:
        meta.append(f"Page {v.claim.page}")
    if v.confidence:
        meta.append(f"{v.confidence.capitalize()} confidence")

    body = f'<p class="vf-quote">“{esc(v.claim.quote)}”</p>'
    if v.verdict == "Error":
        body += f'<p class="vf-why">{esc(v.explanation)}</p>'
    else:
        key = "Confirmed fact" if v.verdict == "Verified" else "Correct fact"
        body += f'<div class="vf-fact"><span class="k">{key}</span>{esc(v.correct_fact)}</div>'
        if v.explanation:
            body += f'<p class="vf-why">{esc(v.explanation)}</p>'
        body += source_links(v.sources)

    return (
        f'<div class="vf-card {mod}">'
        f'<div class="vf-head"><span class="vf-badge {mod}"><i>{icon}</i>{label}</span>'
        f'<span class="vf-meta">{esc(" · ".join(meta))}</span></div>{body}</div>'
    )


def render_cards(verdicts: list[Verdict]) -> None:
    st.html("".join(card_html(v) for v in verdicts))


def stats_html(results: list[Verdict]) -> str:
    count = lambda k: sum(v.verdict == k for v in results)  # noqa: E731
    tiles = [("", len(results), "Claims checked"), ("verified", count("Verified"), "Verified"),
             ("inaccurate", count("Inaccurate"), "Inaccurate"), ("false", count("False"), "False")]
    return '<div class="vf-stats">' + "".join(
        f'<div class="vf-stat {mod}"><div class="n">{n}</div><div class="l">{label}</div></div>' for mod, n, label in tiles
    ) + "</div>"


def to_rows(results: list[Verdict]) -> list[dict]:
    return [
        {
            "id": v.claim.id,
            "page": v.claim.page,
            "category": v.claim.category,
            "claim_in_document": v.claim.quote,
            "verdict": v.verdict,
            "correct_fact": v.correct_fact,
            "explanation": v.explanation,
            "confidence": v.confidence,
            "sources": " | ".join(s["url"] for s in v.sources),
        }
        for v in results
    ]


st.html(CSS)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    max_claims = st.slider("Max claims to check", 5, 40, 20, help="More claims = longer run and higher API cost.")
    if not configured_api_key():
        st.text_input("Anthropic API key", type="password", key="user_api_key",
                      help="Only needed if the app owner hasn't configured one. Never stored.")
    st.caption(f"Model: `{MODEL}` with live web search")
    st.divider()
    st.markdown("### What the verdicts mean")
    st.markdown(
        "🟢 **Verified**: matches current, credible data\n\n"
        "🟠 **Inaccurate**: wrong or outdated figure\n\n"
        "🔴 **False**: no credible evidence, or fabricated"
    )
    st.divider()
    st.caption("Each flagged claim shows the correct figure and the source it came from. "
               "Links are only shown if VeriFact actually found them during its search.")

# ---------- Main ----------
st.html(HERO)

st.html('<div class="vf-section">Upload a document</div>')
uploaded = st.file_uploader("Upload a PDF", type=["pdf"], label_visibility="collapsed",
                            help=f"Up to {MAX_PDF_MB} MB. Decks, reports, whitepapers, press releases, blog exports.")

pdf_bytes, pdf_name = None, None
if uploaded:
    pdf_bytes, pdf_name = uploaded.getvalue(), uploaded.name
elif SAMPLE_PDF.exists():
    col_a, col_b = st.columns([3, 2], vertical_alignment="center")
    col_a.caption("No PDF handy? Try the sample, a marketing brief with planted false and outdated stats.")
    if col_b.toggle("Use the sample trap document", key="use_sample"):
        pdf_bytes, pdf_name = SAMPLE_PDF.read_bytes(), SAMPLE_PDF.name

if pdf_bytes:
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    cached = st.session_state.get("report")
    api_key = configured_api_key() or st.session_state.get("user_api_key")

    if len(pdf_bytes) > MAX_PDF_MB * 1024 * 1024:
        st.error(f"This PDF is larger than {MAX_PDF_MB} MB. Please upload a smaller file.")
    elif not api_key:
        st.warning("Add an Anthropic API key in the sidebar to run the check.")
    elif st.button(f"🔎  Fact-check “{pdf_name}”", type="primary", width="stretch"):
        try:
            results = run_pipeline(pdf_bytes, max_claims, api_key)
            st.session_state["report"] = {"hash": doc_hash, "name": pdf_name, "results": results}
            cached = st.session_state["report"]
        except Exception as e:
            st.error(f"Fact-check failed: {type(e).__name__}: {e}")

    if cached and cached["hash"] == doc_hash:
        results: list[Verdict] = cached["results"]
        st.html('<div class="vf-section" style="margin-top:28px">Report</div>')
        if not results:
            st.html('<div class="vf-empty">No specific, checkable claims (stats, dates, figures) were found in this document.</div>')
        else:
            st.html(stats_html(results))
            errors = sum(v.verdict == "Error" for v in results)
            if errors:
                st.caption(f"{errors} claim(s) could not be checked. They're listed under All claims.")

            flagged = [v for v in results if v.verdict in ("Inaccurate", "False")]
            tab_flagged, tab_all, tab_table = st.tabs(
                [f"🚩 Flagged ({len(flagged)})", f"All claims ({len(results)})", "Table & export"])
            with tab_flagged:
                if flagged:
                    render_cards(flagged)
                else:
                    st.html('<div class="vf-empty">🎉 No inaccurate or false claims found.</div>')
            with tab_all:
                render_cards(results)
            with tab_table:
                df = pd.DataFrame(to_rows(results))
                st.dataframe(df, hide_index=True, width="stretch")
                base = cached["name"].rsplit(".", 1)[0]
                d1, d2 = st.columns(2)
                d1.download_button("⬇ Download CSV", df.to_csv(index=False), f"{base}_factcheck.csv",
                                   "text/csv", width="stretch")
                d2.download_button("⬇ Download JSON", json.dumps(to_rows(results), indent=2),
                                   f"{base}_factcheck.json", "application/json", width="stretch")

st.html(FOOTER)
