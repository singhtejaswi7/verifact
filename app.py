import hashlib
import html
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import streamlit as st

from verifact.client import MODEL, make_client
from verifact.extract import extract_claims
from verifact.verify import Verdict, verify_claim

MAX_PDF_MB = 20
WORKERS = 6

BADGES = {
    "Verified": ("#1a7f37", "✅ Verified"),
    "Inaccurate": ("#b35900", "⚠️ Inaccurate"),
    "False": ("#cf222e", "❌ False"),
    "Error": ("#6e7781", "⏸ Could not check"),
}
ORDER = {"False": 0, "Inaccurate": 1, "Error": 2, "Verified": 3}

st.set_page_config(page_title="VeriFact – PDF Fact-Checker", page_icon="🔎", layout="wide")


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
        status.update(label=f"Checked {len(claims)} claims.", state="complete", expanded=False)

    return sorted(results, key=lambda v: (ORDER[v.verdict], v.claim.id))


def badge(verdict: str) -> str:
    color, label = BADGES[verdict]
    return (
        f'<span style="background:{color};color:#fff;padding:2px 10px;border-radius:12px;'
        f'font-size:0.85rem;font-weight:600">{label}</span>'
    )


MD_SPECIAL = set("\\`*_{}[]<>()#+-.!|$~")


def md(text: str) -> str:
    """Escape markdown (and Streamlit's $…$ LaTeX) so document text renders literally."""
    return "".join("\\" + ch if ch in MD_SPECIAL else ch for ch in text)


def link_md(source: dict) -> str:
    title = md(source.get("title") or source["url"])
    return f"[{title}]({source['url'].replace(' ', '%20').replace('(', '%28').replace(')', '%29')})"


def render_verdict(v: Verdict) -> None:
    with st.container(border=True):
        meta = f"Claim #{v.claim.id} · {v.claim.category}"
        if v.claim.page:
            meta += f" · page {v.claim.page}"
        if v.confidence:
            meta += f" · {v.confidence} confidence"
        st.markdown(f"{badge(v.verdict)} &nbsp; <small>{html.escape(meta)}</small>", unsafe_allow_html=True)
        st.markdown(f"> {md(v.claim.quote)}")

        if v.verdict == "Error":
            st.caption(md(v.explanation))
            return
        label = "Confirmed fact" if v.verdict == "Verified" else "Correct fact"
        st.markdown(f"**{label}:** {md(v.correct_fact)}")
        if v.explanation:
            st.caption(md(v.explanation))
        if v.sources:
            st.markdown("**Sources:** " + " · ".join(link_md(s) for s in v.sources))


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


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    max_claims = st.slider("Max claims to check", 5, 40, 20, help="More claims = longer run and higher API cost.")
    if not configured_api_key():
        st.text_input("Anthropic API key", type="password", key="user_api_key",
                      help="Only needed if the app owner hasn't configured one. Never stored.")
    st.caption(f"Model: `{MODEL}` with live web search")
    st.divider()
    st.markdown(
        "**Verdicts**\n\n"
        "✅ **Verified** – matches current data\n\n"
        "⚠️ **Inaccurate** – wrong or outdated figure\n\n"
        "❌ **False** – no credible evidence / fabricated"
    )

# ---------- Main ----------
st.title("🔎 VeriFact")
st.markdown("**The truth layer for marketing content.** Upload a PDF; VeriFact pulls out every stat, date and "
            "figure, checks each one against the live web, and flags what's wrong with the correct fact and a source.")

uploaded = st.file_uploader("Upload a PDF", type=["pdf"])

if uploaded:
    pdf_bytes = uploaded.getvalue()
    doc_hash = hashlib.sha256(pdf_bytes).hexdigest()
    cached = st.session_state.get("report")
    too_big = len(pdf_bytes) > MAX_PDF_MB * 1024 * 1024
    api_key = configured_api_key() or st.session_state.get("user_api_key")

    if too_big:
        st.error(f"PDF is larger than {MAX_PDF_MB} MB. Please upload a smaller file.")
    elif not api_key:
        st.warning("Add an Anthropic API key in the sidebar to run the check.")
    elif st.button("Run fact-check", type="primary"):
        try:
            results = run_pipeline(pdf_bytes, max_claims, api_key)
            st.session_state["report"] = {"hash": doc_hash, "name": uploaded.name, "results": results}
            cached = st.session_state["report"]
        except Exception as e:
            st.error(f"Fact-check failed: {type(e).__name__}: {e}")

    if cached and cached["hash"] == doc_hash:
        results: list[Verdict] = cached["results"]
        if not results:
            st.info("No specific, checkable claims (stats, dates, figures) were found in this document.")
        else:
            counts = {k: sum(v.verdict == k for v in results) for k in BADGES}
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Claims checked", len(results))
            c2.metric("✅ Verified", counts["Verified"])
            c3.metric("⚠️ Inaccurate", counts["Inaccurate"])
            c4.metric("❌ False", counts["False"])
            if counts["Error"]:
                st.caption(f"{counts['Error']} claim(s) could not be checked (see bottom of list).")

            flagged = [v for v in results if v.verdict in ("Inaccurate", "False")]
            tab_flagged, tab_all, tab_table = st.tabs([f"Flagged ({len(flagged)})", f"All ({len(results)})", "Table"])
            with tab_flagged:
                if not flagged:
                    st.success("No inaccurate or false claims found.")
                for v in flagged:
                    render_verdict(v)
            with tab_all:
                for v in results:
                    render_verdict(v)
            with tab_table:
                rows = to_rows(results)
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                base = cached["name"].rsplit(".", 1)[0]
                d1, d2 = st.columns(2)
                d1.download_button("Download CSV", pd.DataFrame(rows).to_csv(index=False),
                                   f"{base}_factcheck.csv", "text/csv")
                d2.download_button("Download JSON", json.dumps(rows, indent=2),
                                   f"{base}_factcheck.json", "application/json")
else:
    st.info("Upload a PDF to begin. Works best on marketing decks, reports, press releases and blog posts.")
