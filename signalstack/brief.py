"""Step 6 — Monday Morning Brief generator.

Builds the brief in the brief's exact 10-section structure, only from
records actually collected by the crawler (each carries its source link and
verbatim evidence snippet). If a category produced no meaningful
development, the section says so explicitly — developments are never
manufactured to fill a section.
"""
import os
import re

from . import config, db

TOP_N = 6


def _fmt_rec(r, show_action=False):
    lines = [f"- **{r['title']}**"]
    lines.append(f"  - Why it matters: {r['why_it_matters']}")
    if show_action:
        lines.append(f"  - Recommended action: {r['recommended_action']}")
    meta = (f"Signal: {r['signal_type']} · Stance: {r['stance']} · Area: {r['business_area']} · "
            f"Score: {r['composite_score']} (relevance {r['relevance']}, impact {r['impact']}, "
            f"urgency {r['urgency']}, source reliability {r['source_reliability']}, "
            f"evidence strength {r['evidence_strength']}, strategic relevance {r['strategic_relevance']})")
    lines.append(f"  - {meta}")
    lines.append(f"  - Evidence: \"{r['evidence_snippet'][:240]}\" — {r['url']}")
    return "\n".join(lines)


def _section_records(conn, company_id, category, limit=TOP_N):
    return db.rows(conn, """SELECT * FROM records WHERE company_id=? AND category=?
                            ORDER BY composite_score DESC LIMIT ?""",
                   (company_id, category, limit))


def generate_brief(conn, company):
    cid = company["id"]
    all_recs = db.rows(conn, "SELECT * FROM records WHERE company_id=? ORDER BY composite_score DESC", (cid,))
    top5 = all_recs[:5]
    customers = _section_records(conn, cid, "Customers")
    competitors = _section_records(conn, cid, "Competitors", limit=10)
    market = _section_records(conn, cid, "Market")
    internal = _section_records(conn, cid, "Internal")
    threats = [r for r in all_recs if r["stance"] == "threat"][:6]

    # Opportunities: opportunity-stance records first; customer-problem
    # patterns are unmet needs, i.e. evidence-backed opportunities.
    opps = [r for r in all_recs if r["stance"] == "opportunity"]
    if len(opps) < 3:
        extra = [r for r in customers if r not in opps]
        opps = (opps + extra)[:max(3, len(opps))]
    opps = opps[:5]

    date_label = db.now_iso()[:10]
    out = []
    out.append(f"# Monday Morning Brief — {company['name']}")
    out.append(f"*Generated {date_label} · Sources monitored: "
               f"{db.row(conn, 'SELECT COUNT(*) n FROM sources WHERE company_id=? AND status=\'approved\'', (cid,))['n']} · "
               f"Intelligence records on file: {len(all_recs)} · "
               f"Method: evidence (verbatim, linked) is kept separate from interpretation throughout.*")
    out.append("")
    out.append("## 1. Executive Summary — the five most important developments")
    if top5:
        for i, r in enumerate(top5, 1):
            out.append(f"{i}. **{r['title']}** — {r['why_it_matters']} ({r['url']})")
    else:
        out.append("No intelligence records have been collected yet. Run a crawl first; this brief does not manufacture developments.")
    out.append("")
    out.append("## 2. Customer Signals")
    if customers:
        out.extend(_fmt_rec(r) for r in customers)
    else:
        out.append("No meaningful customer-signal development was collected in this period. The customer sources were checked; silence is reported, not filled.")
    out.append("")
    out.append("## 3. Competitor Intelligence")
    if competitors:
        by_comp = {}
        for r in competitors:
            by_comp.setdefault(r["competitor_name"] or "Unspecified competitor", []).append(r)
        for comp, recs in by_comp.items():
            out.append(f"### {comp}")
            out.extend(_fmt_rec(r) for r in recs)
    else:
        out.append("No meaningful competitor development was collected in this period.")
    out.append("")
    out.append("## 4. Market Intelligence")
    if market:
        out.extend(_fmt_rec(r) for r in market)
    else:
        out.append("No meaningful market development was collected in this period.")
    out.append("")
    out.append("## 5. Internal Business Intelligence")
    if internal:
        out.extend(_fmt_rec(r) for r in internal)
    else:
        out.append("No internal data has been imported yet. Upload a CRM export, support log or call notes (CSV/TXT) to activate this section.")
    out.append("")
    out.append("## 6. Opportunities Identified")
    if opps:
        for i, r in enumerate(opps, 1):
            prio = "High" if r["composite_score"] >= 0.62 else "Medium" if r["composite_score"] >= 0.5 else "Watch"
            out.append(f"### Opportunity {i} (priority: {prio}) — from: {r['title']}")
            out.append(f"- Evidence: \"{r['evidence_snippet'][:240]}\" — {r['url']}")
            out.append(f"- Impact: {r['business_area']}; impact score {r['impact']}, relevance {r['relevance']}. {r['why_it_matters']}")
            out.append(f"- Next step: {r['recommended_action']}")
    else:
        out.append("No evidence-backed opportunity cleared the bar this period. Rather than inventing opportunities, the system flags this as a quiet week and keeps monitoring.")
    out.append("")
    out.append("## 7. Risks & Threats")
    if threats:
        out.extend(_fmt_rec(r, show_action=True) for r in threats)
    else:
        out.append("No threat-stance development was collected in this period.")
    out.append("")
    out.append("## 8. Recommended Actions for This Week")
    actions, seen = [], set()
    for r in all_recs:
        if r["recommended_action"] and r["recommended_action"] not in seen:
            seen.add(r["recommended_action"])
            actions.append(f"- ({r['business_area']}) {r['recommended_action']}")
        if len(actions) >= 5:
            break
    out.extend(actions or ["- Run the first crawl to populate the intelligence feed."])
    out.append("")
    out.append("## 9. What We Should Watch")
    watch = []
    quiet = db.rows(conn, """SELECT c.name FROM competitors c WHERE c.company_id=?
                             AND NOT EXISTS (SELECT 1 FROM records r WHERE r.company_id=c.company_id
                                             AND r.competitor_name=c.name)""", (cid,))
    for q in quiet:
        watch.append(f"- **{q['name']}** produced no collected signals this period — either genuinely quiet or a source-health issue; the monthly audit verifies which.")
    for r in [x for x in all_recs if x["stance"] == "neutral"][:3]:
        watch.append(f"- {r['title']} ({r['url']}) — neutral for now; a follow-up development would change its stance.")
    weak = db.rows(conn, """SELECT name FROM sources WHERE company_id=? AND status='approved'
                            AND last_status IN ('error','empty')""", (cid,))
    for w in weak:
        watch.append(f"- Source health: '{w['name']}' last returned an error/empty result — see Run History and the monthly audit.")
    out.extend(watch or ["- All monitored competitors produced signals this period; keep the weekly cadence."])
    out.append("")
    out.append("## 10. Source Appendix")
    out.append("| # | Item | Source | Published | Discovered | Verification | Evidence snippet |")
    out.append("|---|------|--------|-----------|------------|--------------|------------------|")
    for i, r in enumerate(all_recs, 1):
        src = db.row(conn, "SELECT name FROM sources WHERE id=?", (r["source_id"],))
        ev = re.sub(r"\|", "/", r["evidence_snippet"][:110])
        out.append(f"| {i} | [{r['title'][:70]}]({r['url']}) | {(src or {}).get('name', '')[:40]} | "
                   f"{r['published_at'] or '—'} | {r['discovered_at'][:10]} | {r['verified_status']} | {ev} |")
    out.append("")
    out.append("---")
    out.append("*Limitations: news-index records are single-source until corroborated; customer-voice items are "
               "reported speech (sentiment evidence, not verified fact); website snapshots record positioning at "
               "crawl time. AI confidence is never treated as proof — every item above links to its evidence.*")
    md = "\n".join(out)

    slug = re.sub(r"[^a-z0-9]+", "-", company["name"].lower()).strip("-")
    brief_dir = os.path.join(config.OUTPUT_DIR, "briefs")
    os.makedirs(brief_dir, exist_ok=True)
    path = os.path.join(brief_dir, f"{slug}_monday_brief_{date_label}.md")
    with open(path, "w") as f:
        f.write(md)
    conn.execute("INSERT INTO briefs(company_id, generated_at, period_label, content_md, file_path) VALUES (?,?,?,?,?)",
                 (cid, db.now_iso(), f"Week of {date_label}", md, path))
    conn.commit()
    return md, path
