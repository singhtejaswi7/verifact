# VeriFact: PDF Fact-Checker

VeriFact is a "truth layer" for marketing content. Upload a PDF and it:

1. **Extracts** specific, checkable claims (statistics, dates, financial and technical figures).
2. **Verifies** each claim against the live web.
3. **Reports** each claim as **Verified**, **Inaccurate** (wrong or outdated figure) or **False** (no credible evidence or fabricated), with the correct fact and the source links used.

**Live app:** _add your Streamlit Cloud URL here_

## How it works

```
PDF ──► Claude (native PDF reading + JSON-schema output) ──► list of standalone claims
                                                                  │  (checked in parallel, 6 at a time)
                                                                  ▼
          Claude + web_search / web_fetch (server-side tools) ──► submit_verdict (strict tool schema)
                                                                  │
                                                                  ▼
                       source links checked against the URLs actually seen ──► Streamlit report + CSV/JSON
```

- **Extraction** ([verifact/extract.py](verifact/extract.py)): the PDF goes to Claude as a native document, so tables and charts are read too, not only the text layer. Structured outputs guarantee valid JSON. Each claim is rewritten as a standalone sentence (subject + figure + timeframe) so it can be searched on its own.
- **Verification** ([verifact/verify.py](verifact/verify.py)): one agent loop per claim, using Anthropic's server-side `web_search` and `web_fetch` tools. The model is given today's date so it can recognise outdated stats. It records its result by calling a `strict` `submit_verdict` tool, so every verdict has the same shape.
- **Source grounding**: a cited link is kept only if it appeared in that claim's search results or was fetched. If none survive, the top results the model actually saw are shown instead. This prevents made-up URLs.
- **UI** ([app.py](app.py)): Streamlit, with flagged claims listed first, summary counts, a table view, and CSV/JSON export. Results are cached in the session, so reruns don't cost anything.

## Run locally

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then add your key
streamlit run app.py
```

You can also set `ANTHROPIC_API_KEY` in the environment. If no key is configured, the app asks for one in the sidebar.

## Deploy (Streamlit Community Cloud)

1. Push this repo to GitHub.
2. On [share.streamlit.io](https://share.streamlit.io), click **Create app** and pick the repo, branch `main`, file `app.py`. Under **Advanced settings**, choose Python 3.12.
3. In **Secrets**, add `ANTHROPIC_API_KEY = "sk-ant-..."`.
4. Deploy.

Web search must be enabled for your organization in the Anthropic Console.

## Configuration

| Setting | Where | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | secrets / env | required |
| `VERIFACT_MODEL` | env | `claude-opus-5-5` |
| Max claims per run | sidebar slider | 20 |

## Cost and speed

Each claim uses up to 5 web searches and 3 page fetches. A typical 10–20 claim document takes a few minutes. As a rough estimate, it costs $0.10–0.30 per claim (search fees plus tokens). Lower the max-claims slider to cap spend.
