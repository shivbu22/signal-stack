# Cost Statement — Signal Stack

**Total build & run cost: ₹0 / $0.** Every component is free and open-source,
or a free public endpoint used within its terms. No paid APIs, no paid
scraping services, no paid AI/LLM services are used anywhere in the system.

## What is used, and what it costs

| Component | Used for | Cost |
|---|---|---|
| Python 3 (stdlib: sqlite3, hashlib, re, csv) | Runtime, storage, analysis | Free, open-source |
| Flask | Web dashboard | Free, open-source (BSD) |
| requests + BeautifulSoup4 | Polite HTTP fetching + HTML/RSS parsing | Free, open-source |
| markdown (Python) | Rendering briefs in the dashboard | Free, open-source |
| SQLite | All storage (companies, sources, records, briefs, runs, audits) | Free, public domain |
| Bing News RSS (`bing.com/news/search?format=rss`) | News index for records — item links decode to the real publisher URL | Free public RSS |
| Google News RSS (`news.google.com/rss`) | Name mining during competitor discovery only (its article links are opaque redirect tokens, so it is never cited as a record source) | Free public RSS |
| Wikipedia API (`en.wikipedia.org/w/api.php`) | Competitor-discovery link graph + official-website resolution | Free public API |
| Company / competitor public websites | First-party positioning, pricing and change-watch sources | Free public pages, fetched politely (robots.txt honoured, per-host rate limiting) |
| cron / Task Scheduler (OS-level) | Weekly brief + monthly audit scheduling via `schedule.json` commands | Free, built into the OS |

## What is deliberately NOT used

- No OpenAI / Anthropic / any LLM API — the brief forbids paid AI services.
  Analysis is a transparent, documented rule-based engine
  (see `docs/TECHNICAL.md` §5). Its rules are inspectable in
  `signalstack/analysis.py`.
- No paid scraping proxies, CAPTCHA solvers or headless-browser farms.
  Sources that block polite fetching (HTTP 403, robots.txt, bot walls) are
  logged as failed in Run History — never circumvented.
- No paid news APIs. The two RSS indexes above are free public feeds.

## Free-tier limitations (honest)

1. **General web search has no free programmatic tier.** Google/Bing web
   search HTML is bot-walled or JavaScript-only, and search APIs are paid.
   Competitor discovery therefore combines the signals that *are* freely
   accessible — Wikipedia's link graph, news listicles, news-corpus
   co-mentions — plus the founder interview, with every candidate verified
   live before inclusion. On an unseen company in a niche with thin news
   coverage, auto-discovery may return fewer than 5 competitors; the
   interview channel and manual source add (Source Manager) cover that.
2. **RSS indexes rotate.** Bing News / Google News RSS return a rolling
   window of recent items; a quiet week for a small competitor can yield
   zero new records. The system logs "no development found" rather than
   inventing activity, and briefs state empty categories explicitly.
3. **Some publishers block crawlers** (403 / robots). Those sources stay in
   the stack with their failure visible in Run History and the monthly
   audit flags them for replacement.
4. **Rate limits.** Fetching is deliberately polite (≥1s between requests
   to the same host, small per-source item caps). A full 3-company crawl
   takes minutes, not seconds — acceptable for a weekly brief cadence.
