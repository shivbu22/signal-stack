# Demo Runbook — Signal Stack screen recording (5–10 minutes)

For the candidate to record. Everything below is live in the app — no slides
needed. Start the app first:

```bash
cd edxso-build
python3 seed_demo.py   # only if the demo database is not built yet
python3 app.py         # dashboard at http://127.0.0.1:5000
```

## Script (≈8 minutes)

**0:00 – The problem (30s, on the Home page)**
"Founders drown in scattered news, competitor moves and customer complaints.
Signal Stack turns public information into one Monday Morning Brief per
company. Three companies are configured — MeetUniversity (study-abroad),
Zerodha (fintech broking) and boAt (D2C audio) — to prove the same engine
adapts to any business."

**0:30 – Company setup & research (1 min → Company Setup / MeetUniversity profile)**
Show the MeetUniversity intelligence profile: industry, business lines,
customers and value proposition were extracted automatically from its public
website at setup. "Nothing here was typed in — the system researched the
site, and the profile stays editable."

**1:30 – Adaptive interview (1.5 min → MeetUniversity → AI Interview)**
Show the 10 questions. Point out they are generated from this company's own
profile — the business-lines question names MeetUniversity's actual services;
switch to Zerodha's interview and show the questions are different (trading,
brokerage, SEBI context). Show one seeded founder answer and the 'seed —
editable' marker; show a follow-up question generated from an answer.
"The interview also feeds discovery: competitors the founder names are
verified live by the system before being added."

**3:00 – Signal Stack & source justification (1.5 min → MeetUniversity → Signal Stack)**
Show the four categories (Customers / Competitors / Market / Internal) and
the 20+ approved sources. Open one competitor source and one market source:
each carries a written reason plus Specific / Recent / Credible
justifications. Show the competitor list and one derivation evidence entry:
"Competitors were derived — from Wikipedia's link graph, news listicles and
co-mentions — then verified against the company's own keyword profile.
Nothing is hard-coded; run setup for a new company and it derives a new list."

**4:30 – Live crawl & Intelligence Feed (1.5 min → Sources → 'Crawl now' on one source, then Feed)**
Trigger a crawl of one source live. Then open the Intelligence Feed: filter
by category and by minimum impact. Open one record: evidence snippet, direct
publisher link, publication + discovery dates, verification status, and the
three separate scores — source reliability, evidence strength, strategic
relevance — plus why it matters and the recommended action. "Every record
is a real fetched item, traceable to its URL. Nothing is fabricated; quiet
sources log 'no development found'."

**6:00 – Monday Morning Brief (1.5 min → MeetUniversity → Brief)**
Walk the 10 sections quickly: executive summary (top 5), the four signal
sections, ≥3 opportunities each with evidence, impact, next step and
priority, risks, this week's recommended actions, watch list, and the full
source appendix. Note any section that states 'no meaningful development'
explicitly — that's the honesty rule working.

**7:30 – Automation & reassessment (1 min → Run History, Audits, Settings)**
Show Run History (every setup/crawl/brief/audit run with its log, failures
visible), one monthly audit report (dead/duplicate/inactive sources +
recommendations), and Settings with the weekly/monthly schedule
(`run_weekly.py` / `run_monthly_audit.py`, cron lines in `schedule.json`).
Finish on the Zerodha reassessment demo (evidence file
`output/evidence/reassessment_demo.md`): "When the founder changed Zerodha's
growth focus, the system flagged stale sources, discovered new ones and
explained every change."

**8:30 – Close (30s)**
"Free and open-source end to end — no paid APIs, no LLM calls; the analysis
engine is transparent rules. Limitations are documented honestly in
`docs/TECHNICAL.md`: search has no free programmatic tier, some publishers
block crawlers, and quiet sources report zero developments instead of
inventing them."
