# VeriFact: Product Note

## Who it's for
Content marketers, agency account teams and brand/PR reviewers who publish stat-heavy material such as decks, whitepapers, blog posts and press releases. Their content often reuses a figure from a three-year-old report or a number an AI tool made up. Checking it by hand means one Google search per number, so it gets skipped. VeriFact handles that last check before something goes out: upload the PDF and get a list of the claims that are wrong, what the right figure is, and the source for it.

## Key choices
- **Extract first, then verify each claim separately.** One LLM call over the whole document would skim. Splitting the work turns it into many small, focused research tasks, each with its own search budget. They run in parallel, so a 20-claim document doesn't take 20× as long.
- **Claims are rewritten to stand on their own.** "It grew 40% last year" can't be searched. "Company X's revenue grew 40% in 2023" can. Extraction adds the subject and timeframe and keeps the original quote for display.
- **"Outdated" counts as a defined failure, not a judgment call.** The verifier is given today's date. A figure presented as current when a materially newer one exists is marked **Inaccurate**, with the current figure shown. A figure that is explicitly dated and was true at that time is marked **Verified**. This is the most common trap in marketing copy.
- **Every verdict has the same structure.** Verdicts come through a strict tool schema (verdict, correct fact, explanation, confidence, sources) rather than free text, so the UI and exports never break on odd output.
- **Source links can't be invented.** A cited URL is shown only if it appeared in that claim's search results or was actually fetched. A fact-checker that invents its sources would defeat the point.
- **Flagged claims come first.** Reviewers care about what's wrong, so the default view shows only Inaccurate and False claims. Verified claims are one tab away, and there is a CSV/JSON export for editors.

## Current limitations
- **"False" combines two cases.** "Contradicted by evidence" and "no evidence found" share one label, as the brief specified. Niche or very recent claims can be marked False only because they aren't indexed yet.
- **Internal claims can't be checked.** Statements like "our NPS is 72" have no public source, so they are skipped on purpose and the user isn't told they were skipped.
- **Search-quality ceiling.** Paywalled reports (Gartner, Statista) and conflicting sources limit accuracy. The confidence label helps, but the tool doesn't yet show the conflict between sources.
- **Cost and latency grow with the number of claims.** Each claim makes several web searches, which takes a few minutes for a dense deck. There is no caching across documents or users.
- **Results aren't fully repeatable.** Two runs on the same PDF can return slightly different claim lists or verdicts.

## Top three next improvements
1. **A fourth "Unverifiable" verdict and a list of skipped claims.** Separate "evidence contradicts it" from "couldn't find evidence", and show the internal claims that were skipped. This makes the report more trustworthy, because the user can see what wasn't checked.
2. **Inline annotation of the PDF.** Highlight each claim at its exact location in the document, with the correct figure as a comment, and allow export of an annotated PDF. This fits how editors already review, and makes fixes a one-click job.
3. **A shared fact cache plus an evaluation set.** Cache verified facts with their sources and dates so repeated stats (such as "ChatGPT weekly users") are instant and consistent. Build a labelled set of trap documents to measure precision and recall on Inaccurate and False claims for every prompt or model change.
