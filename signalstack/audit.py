"""Monthly Signal Stack Audit.

Checks, per company: dead/erroring URLs, duplicate sources, inactive
sources (approved but producing nothing), declining relevance, and newly
discovered candidate sources from a fresh discovery pass. Produces a
markdown health report with explicit add/remove recommendations. Failed
scheduled runs are visible because every audit/crawl writes a runs row.
"""
import json
import os
import re
from urllib.parse import urlparse

from . import config, db, discovery, http_util


def _norm(url):
    p = urlparse(url)
    return (p.netloc + p.path).rstrip("/").lower()


def run_audit(conn, company_id=None):
    companies = ([db.get_company(conn, company_id)] if company_id
                 else db.rows(conn, "SELECT * FROM companies"))
    lines, summary = [], {}
    lines.append(f"# Signal Stack Audit — {db.now_iso()[:10]}")
    for company in companies:
        cid = company["id"]
        sources = db.rows(conn, "SELECT * FROM sources WHERE company_id=? AND status != 'removed'", (cid,))
        dead, dupes, inactive, healthy = [], [], [], 0
        seen = {}
        for s in sources:
            key = _norm(s["url"])
            if key in seen:
                dupes.append(s)
            seen[key] = s
            if s["fail_count"] >= 2 or s["last_status"] == "error":
                dead.append(s)
            elif s["records_total"] == 0 and s["source_type"] != "internal":
                inactive.append(s)
            else:
                healthy += 1
        # Fresh discovery pass (RSS-level) for new candidate domains.
        vocab = discovery.vocab_for(company)
        existing_domains = set()
        for row in db.rows(conn, "SELECT website FROM competitors WHERE company_id=?", (cid,)):
            existing_domains.add(urlparse(row["website"]).netloc.replace("www.", ""))
        new_candidates = set()
        for q in [f"best {vocab['category_phrase']} India", f"{company['name']} competitors alternatives"]:
            for item in discovery._rss_items(discovery.gnews_url(q), limit=4):
                link = item["link"]
                if not link:
                    continue
                # News-index links are redirects; resolve to the publisher.
                r = http_util.fetch(link)
                if r["ok"]:
                    new_candidates.add(urlparse(r["final_url"]).netloc.replace("www.", ""))
        new_candidates = {d for d in new_candidates
                          if d and d not in existing_domains and d not in discovery.NEWS_DOMAINS
                          and d not in discovery.NOT_COMPETITORS}
        summary[company["name"]] = {
            "sources_total": len(sources), "healthy": healthy, "dead_or_erroring": len(dead),
            "duplicates": len(dupes), "inactive": len(inactive),
            "new_candidate_domains": sorted(new_candidates)[:8],
        }
        lines.append(f"\n## {company['name']}")
        lines.append(f"- Sources in stack: {len(sources)} · healthy: {healthy} · "
                     f"dead/erroring: {len(dead)} · duplicates: {len(dupes)} · inactive (0 records): {len(inactive)}")
        for s in dead:
            lines.append(f"- REMOVE or repair (failing, {s['fail_count']} consecutive failures, last status {s['last_status']}): {s['name']} — {s['url']}")
        for s in dupes:
            lines.append(f"- REMOVE duplicate: {s['name']} — {s['url']}")
        for s in inactive:
            lines.append(f"- REVIEW (approved but has produced no records yet): {s['name']}")
        for d in sorted(new_candidates)[:8]:
            lines.append(f"- CONSIDER adding (surfaced by fresh discovery, unverified): {d} — run competitor verification before approving.")
        if not (dead or dupes or inactive or new_candidates):
            lines.append("- No issues found; stack is healthy.")
    md = "\n".join(lines)
    out_dir = os.path.join(config.OUTPUT_DIR, "audits")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"audit_{db.now_iso()[:10]}.md")
    with open(path, "w") as f:
        f.write(md)
    conn.execute("INSERT INTO audits(company_id, generated_at, summary_json, report_md, file_path) VALUES (?,?,?,?,?)",
                 (company_id, db.now_iso(), json.dumps(summary), md, path))
    conn.commit()
    return md, path, summary
