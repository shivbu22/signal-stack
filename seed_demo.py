#!/usr/bin/env python3
"""Build the full demonstration: 3 companies end-to-end.

MeetUniversity (mandatory primary) + Zerodha (fintech) + boAt (D2C audio) —
three different industries to prove reusability: different interview
questions, different derived competitors, different Signal Stacks.

For each company: setup (research -> discovery -> interview -> stack) ->
seed interview answers (clearly marked seed_answer=1, editable in the UI)
-> internal sample import -> crawl -> Monday Morning Brief. Then one
monthly audit, then a context-change reassessment demo on Zerodha.

Evidence is written to output/evidence/ (counts.json, run logs).
Safe to re-run: companies that already exist are skipped.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signalstack import audit, brief, crawler, db, engine, internal_docs, reassess

COMPANIES = [
    ("MeetUniversity", "https://www.meetuniversity.com", "meetuniversity_support_sample.csv"),
    ("Zerodha", "https://zerodha.com", "zerodha_support_sample.txt"),
    ("boAt", "https://www.boat-lifestyle.com", "boat_crm_sample.csv"),
]

SEED_ANSWERS = {
    "MeetUniversity": {
        "business_lines": "Most revenue comes from university commissions on successful enrolments and paid counselling programs; test prep, education-loan assistance and visa filing support are smaller but growing lines that also improve conversion of the free counselling funnel.",
        "customer_segments": "Postgraduate applicants targeting the US, UK, Canada and Australia are the most valuable - higher loan sizes and higher commission per enrolment. Undergraduate and Germany/EU applicants are growing fastest.",
        "customer_problems": "Students arrive confused about which country and course fits their profile, anxious about visa rejection, unsure about loan documentation, and overwhelmed by conflicting advice from local agents and social media.",
        "why_us": "Students pick us over local agents for transparent, data-backed shortlisting and end-to-end help (applications, loans, visa) in one place. We lose students when a local agent promises guaranteed admits or when our counsellor response time slips.",
        "competitors": "The rivals we actually watch: IDP Education and Leverage Edu for scale moves, Yocket for community-led growth, AECC, Edwise International and KC Overseas as established counsellor networks, upGrad Abroad and Shiksha as content-led players, and local agents as the real substitute. University partnerships and loan tie-ups are the moves we care about most.",
        "market_changes": "Destination-country visa policy is the big one - US F-1 scrutiny, Canada caps, Australia tightening, and Germany becoming more attractive. Currency moves change affordability conversations every month.",
        "material_developments": "A visa-policy reversal in a top destination, a large competitor acquiring a test-prep or loan player, or a major university changing commission structures would each change our plans within a quarter.",
        "growth_priorities": "Next 6-12 months: grow Germany/EU admissions, deepen education-loan partnerships, and expand university partnerships beyond the current top destinations.",
        "internal_info": "Counsellor notes and CRM drop-off stages, visa rejection patterns by country, and partner-university feedback should all shape what the system flags.",
        "decisions": "Where to spend marketing budget by destination country, which university partnerships to prioritise, and when to add counsellor capacity in a city.",
    },
    "Zerodha": {
        "business_lines": "Brokerage and exchange-related charges on active traders drive most revenue; interest income and value-added tools matter, account opening itself is not the business.",
        "customer_segments": "Active F&O and intraday traders are the most valuable segment; long-term investors are the largest base and the most stable.",
        "customer_problems": "Users complain most about charges they do not fully understand, platform reliability during peak volatility, and lack of guidance when they are losing money.",
        "why_us": "Traders choose us for low, transparent pricing and a fast, reliable platform. We lose users when a competitor offers a feature we lack or during any outage.",
        "competitors": "We watch Groww and Upstox on first-time-investor growth, Angel One on activation offers, and Dhan as the trader-focused challenger; full-service brokers are the substitute for advised clients.",
        "market_changes": "SEBI's F&O and margin rules directly change volumes; tax changes and retail participation trends shift the whole category.",
        "material_developments": "A SEBI circular on derivatives, a competitor going aggressive on pricing, or a major outage anywhere in the ecosystem would change our quarter.",
        "growth_priorities": "Activate dormant accounts, grow the investor (not just trader) base, and expand product lines carefully within regulation.",
        "internal_info": "Support tickets, activation funnel data and app reviews we collect directly should shape what the system flags.",
        "decisions": "Pricing responses, feature priorities, and which user segments to invest in.",
    },
    "boAt": {
        "business_lines": "Audio (TWS earbuds, neckbands, speakers) drives most revenue; wearables are the growth line and the repeat-purchase engine.",
        "customer_segments": "Young metro and tier-2 buyers upgrading from wired audio give the best lifetime value; first-time smartwatch buyers are growing fastest.",
        "customer_problems": "Buyers hesitate over battery life claims, durability and service support; fakes and lookalikes in marketplaces confuse comparisons.",
        "why_us": "Customers pick us for design, bass-forward sound and price; they switch away when a rival launches a similar spec cheaper or the service experience disappoints.",
        "competitors": "We watch Noise and Fire-Boltt on wearables and launch pricing, JBL and Sony as the premium global audio brands, and marketplace private labels on price.",
        "market_changes": "Component prices, quick-commerce growth and marketplace fee changes move our margins and channel mix quickly.",
        "material_developments": "A rival launching in our price band, a marketplace policy change, or a viral quality complaint would each change our plans.",
        "growth_priorities": "Grow wearables, expand quick-commerce presence, and build repeat purchase through accessories.",
        "internal_info": "Return reasons, support chats and repeat-purchase data should shape what the system flags.",
        "decisions": "Pricing and offers, category expansion, and channel mix.",
    },
}


def seed_answers(conn, company_id, company_name, log):
    answers = SEED_ANSWERS.get(company_name, {})
    n = 0
    for topic, text in answers.items():
        cur = conn.execute(
            "UPDATE interview_questions SET answer=?, seed_answer=1 WHERE company_id=? AND topic=? AND is_followup=0",
            (text, company_id, topic))
        n += cur.rowcount
    conn.commit()
    engine.apply_interview_to_profile(conn, company_id)
    added = engine.absorb_interview_competitors(conn, company_id, log)
    log.append(f"Seeded {n} interview answers for {company_name} (marked seed, editable in UI); "
               f"interview-named competitors verified & added: {added}")
    return n


def main():
    conn = db.init_db()
    evidence_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "evidence")
    os.makedirs(evidence_dir, exist_ok=True)
    counts = {}

    for name, website, sample_file in COMPANIES:
        existing = db.row(conn, "SELECT id FROM companies WHERE name=?", (name,))
        log = []
        if existing:
            company_id = existing["id"]
            log.append(f"{name} already configured (id {company_id}); skipping setup")
        else:
            company_id = engine.setup_company(conn, name, website, log)
            if company_id is None:
                print(f"!! setup failed for {name}")
                continue
            seed_answers(conn, company_id, name, log)
            # Internal sample import
            company = db.get_company(conn, company_id)
            src = db.row(conn, "SELECT * FROM sources WHERE company_id=? AND source_type='internal'",
                         (company_id,))
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "data", "internal_samples", sample_file)
            with open(path, "rb") as f:
                added, ilog = internal_docs.import_internal_file(conn, company, src, sample_file, f.read())
            log.extend(ilog)
        # Crawl + brief (idempotent: dedupe prevents double records)
        run_id = db.start_run(conn, "crawl", company_id)
        stats = crawler.crawl_company(conn, company_id, log)
        db.finish_run(conn, run_id, "partial" if stats["errors"] else "success", "\n".join(log))
        company = db.get_company(conn, company_id)
        _, brief_path = brief.generate_brief(conn, company)
        counts[name] = {
            "sources_approved": db.row(conn, "SELECT COUNT(*) n FROM sources WHERE company_id=? AND status='approved'", (company_id,))["n"],
            "competitors": db.row(conn, "SELECT COUNT(*) n FROM competitors WHERE company_id=?", (company_id,))["n"],
            "records_total": db.row(conn, "SELECT COUNT(*) n FROM records WHERE company_id=?", (company_id,))["n"],
            "records_by_category": {r["category"]: r["n"] for r in db.rows(
                conn, "SELECT category, COUNT(*) n FROM records WHERE company_id=? GROUP BY category", (company_id,))},
            "crawl_stats_last_run": stats,
            "brief_file": brief_path,
        }
        print(f"== {name}: {counts[name]}")

    # Monthly audit once
    run_id = db.start_run(conn, "monthly_audit")
    _, audit_path, summary = audit.run_audit(conn)
    db.finish_run(conn, run_id, "success", f"Audit: {audit_path}")
    print(f"== audit: {audit_path}")

    # Reassessment demo on Zerodha: founder changes growth focus.
    z = db.row(conn, "SELECT id FROM companies WHERE name='Zerodha'")
    if z:
        conn.execute("UPDATE companies SET growth_focus=?, context_notes=? WHERE id=?",
                     ("options trading education and investor activation",
                      "Strategy shift: prioritise investor education content and dormant-account activation over pure trader acquisition; SEBI derivatives rules are the dominant external risk.",
                      z["id"]))
        conn.commit()
        company = db.get_company(conn, z["id"])
        rlog = []
        run_id = db.start_run(conn, "reassessment", z["id"])
        changes = reassess.reassess_company(conn, company, rlog)
        report = "# Context-change reassessment demo — Zerodha\n\n" \
                 "Change made: growth_focus set to 'options trading education and investor activation'; " \
                 "context notes updated (investor education + activation priority, SEBI derivatives risk).\n\n" + \
                 "\n".join(f"- {c}" for c in changes) + "\n\nDiscovery log:\n" + "\n".join(rlog)
        with open(os.path.join(evidence_dir, "reassessment_demo.md"), "w") as f:
            f.write(report)
        db.finish_run(conn, run_id, "success", report)
        print(f"== reassessment demo: {len(changes)} stack changes")

    counts["_total_records"] = db.row(conn, "SELECT COUNT(*) n FROM records")["n"]
    with open(os.path.join(evidence_dir, "counts.json"), "w") as f:
        json.dump(counts, f, indent=2)
    with open(os.path.join(evidence_dir, "run_logs.txt"), "w") as f:
        for r in db.rows(conn, "SELECT kind, company_id, status, started_at, log FROM runs ORDER BY id"):
            f.write(f"\n===== {r['started_at']} · {r['kind']} · company={r['company_id']} · {r['status']} =====\n{r['log']}\n")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
