# Signal Stack — Company Intelligence & Executive Briefing Engine

EDXSO AI Engineer Intern, Assignment 1. Give the system a company name and
website; it researches the company, runs an adaptive 10-question founder
interview, builds a justified Signal Stack of intelligence sources across
**Customers / Competitors / Market / Internal**, crawls those sources for
real developments, analyses and ranks them, and produces a **Monday Morning
Brief** in the exact 10-section format — every claim traceable to a fetched
URL, nothing fabricated.

Free and open-source only: Python 3, Flask, SQLite, requests/BeautifulSoup.
No paid APIs, no LLM services (analysis is a transparent rule-based engine).

## Run it locally (end-to-end)

```bash
cd edxso-build
pip install -r requirements.txt

# 1) Build the 3-company demonstration (research → discovery → interview
#    seeding → stack → crawl → briefs → audit → reassessment demo).
#    Takes several minutes: fetching is deliberately polite.
python3 seed_demo.py

# 2) Start the dashboard
python3 app.py            # http://127.0.0.1:5000

# 3) (Optional) run the automation once, exactly as the scheduler does
python3 run_weekly.py          # crawl all companies + regenerate all briefs
python3 run_monthly_audit.py   # source-health audit report
```

To configure a **new** company instead: start `app.py`, open **Company
Setup**, enter name + website, and follow the flow (research → interview →
stack → crawl → brief). No code changes are needed per company.

### Scheduling (cron)

`schedule.json` holds the two jobs; Settings in the dashboard edits them.
Install at OS level with:

```cron
0 7 * * 1   cd /path/to/edxso-build && python3 run_weekly.py
0 8 1 * *   cd /path/to/edxso-build && python3 run_monthly_audit.py
```

Every run — scheduled, manual or failed — is logged in **Run History**.

## How it works

| Stage | Module | What happens |
|---|---|---|
| Research | `signalstack/research.py` | Fetches the site's public pages (robots.txt honoured, rate-limited) and drafts the company profile: industry, business lines, customers, value proposition, keyword profile. |
| Interview | `signalstack/interview.py` | 10 mandated topics, phrased per industry archetype with slots filled from *this* company's profile, business lines and discovered competitors — so questions differ per company. One at a time, skippable, editable, with answer-driven follow-ups. |
| Discovery | `signalstack/discovery.py` | Competitors are **derived** via 5 channels (Wikipedia link graph, news listicles, news-corpus co-mentions, co-mention expansion, founder-interview names) and every candidate must pass live verification (real homepage, keyword overlap with the company's own profile, self-branding check). Stack sources are then assembled per category, each with a written Specific / Recent / Credible justification. |
| Crawling | `signalstack/crawler.py` | RSS news index (links decoded to the real publisher) + web change detection via content hashing; dedupe by content hash; records keep evidence snippet + direct link + publication/discovery dates + verification status. |
| Internal | `signalstack/internal_docs.py` | CSV/TXT uploads clustered into recurring themes (price objections, process confusion, delays, lost-to-competitor, feature requests, quality complaints); themes with ≥2 mentions become records quoting the actual lines. Samples in `data/internal_samples/`. |
| Analysis | `signalstack/analysis.py` | Rule-based (no AI APIs): signal type, stance (opportunity/threat/neutral), business area, why-it-matters from company context, action playbook; six separate measures stored per record — relevance, impact, urgency, source reliability, evidence strength, strategic relevance (+ novelty, composite). |
| Brief | `signalstack/brief.py` | The exact 10-section Monday Morning Brief from stored records; empty categories say so explicitly; ≥3 opportunities with evidence / impact / next step / priority; full source appendix. Saved to `output/briefs/` and the DB. |
| Audit | `signalstack/audit.py` | Monthly: dead/erroring sources, duplicates, inactive sources, fresh-discovery suggestions → `output/audits/`. |
| Reassessment | `signalstack/reassess.py` | On context change: flags stale sources, adds newly discovered competitors/sources, explains every change. Demo: `output/evidence/reassessment_demo.md`. |

## How each brief requirement is satisfied

- **3 companies, different industries** — MeetUniversity (study-abroad
  admissions), Zerodha (fintech broking), boAt (D2C consumer audio), all
  configured by the same pipeline in `seed_demo.py`.
- **Adaptive interview per company** — archetype variants × profile slots;
  compare the three companies' interview pages: wording, examples and
  follow-ups differ.
- **≥20 approved MeetUniversity sources** — 2 per competitor (official site
  + dedicated news index) + market + customer + internal sources; see
  `output/evidence/counts.json` for the verified count.
- **5–10 MeetUniversity competitors** — derived + verified as above; each
  competitor row stores its derivation evidence.
- **≥30 real records** — every record in the feed links to the publisher
  page it was fetched from; counts in `output/evidence/counts.json`.
- **Brief per company** — `output/briefs/` (also viewable in the dashboard,
  with history).
- **Working scheduler + audit** — `schedule.json`, `run_weekly.py`,
  `run_monthly_audit.py`; failed runs are visible in Run History.
- **Source add/remove** — Source Manager in the dashboard (add, approve,
  mark stale, remove, crawl now).
- **Historical records** — crawls and briefs are append-only in SQLite;
  re-crawls dedupe instead of duplicating.

## Repository layout

```
app.py                  Flask dashboard (all pages in the brief)
seed_demo.py            builds the 3-company demonstration + evidence
run_weekly.py           weekly brief job (scheduler entry point)
run_monthly_audit.py    monthly audit job (scheduler entry point)
schedule.json           schedule config (also editable in Settings)
schema.sql              SQLite schema
signalstack/            engine: research, interview, discovery, crawler,
                        analysis, internal_docs, brief, audit, reassess,
                        db, http_util (robots/rate-limit), config
templates/              dashboard templates
data/internal_samples/  sample internal files used by the demo
docs/TECHNICAL.md       architecture, discovery, crawling, ranking,
                        analysis method, scheduling, limitations (≤5 pages)
docs/COST_STATEMENT.md  free/open-source inventory + free-tier limitations
demo/DEMO_RUNBOOK.md    5–10 minute screen-recording script
output/                 generated briefs, audits, evidence (counts, logs)
```

## Honesty rules built into the system

- Records are created **only** inside fetch paths — if a source yields
  nothing, the run log says so and the brief states the category had no
  meaningful development.
- Evidence (verbatim snippet + link) is stored separately from
  interpretation (why-it-matters); verification status is shown per record.
- Sources that block crawling (403, robots.txt) fail visibly in Run
  History and are flagged by the monthly audit — never circumvented.
