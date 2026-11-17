# Technical Documentation — Signal Stack

*Company Intelligence & Executive Briefing Engine. Python 3 + Flask + SQLite,
free/open-source only, no paid APIs and no LLM services.*

## 1. Architecture

```
            ┌──────────────────────── Flask dashboard (app.py) ───────────────────────┐
            │ Setup · Profile · Interview · Signal Stack · Sources · Feed · Brief ·    │
            │ Run History · Audits · Settings                                          │
            └──────────────┬───────────────────────────────────────┬──────────────────┘
                           │                                       │
   signalstack/engine.py   │  setup pipeline                       │  run_weekly.py /
        │                  │                                       │  run_monthly_audit.py
        ├─ research.py     │  fetch site → draft profile           │  (schedule.json + cron)
        ├─ discovery.py    │  competitors + Signal Stack sources   │
        ├─ interview.py    │  adaptive 10-question interview       │
        ├─ crawler.py      │  RSS + web change detection ──────────┤
        ├─ analysis.py     │  rule-based signal analysis + ranking │
        ├─ internal_docs.py│  CSV/TXT internal-signal extraction   │
        ├─ brief.py        │  Monday Morning Brief (10 sections)   │
        ├─ audit.py        │  monthly source-health audit          │
        └─ reassess.py     │  context-change reassessment          │
                           │
                    SQLite (schema.sql): companies, competitors,
                    interview_questions, sources, records, briefs,
                    runs, audits, settings
```

Every pipeline step writes a row to `runs` with a full text log — successes
*and failures* are visible in the dashboard's Run History. Nothing in the
system invents data: a record exists only if it was fetched from a URL, and
it keeps that URL forever.

## 2. Company research (setup step 1)

Given a name + website, `research.py` fetches the homepage plus up to three
internal pages (robots.txt checked, per-host rate limiting), then extracts a
draft profile: industry (keyword-dictionary classification over page text),
business lines (service-keyword headings preferred over marketing slogans),
customer segments, value proposition and a keyword profile (top content
words) that later stages use for verification and ranking. The profile is
stored as JSON on the company row and is editable in the dashboard.

## 3. Source discovery (setup steps 2–3)

**Competitors are derived, never hard-coded.** Five channels feed one
verification gate:

- **S1 Wikipedia graph** — the company's article and the industry-concept
  article contribute their outgoing links (institutions filtered out;
  off-topic seed articles skipped by keyword overlap).
- **S2 News listicles** — comparison/best-of articles from the news index;
  company names from their headings and outbound links.
- **S3 News-corpus mining** — capitalised names recurring across category
  news titles/descriptions (Bing News + Google News RSS text).
- **S4 Co-mention expansion** — one query per verified competitor surfaces
  the next ring of players named alongside them.
- **S5 Founder interview** — the interview asks which competitors the
  company watches; those names enter the same gate.

**Verification gate (mandatory for every candidate):** resolve a website
(Wikipedia's official link → domain derivation), fetch the homepage, and
require (a) keyword overlap with the target company's researched profile,
including at least one *distinctive* industry term — generic words prove
nothing (measured: a food site scored 6 generic matches such as
"expert/support/experience" and 0 distinctive ones, and is rejected; a real
peer with a thin JS-rendered homepage still shares a distinctive term);
(b) the site brands itself with the candidate's name (title/domain) — and
for listicle content links, whose anchors describe the link's topic rather
than the company, the brand token must match the linked domain; and (c) the
name is not a publisher (media domains and subdomains), newsroom byline,
institution, Wikipedia-defined concept (including near-titles such as
"Trading Strategies" → "Trading strategy"), category noun or generic
corpus fragment. Two names resolving to one domain are de-duplicated.
Wikipedia is also checked in the other direction: a name whose exact
article (and "<name> company" article) does not read as a company is a
thing, not a firm ("Bluetooth", "AirPods"); and when Wikipedia hands back
a division's site ("Sony" → sonypictures.com), the exact-name domain wins
if it verifies about as well (sony.com). Deep article URLs offered as
"websites" are ignored — an article is evidence, not a homepage.
Rejections are logged with reasons. Each survivor stores its derivation
evidence. General web search has no free programmatic tier (documented in
`COST_STATEMENT.md`), which is why discovery is built from these signals.

**Signal Stack assembly** (`discovery.build_sources`): per competitor — its
official website (change watch) + a dedicated exact-phrase news-index
source; Market — industry/regulatory queries derived from the industry
vocabulary + an exact-phrase source on the company itself; Customers — a
reviews/complaints query + category problem queries; Internal — one upload
source per company. Every source stores a reason and written Specific /
Recent / Credible justifications.

## 4. Crawling & monitoring

`crawler.py` handles three source types:

- **rss** — parses the news index (Bing News RSS; item links are apiclick
  URLs decoded to the real publisher URL; publisher read from the feed's
  `News:Source` element). Items older than 120 days are dropped.
- **web** — fetches the page, hashes its main content; a first crawl stores
  a positioning-snapshot record, later crawls store a record only when the
  hash changes (change detection).
- **internal** — not crawled; populated by file upload (see §5).

Dedupe is by `UNIQUE(company_id, content_hash)` over title+URL+snippet, so
re-crawls never duplicate records. Each record stores: evidence snippet
(verbatim from the source), direct link, publication date (feed) and
discovery date, verification status, and the source's identity. Fetch
failures increment the source's `fail_count` and appear in the run log.
Politeness: robots.txt honoured for web pages, ≥1s between requests to the
same host, max 4 items per source per crawl.

## 5. Analysis & ranking (no AI APIs)

`analysis.py` is a transparent rule-based engine — the brief forbids paid AI
services, and rules are inspectable:

- **Signal type** from keyword patterns (launch, pricing, partnership,
  funding, regulation, complaint, expansion, hiring…).
- **Category & stance** — opportunity / threat / neutral from the category
  plus signal-type rules (e.g. a competitor price cut = threat; a market
  regulation that raises rivals' costs = opportunity).
- **Business area** mapped from the company's own profile/interview context;
  strategic relevance is boosted when the founder's answers name that area.
- **Why it matters** is generated per category×signal-type from the company
  context (its segments, growth focus, stated material developments) —
  interpretation is stored in a separate field from the verbatim evidence.
- **Six separate measures** per record: relevance, impact, urgency,
  source_reliability (from the source), evidence_strength (snippet length /
  first-party vs aggregator), strategic_relevance, plus novelty; a weighted
  composite orders the feed and the brief. "AI confidence is not proof":
  verification status is shown separately and unverified items are labelled.

`internal_docs.py` clusters uploaded CSV/TXT text into 7 themes (price
objection, process confusion, delay, lost-to-competitor, feature request,
quality complaint, positive); a theme with ≥2 mentions becomes an Internal
record quoting the actual lines as evidence.

## 6. Monday Morning Brief

`brief.py` renders the brief's exact 10 sections from stored records:
executive summary = top 5 by composite score; the four category sections
(empty categories state "no meaningful development found" explicitly —
never padded); ≥3 opportunities (opportunity-stance records first, then
customer-problem patterns) each with evidence, impact, next step (from the
per-signal-type action playbook) and priority; risks; recommended actions;
watch list; and a full source appendix table (source, link, publication
date, discovery date, evidence, verification status). Briefs are saved to
`output/briefs/` and to the `briefs` table (history kept).

## 7. Scheduling & audit

`schedule.json` holds the two jobs with cron expressions (weekly: Monday
07:00 → `run_weekly.py`; monthly: day 1, 08:00 → `run_monthly_audit.py`),
editable in Settings. `run_weekly.py` crawls every company and regenerates
every brief, logging one `runs` row per company. `audit.py` flags dead or
repeatedly erroring sources (fail_count ≥2), duplicate sources (normalised
URL), inactive sources (0 records), and suggests fresh discoveries; the
report is saved to `output/audits/` and the `audits` table. Install with
two crontab lines (see README).

## 8. Reassessment (context change)

`reassess.py`: when a company's context (growth focus / notes) changes, it
(1) flags non-competitor sources whose queries share no vocabulary with the
new context as `stale` (with the reason stored), (2) re-runs competitor
discovery and adds verified newcomers with their sources, and (3) adds a
market source built from the new growth focus. Every change is returned as
an explained list and logged. A worked demo is in
`output/evidence/reassessment_demo.md`.

## 9. Reliability & limitations

- **Failure visibility:** setup/crawl/audit failures land in `runs` with
  status `failed`/`partial` and the reason; sources carry `fail_count` and
  last-status; the audit surfaces chronic failures monthly.
- **No fabrication, by construction:** records are only created inside the
  fetch paths; the brief renders only stored records; empty means empty.
- **Free-tier limits:** no free programmatic web search (discovery is
  multi-signal instead); RSS windows rotate, so quiet sources yield zero
  records in a week; some publishers return 403 to any crawler — those
  sources fail visibly rather than being circumvented; Google News article
  links are opaque redirect tokens (rate-limited on resolve), so Google
  News is used only for name mining, never as a cited record source.
- **Scale:** designed for the brief's scale (a handful of companies, tens
  of sources each, weekly cadence) on one small machine; SQLite + polite
  sequential fetching is a deliberate fit, not a bottleneck at this size.
