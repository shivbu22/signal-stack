"""Internal intelligence: import CRM exports / support logs / call notes.

Accepts CSV, Excel-exported CSV and plain text. The importer clusters the
rows/lines into recurring themes (objections, lost-deal reasons, product
requests, risks) using documented keyword clusters, and turns each theme
with at least 2 mentions into an intelligence record whose evidence is
verbatim lines from the uploaded file — traceable to the file, never
paraphrased into existence.
"""
import csv
import io
import re

from . import analysis, db, http_util

THEMES = [
    ("Price / cost objection", ["price", "cost", "expensive", "charges", "fee", "discount", "refund", "loan", "budget"]),
    ("Process confusion", ["confus", "how to", "documents required", "not sure", "unclear", "process", "steps"]),
    ("Delay / slow response", ["delay", "slow", "waiting", "no response", "late", "pending", "follow up", "follow-up"]),
    ("Lost to competitor", ["went with", "chose", "joined", "competitor", "other platform", "another", "switched"]),
    ("Product / feature request", ["request", "wish", "need feature", "please add", "want", "suggestion", "should have"]),
    ("Quality complaint", ["complaint", "bad", "poor", "worst", "unhappy", "issue", "problem", "error", "crash", "bug"]),
    ("Positive signal", ["happy", "great", "excellent", "thank", "satisfied", "recommend", "love"]),
]


def _lines_from_upload(filename, raw_bytes):
    text = raw_bytes.decode("utf-8", errors="ignore")
    lines = []
    if filename.lower().endswith(".csv"):
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return lines
        header = [h.lower() for h in rows[0]]
        text_cols = [i for i, h in enumerate(header)
                     if any(k in h for k in ("note", "feedback", "comment", "subject",
                                             "description", "message", "text", "reason", "detail"))]
        if not text_cols:
            text_cols = list(range(len(header)))
        for r in rows[1:]:
            joined = " | ".join(r[i] for i in text_cols if i < len(r)).strip()
            if len(joined) >= 12:
                lines.append(joined)
    else:
        for line in text.splitlines():
            line = line.strip(" -\t")
            if len(line) >= 12:
                lines.append(line)
    return lines


def import_internal_file(conn, company, source, filename, raw_bytes):
    """Import one file under the company's Internal source. Returns (records_added, log)."""
    log = []
    lines = _lines_from_upload(filename, raw_bytes)
    if not lines:
        return 0, [f"Internal import: no usable text lines found in {filename}"]
    buckets = {name: [] for name, _ in THEMES}
    for line in lines:
        low = line.lower()
        for theme, kws in THEMES:
            if any(k in low for k in kws):
                buckets[theme].append(line)
                break
    added = 0
    for theme, hits in buckets.items():
        if len(hits) < 2:
            continue
        evidence = " || ".join(h[:130] for h in hits[:3])
        rec = {
            "category": "Internal",
            "competitor_name": "",
            "title": f"Internal pattern: {theme} — {len(hits)} mentions in {filename}"[:180],
            "url": f"internal://{company['name'].lower().replace(' ', '-')}/{filename}",
            "published_at": "", "published_dt": None,
            "evidence_snippet": evidence[:420],
            "content_hash": http_util.content_hash(f"internal|{company['id']}|{filename}|{theme}|{len(hits)}"),
        }
        rec = analysis.enrich(company, source, rec)
        # Internal records: the theme drives the stance more precisely than keywords alone.
        if theme in ("Price / cost objection", "Delay / slow response", "Quality complaint", "Lost to competitor"):
            rec["stance"] = "threat"
        elif theme in ("Product / feature request", "Positive signal"):
            rec["stance"] = "opportunity"
        try:
            conn.execute(
                """INSERT INTO records(company_id, source_id, category, competitor_name, title, url,
                     published_at, discovered_at, evidence_snippet, content_hash, signal_type, stance,
                     business_area, why_it_matters, recommended_action, urgency, impact, relevance,
                     source_reliability, evidence_strength, strategic_relevance, novelty,
                     composite_score, verified_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (company["id"], source["id"], rec["category"], "", rec["title"], rec["url"],
                 "", db.now_iso(), rec["evidence_snippet"], rec["content_hash"], rec["signal_type"],
                 rec["stance"], rec["business_area"], rec["why_it_matters"], rec["recommended_action"],
                 rec["urgency"], rec["impact"], rec["relevance"], rec["source_reliability"],
                 rec["evidence_strength"], rec["strategic_relevance"], rec["novelty"],
                 rec["composite_score"], rec["verified_status"]))
            conn.commit()
            added += 1
        except Exception:
            conn.rollback()
    log.append(f"Internal import {filename}: {len(lines)} lines -> {added} pattern records")
    return added, log
