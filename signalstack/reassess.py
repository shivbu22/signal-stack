"""Context-change reassessment (brief §12 stress test).

When a company's business context changes (founder edits the profile /
context notes — e.g. a new priority market or a dropped product line), the
system must: re-run discovery with the new context, flag sources that no
longer serve the strategy as stale, recommend/add sources that the new
context calls for, and explain every change. This module does exactly
that and returns a human-readable change report.
"""
import re

from . import db, discovery


def _context_terms(company):
    text = " ".join([
        company.get("context_notes") or "", company.get("growth_focus") or "",
        company.get("industry") or "", company.get("target_customers") or "",
    ]).lower()
    return set(re.findall(r"[a-z][a-z\-]{3,}", text))


def reassess_company(conn, company, log):
    cid = company["id"]
    terms = _context_terms(company)
    changes = []

    # 1) Flag sources whose focus no longer matches the context.
    sources = db.rows(conn, "SELECT * FROM sources WHERE company_id=? AND status='approved'", (cid,))
    for s in sources:
        hay = (s["name"] + " " + (s["query"] or "") + " " + s["reason"]).lower()
        # Competitor sources are exempt: competitors matter regardless of phrasing.
        if s["category"] in ("Competitors", "Internal"):
            continue
        overlap = sum(1 for t in terms if t in hay)
        if terms and overlap == 0:
            conn.execute("UPDATE sources SET status='stale' WHERE id=?", (s["id"],))
            changes.append(f"FLAGGED STALE: '{s['name']}' — its focus no longer matches the updated "
                           f"business context (no overlap with current priorities). Kept in the "
                           f"manager as 'stale', excluded from crawls until re-approved.")
    conn.commit()

    # 2) Re-run competitor discovery under the new context; add verified newcomers.
    fresh = discovery.discover_competitors(company, log)
    existing = {c["name"].lower() for c in
                db.rows(conn, "SELECT name FROM competitors WHERE company_id=?", (cid,))}
    vocab = discovery.vocab_for(company)
    for c in fresh:
        if c["name"].lower() in existing:
            continue
        cur = conn.execute(
            "INSERT INTO competitors(company_id, name, website, why_relevant, derivation_evidence, profile_summary, discovered_at) VALUES (?,?,?,?,?,?,?)",
            (cid, c["name"], c["website"], c["why_relevant"], c["derivation_evidence"],
             c["profile_summary"], db.now_iso()))
        c["id"] = cur.lastrowid
        conn.commit()
        for s in discovery.build_sources(company, [c], vocab):
            if s["category"] != "Competitors":
                continue
            conn.execute(
                """INSERT INTO sources(company_id, category, name, url, source_type, competitor_id, query,
                     justification_specific, justification_recent, justification_credible, reason,
                     status, reliability, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)""",
                (cid, s["category"], s["name"], s["url"], s["source_type"], s["competitor_id"],
                 s["query"], s["justification_specific"], s["justification_recent"],
                 s["justification_credible"], s["reason"], s["reliability"], db.now_iso()))
        conn.commit()
        changes.append(f"ADDED COMPETITOR: {c['name']} ({c['website']}) — surfaced by re-running "
                       f"discovery under the updated context and verified against the company's "
                       f"keyword profile. Two sources added (official site + news index).")

    # 3) Context-specific market source from the new priorities.
    focus = (company.get("growth_focus") or "").strip()
    if focus:
        q = f"{focus} {company.get('industry','').split('—')[0].strip().lower()}"
        exists = db.row(conn, "SELECT id FROM sources WHERE company_id=? AND query=?", (cid, q))
        if not exists:
            conn.execute(
                """INSERT INTO sources(company_id, category, name, url, source_type, query,
                     justification_specific, justification_recent, justification_credible, reason,
                     status, reliability, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,'approved',?,?)""",
                (cid, "Market", f"News index: {q}", discovery.gnews_url(q), "rss", q,
                 f"Specific: added because the updated context names '{focus}' as a priority.",
                 "Recent: continuously updated index; dated items only.",
                 "Credible: established publishers; items link to originals.",
                 f"Tracks '{focus}' developments created by the context change.",
                 0.7, db.now_iso()))
            conn.commit()
            changes.append(f"ADDED MARKET SOURCE: news index '{q}' — the new context makes this a first-class watch area.")
    if not changes:
        changes.append("No stack changes were required: every approved source still matches the updated context and discovery surfaced no new verified competitors.")
    return changes
