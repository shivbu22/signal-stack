"""Pipeline orchestration: company setup end-to-end.

setup_company() runs, in order: research -> competitor discovery ->
adaptive interview generation -> Signal Stack assembly. Every stage logs
into the runs table so the dashboard's Run History shows exactly what the
system did and what failed.
"""
import json

from . import db, discovery, interview, research


def setup_company(conn, name, website, log=None):
    log = log if log is not None else []
    run_id = db.start_run(conn, "setup_research")
    try:
        profile, rlog = research.research_company(name, website)
        log.extend(rlog)
        if profile is None:
            db.finish_run(conn, run_id, "failed", "\n".join(log))
            return None
        cur = conn.execute(
            """INSERT INTO companies(name, website, industry, archetype, business_model,
                 product_summary, revenue_streams, target_customers, value_prop,
                 context_notes, growth_focus, profile_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, profile["website"], profile["industry"], profile["archetype"], "",
             profile["product_summary"], "", "", "", "", "",
             json.dumps(profile), db.now_iso()))
        company_id = cur.lastrowid
        conn.commit()
        company = db.get_company(conn, company_id)

        competitors = discovery.discover_competitors(company, log)
        for c in competitors:
            cur = conn.execute(
                """INSERT INTO competitors(company_id, name, website, why_relevant,
                     derivation_evidence, profile_summary, discovered_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (company_id, c["name"], c["website"], c["why_relevant"],
                 c["derivation_evidence"], c["profile_summary"], db.now_iso()))
            c["id"] = cur.lastrowid
        conn.commit()
        log.append(f"Competitor discovery complete: {len(competitors)} verified competitors")

        questions = interview.generate_questions(company, competitors)
        for q in questions:
            conn.execute(
                """INSERT INTO interview_questions(company_id, position, topic, question)
                   VALUES (?,?,?,?)""",
                (company_id, q["position"], q["topic"], q["question"]))
        conn.commit()
        log.append(f"Adaptive interview generated: {len(questions)} questions "
                   f"(archetype variant: {company['archetype']})")

        vocab = discovery.vocab_for(company)
        sources = discovery.build_sources(company, competitors, vocab)
        for s in sources:
            conn.execute(
                """INSERT INTO sources(company_id, category, name, url, source_type, competitor_id,
                     query, justification_specific, justification_recent, justification_credible,
                     reason, status, reliability, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)""",
                (company_id, s["category"], s["name"], s["url"], s["source_type"],
                 s.get("competitor_id"), s.get("query", ""), s["justification_specific"],
                 s["justification_recent"], s["justification_credible"], s["reason"],
                 s["reliability"], db.now_iso()))
        conn.commit()
        log.append(f"Signal Stack assembled: {len(sources)} sources across "
                   f"Customers / Competitors / Market / Internal")
        db.finish_run(conn, run_id, "success", "\n".join(log))
        return company_id
    except Exception as e:
        log.append(f"SETUP FAILED: {type(e).__name__}: {e}")
        db.finish_run(conn, run_id, "failed", "\n".join(log))
        raise


def absorb_interview_competitors(conn, company_id, log):
    """S5 discovery channel: competitors the founder names in the interview
    (the brief's own Q5 asks exactly this) are resolved and verified with
    the same live checks as auto-discovered candidates, then added with
    their two standard sources. Names that fail verification are logged
    and discarded — the interview informs, the system verifies."""
    import re
    from . import discovery
    company = db.get_company(conn, company_id)
    answers = {q["topic"]: (q["answer"] or "") for q in db.rows(
        conn, "SELECT topic, answer FROM interview_questions WHERE company_id=? AND is_followup=0", (company_id,))}
    text = answers.get("competitors", "")
    if not text:
        return []
    names = set(discovery._name_phrases(text))
    names |= set(re.findall(r"\b([a-z]{2,}[A-Z][a-zA-Z]+)\b", text))  # camelCase brands: upGrad, boAt
    existing = {c["name"].lower() for c in db.rows(
        conn, "SELECT name FROM competitors WHERE company_id=?", (company_id,))}
    from .http_util import domain_of as _dom
    existing_domains = {_dom(c["website"]) for c in db.rows(
        conn, "SELECT website FROM competitors WHERE company_id=?", (company_id,))}
    keywords = set((company.get("profile") or {}).get("keywords") or [])
    added = []
    for nm in sorted(names):
        count = db.row(conn, "SELECT COUNT(*) n FROM competitors WHERE company_id=?",
                       (company_id,))["n"]
        if nm.lower() in existing or count >= 10:
            continue
        res = discovery._resolve_website(nm, keywords, allow_acronym=True)
        if not res:
            log.append(f"Interview-named competitor not verified, skipped: {nm}")
            continue
        url, ov, how = res
        if _dom(url) in existing_domains:
            log.append(f"Interview-named competitor already tracked under another name, skipped: {nm}")
            continue
        existing_domains.add(_dom(url))
        cur = conn.execute(
            """INSERT INTO competitors(company_id, name, website, why_relevant,
                 derivation_evidence, profile_summary, discovered_at)
               VALUES (?,?,?,?,?,?,?)""",
            (company_id, nm, url,
             f"Named by the founder in the interview (Q: competitors watched) and "
             f"verified live by the system: homepage keyword overlap {ov} with "
             f"{company['name']}'s researched profile.",
             f"Interview answer; resolution via {how}",
             "Founder-named rival; profile snapshot taken from its live homepage.",
             db.now_iso()))
        cid = cur.lastrowid
        conn.commit()
        comp = {"id": cid, "name": nm, "website": url}
        for s in discovery.sources_for_competitor(company["name"], comp):
            conn.execute(
                """INSERT INTO sources(company_id, category, name, url, source_type, competitor_id,
                     query, justification_specific, justification_recent, justification_credible,
                     reason, status, reliability, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)""",
                (company_id, s["category"], s["name"], s["url"], s["source_type"],
                 s.get("competitor_id"), s.get("query", ""), s["justification_specific"],
                 s["justification_recent"], s["justification_credible"], s["reason"],
                 s["reliability"], db.now_iso()))
        conn.commit()
        existing.add(nm.lower())
        added.append(nm)
        log.append(f"Interview-named competitor verified and added: {nm} -> {url} (overlap {ov})")

    # Expansion: co-mention mining around the now-verified set surfaces the
    # next ring of players (same S4 signal as setup discovery).
    from collections import Counter
    vocab = discovery.vocab_for(company)
    verified_names = [c["name"] for c in db.rows(
        conn, "SELECT name FROM competitors WHERE company_id=?", (company_id,))]
    pool = Counter()
    for vn in verified_names[:3]:
        for item in discovery._rss_items(
                discovery.news_index_url(f'"{vn}" {vocab["category_phrase"]}'), limit=8):
            for phrase in discovery._name_phrases(item["title"] + " " + item["desc"]):
                pool[phrase] += 1
    for nm, freq in pool.most_common(12):
        count = db.row(conn, "SELECT COUNT(*) n FROM competitors WHERE company_id=?",
                       (company_id,))["n"]
        if count >= 10:
            break
        if freq < 2 or nm.lower() in existing or nm.lower() == company["name"].lower() \
                or discovery._implausible_name(nm) or discovery._wiki_says_not_company(nm):
            continue
        res = discovery._resolve_website(nm, keywords)
        if not res:
            continue
        url, ov, how = res
        if _dom(url) in existing_domains:
            continue
        existing_domains.add(_dom(url))
        cur = conn.execute(
            """INSERT INTO competitors(company_id, name, website, why_relevant,
                 derivation_evidence, profile_summary, discovered_at)
               VALUES (?,?,?,?,?,?,?)""",
            (company_id, nm, url,
             f"Surfaced by co-mention expansion around the founder-confirmed watch list "
             f"({freq} category news co-mentions) and verified live: homepage keyword "
             f"overlap {ov} with {company['name']}'s researched profile.",
             f"Co-mention expansion; resolution via {how}",
             "Expansion-discovered rival; profile snapshot taken from its live homepage.",
             db.now_iso()))
        cid = cur.lastrowid
        conn.commit()
        for s in discovery.sources_for_competitor(company["name"], {"id": cid, "name": nm, "website": url}):
            conn.execute(
                """INSERT INTO sources(company_id, category, name, url, source_type, competitor_id,
                     query, justification_specific, justification_recent, justification_credible,
                     reason, status, reliability, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)""",
                (company_id, s["category"], s["name"], s["url"], s["source_type"],
                 s.get("competitor_id"), s.get("query", ""), s["justification_specific"],
                 s["justification_recent"], s["justification_credible"], s["reason"],
                 s["reliability"], db.now_iso()))
        conn.commit()
        existing.add(nm.lower())
        added.append(nm)
        log.append(f"Expansion competitor verified and added: {nm} -> {url} (overlap {ov})")
    return added


def apply_interview_to_profile(conn, company_id):
    """Fold interview answers back into the Company Intelligence Profile."""
    answers = {r["topic"]: r["answer"] for r in db.rows(
        conn, "SELECT topic, answer FROM interview_questions WHERE company_id=? AND answer != ''",
        (company_id,))}
    if not answers:
        return
    conn.execute(
        """UPDATE companies SET revenue_streams=?, target_customers=?, value_prop=? WHERE id=?""",
        (answers.get("business_lines", ""), answers.get("customer_segments", ""),
         answers.get("why_us", ""), company_id))
    conn.commit()
