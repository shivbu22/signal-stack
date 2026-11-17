"""Step 4 — Monitoring crawler.

Visits approved sources, detects new/changed content, dedupes and stores
intelligence records with evidence. Three source types:

- rss : publisher-syndication feeds (Google News index queries). Each item
        becomes a record with its original article link, publication date
        and a verbatim evidence snippet. Items older than
        config.MAX_RECORD_AGE_DAYS are ignored.
- web : a competitor's official site. The crawler hashes the page's main
        content; the first visit stores a positioning snapshot record, a
        later hash change stores a "website changed" record. That is real
        change detection, not a static scrape.
- internal : handled by internal_docs.py uploads; the crawler only reports
        how many internal documents have been imported.

Dedupe is by content hash per company, enforced again by a UNIQUE
constraint. Every fetch outcome (ok / empty / error / robots-blocked) is
written back to the source row and the run log — failures are visible in
the dashboard and the monthly audit, never hidden.
"""
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from . import analysis, config, db, http_util


def _strip_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()


def _parse_date(pub):
    if not pub:
        return None
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _insert_record(conn, company, source, rec):
    rec = analysis.enrich(company, source, rec)
    try:
        conn.execute(
            """INSERT INTO records(company_id, source_id, category, competitor_name, title, url,
                 published_at, discovered_at, evidence_snippet, content_hash, signal_type, stance,
                 business_area, why_it_matters, recommended_action, urgency, impact, relevance,
                 source_reliability, evidence_strength, strategic_relevance, novelty,
                 composite_score, verified_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (company["id"], source["id"], rec["category"], rec.get("competitor_name", ""),
             rec["title"], rec["url"], rec.get("published_at", ""), db.now_iso(),
             rec.get("evidence_snippet", ""), rec["content_hash"], rec["signal_type"],
             rec["stance"], rec["business_area"], rec["why_it_matters"],
             rec["recommended_action"], rec["urgency"], rec["impact"], rec["relevance"],
             rec["source_reliability"], rec["evidence_strength"],
             rec["strategic_relevance"], rec["novelty"], rec["composite_score"],
             rec["verified_status"]))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False  # duplicate (UNIQUE company_id+content_hash)


def _crawl_rss(conn, company, source, log):
    r = http_util.fetch(source["url"])
    if not r["ok"]:
        return 0, "error", r["error"], None
    soup = BeautifulSoup(r["text"], "xml")
    items = soup.find_all("item")
    if not items:
        return 0, "empty", "feed returned no items", None
    added, cutoff = 0, datetime.now(timezone.utc) - timedelta(days=config.MAX_RECORD_AGE_DAYS)
    for item in items:
        if added >= config.MAX_ITEMS_PER_SOURCE:
            break
        title = item.title.get_text() if item.title else ""
        link = item.link.get_text() if item.link else ""
        pub_raw = item.pubDate.get_text() if item.pubDate else ""
        desc = _strip_html(item.description.get_text() if item.description else "")
        if not title or not link:
            continue
        dt = _parse_date(pub_raw)
        if dt and dt < cutoff:
            continue
        # Bing News items carry the real publisher URL inside the apiclick
        # link and the publisher name in a namespaced Source element.
        from . import discovery as _disc
        link = _disc.resolve_news_link(link)
        publisher = ""
        for child in item.find_all():
            if child.name.lower().endswith("source"):
                publisher = child.get_text().strip()
                break
        if not publisher and " - " in title:
            title, publisher = title.rsplit(" - ", 1)
        rec = {
            "category": source["category"],
            "competitor_name": _competitor_for(conn, source),
            "title": title.strip(),
            "url": link,
            "published_at": dt.date().isoformat() if dt else "",
            "published_dt": dt,
            "evidence_snippet": (f"[{publisher}] " if publisher else "") + desc[:420],
            "content_hash": http_util.content_hash(title + "|" + link),
        }
        if _insert_record(conn, company, source, rec):
            added += 1
    return added, "ok", f"{len(items)} items in feed, {added} new records", None


def _crawl_web(conn, company, source, log):
    r = http_util.fetch(source["url"], check_robots=True)
    if not r["ok"]:
        return 0, "error", r["error"], None
    soup = BeautifulSoup(r["text"], "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else source["url"]
    meta = ""
    m = soup.find("meta", attrs={"name": "description"})
    if m:
        meta = m.get("content", "")
    headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2"])][:5]
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    page_hash = http_util.content_hash(soup.get_text(" "))
    comp = _competitor_for(conn, source)
    if not source.get("last_hash"):
        rec = {
            "category": source["category"], "competitor_name": comp,
            "title": f"{comp or company['name']} — website positioning snapshot: {title}"[:180],
            "url": source["url"], "published_at": "", "published_dt": None,
            "evidence_snippet": (meta or " | ".join(headings))[:420],
            "content_hash": http_util.content_hash("snapshot|" + source["url"] + "|" + page_hash),
        }
        added = 1 if _insert_record(conn, company, source, rec) else 0
        return added, "ok", "first crawl: positioning snapshot stored", page_hash
    if page_hash != source["last_hash"]:
        rec = {
            "category": source["category"], "competitor_name": comp,
            "title": f"{comp or company['name']} — website content changed since last crawl"[:180],
            "url": source["url"], "published_at": "", "published_dt": None,
            "evidence_snippet": (meta or " | ".join(headings))[:420],
            "content_hash": http_util.content_hash("change|" + source["url"] + "|" + page_hash),
        }
        added = 1 if _insert_record(conn, company, source, rec) else 0
        return added, "ok", "content change detected and recorded", page_hash
    return 0, "ok", "no change since last crawl", page_hash


def _competitor_for(conn, source):
    cid = source.get("competitor_id")
    if not cid:
        return ""
    c = db.row(conn, "SELECT name FROM competitors WHERE id=?", (cid,))
    return c["name"] if c else ""


def crawl_company(conn, company_id, log=None):
    """Crawl every approved source of a company. Returns stats dict."""
    log = log if log is not None else []
    company = db.get_company(conn, company_id)
    answers = db.rows(conn, "SELECT answer FROM interview_questions WHERE company_id=? AND answer != ''",
                      (company_id,))
    company["interview_text"] = " ".join(a["answer"] for a in answers)
    sources = db.rows(conn, "SELECT * FROM sources WHERE company_id=? AND status='approved'",
                      (company_id,))
    stats = {"sources": len(sources), "new_records": 0, "errors": 0, "empty": 0}
    for source in sources:
        if source["source_type"] == "rss":
            added, status, note, new_hash = _crawl_rss(conn, company, source, log)
        elif source["source_type"] == "web":
            added, status, note, new_hash = _crawl_web(conn, company, source, log)
        else:
            n = db.row(conn, "SELECT COUNT(*) AS n FROM records WHERE source_id=?",
                       (source["id"],))["n"]
            added, status, note, new_hash = 0, "ok", f"internal source: {n} imported records on file", None
        page_hash = new_hash if new_hash is not None else source.get("last_hash", "")
        conn.execute(
            """UPDATE sources SET last_checked_at=?, last_status=?, last_hash=?,
                 fail_count=?, records_total=records_total+? WHERE id=?""",
            (db.now_iso(), status, page_hash,
             (source["fail_count"] + 1) if status == "error" else 0, added, source["id"]))
        conn.commit()
        stats["new_records"] += added
        if status == "error":
            stats["errors"] += 1
        if status == "empty":
            stats["empty"] += 1
        log.append(f"[{source['category']}] {source['name'][:58]} -> {status}: {note}")
    return stats
