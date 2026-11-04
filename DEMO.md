# PruvChat Demo Script (~2.5 minutes, Mock Mode, fully offline)

## Hackathon 60 second cut (Visa, Mock Mode, offline)

1. Top menu → Visa review. Click Try example (synthetic travel checklist, clearly labeled).
2. Click Run assessment. Point at the plain coverage lines: What looks ready 1 of 3, What needs attention 2, What to do next.
3. Open one card: exact quote, source label, method line. Missing evidence means uncertain, not verified.
4. Save the workspace, reopen it from the sidebar, download the findings. Done.
Say: mock verdicts are word match heuristics. Official URL fetch and refresh each take one click for live review, and live AI needs separate approval.

Prereqs: `pip install -r requirements.txt`, then `streamlit run app.py`.
Open http://localhost:8501. Stay on the **Mock (offline, free)** engine the whole time.
Never switch to Live on stage (billed, needs a key and explicit approval).

Say up front: *"Mock verdicts are keyword-overlap heuristics, not AI judgments.
Watch the Method line on every card — it says exactly how each finding was made."*

## 0:00 — Overview (20s)

1. Overview shows the top menu and four mode cards in a 2 by 2 grid.
2. Click **Explore Requirements**. Point at the yellow banner: `MOCK MODE — verdicts are keyword-overlap heuristics`.

## 0:20 — Requirements (40s)

1. Click **Try example** (synthetic portfolio review, labeled in the fixture).
2. Click **Run assessment**. Staged progress runs: extract → score → contradiction check.
3. Show the summary line: 3 findings, 1 Supported, 2 Needs review.
4. Show the three finding cards: title, simple status, one sentence, next action.
   - r1 SUPPORTED, cites e1;
   - r2 CONTESTED (Needs review), cites e2;
   - r3 CONTESTED — point out it only weakly matches on the word
     "client". This is the honest limitation of a heuristic: shown as-is.
5. Expand one **View evidence and details** section: exact excerpt + `pasted text #N` locator.
6. Point at `Method: keyword-overlap heuristic (not an AI judgment)` inside details.

## 1:00 — Business disputes (35s)

1. Top menu → **Disputes**. Click **Try example**
   (synthetic order-1042 dispute, no real parties). Click **Run assessment**.
2. Same claim scored against each side: Side A SUPPORTED (0.667), Side B
   CONTESTED (0.333) — the verdict visibly flips with the evidence.
3. Point at both **Contradiction flag (heuristic)** warnings: a1↔b1 disagree,
   uncertainty Medium. "Flags are leads for human review, not accusations."

## 1:35 — Custom + Save (30s)

1. Top menu → **Custom**. Click **Try example** (synthetic
   launch-readiness check). Click **Run assessment**: 1 SUPPORTED (cites the
   beta-test line), 1 UNSUPPORTED showing "No supporting evidence supplied."
2. Under **Save or export**, name it `demo-custom`, click **Save workspace locally**.
3. Sidebar **Saved workspaces (this machine)** now lists it. Note the
   `Runs dir: …/.pruvchat_runs (N file(s))` caption — runs never leave the machine.

## 2:05 — Reopen + Export (25s)

1. Sidebar: select the saved run, click **Open**. Inputs return AND the PruvCards
   render immediately with a `Restored saved findings — assessed … · mock engine`
   banner. No rerun, no providers called.
2. Click **Download findings (.md)**. The export header names the mode and engine
   (`Engine: Mock (offline, free)`), and every card carries its method,
   uncertainty, excerpt, locator, and next action.

## 2:30 — Close (10s)

`pytest -q` passes offline (289 tests). Mock is the default; live Meta inference
exists behind a two-step confirm and is deliberately not part of this demo.

## Deliberately out of the timed path

- **URL fetch / file upload**: work (SSRF-guarded fetch, TXT/MD/PDF/DOCX), but need
  internet respectively a local file — mention, don't click.
- **Disputes saving**: each side saves as its own workspace (two Save sections);
  the demo saves only the Custom run to stay in time.
- **Live engine**: never enable on stage without prior approval — it spends credits.
- **r3 contested-via-pooling**: requirements share one evidence pool, so r3 weakly
  matches e1 (0.25). Present it as the heuristic's visible limit, not a verdict bug.
