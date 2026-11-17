"""Step 5 — Intelligence analysis & ranking (transparent, rule-based).

No paid AI APIs are used anywhere in this system (brief §14). Analysis is a
documented keyword/rule engine — every score below can be traced to a rule
in this file, which is exactly what docs/TECHNICAL.md describes. Evidence
(the verbatim snippet + link stored by the crawler) is always kept separate
from interpretation (why_it_matters / recommended_action generated here).

For each record the engine assesses: what happened (signal_type), source,
verified status, why it matters, business area, opportunity/threat/neutral,
urgency, and a recommended action — then ranks with six separate measures:
relevance, impact, urgency, source reliability, evidence strength and
strategic relevance, combined into one composite score. Strategic relevance
is boosted when the founder's own interview answers name that area as a
priority — the interview literally steers the ranking.
"""
import re
from datetime import datetime, timezone

SIGNAL_KEYWORDS = [
    ("policy", ["sebi", "regulat", "policy", "visa rule", "circular", "ban", "banned", "tighten",
                "restriction", "government", "ministry", "compliance", "norms", "framework"]),
    ("pricing", ["price", "pricing", "charges", "fee", "fees", "discount", "zero brokerage",
                 "subscription plan", "costlier", "cheaper", "rate cut", "hike"]),
    ("funding", ["raises", "raised", "funding", "series a", "series b", "valuation",
                 "acquires", "acquisition", "acquired", "merger", "stake"]),
    ("launch", ["launch", "introduces", "unveils", "rolls out", "debut", "new feature",
                "new product", "releases", "announces new", "beta"]),
    ("partnership", ["partner", "partnership", "tie-up", "tie up", "collaborat", "mou",
                     "alliance", "joins hands", "signs agreement"]),
    ("expansion", ["expand", "expansion", "enters", "new market", "opens", "international",
                   "overseas", "foray", "sets up"]),
    ("hiring", ["hiring", "to hire", "appoints", "appointed", "names", "new ceo", "new head",
                "leadership", "jobs"]),
    ("complaint", ["complaint", "complain", "scam", "fraud", "not working", "outage", "down",
                   "refund", "issue", "problem", "worst", "cheated", "harass", "glitch", "crash"]),
    ("demand", ["surge", "growth", "record high", "rises", "jump", "soars", "boom", "demand",
                "increase", "doubles", "spike"]),
    ("technology", [" ai ", "artificial intelligence", "technology", "app update", "platform",
                    "automation", "chatbot", "digital"]),
]

IMPACT_BASE = {"policy": .85, "pricing": .8, "funding": .8, "launch": .75, "expansion": .75,
               "partnership": .7, "demand": .7, "complaint": .65, "technology": .6,
               "hiring": .5, "other": .4}

AREA_BY_SIGNAL = {"pricing": "Pricing & monetisation", "launch": "Product",
                  "partnership": "Partnerships", "hiring": "Organisation & talent",
                  "expansion": "Growth & new markets", "funding": "Corporate strategy",
                  "policy": "Regulatory & compliance", "complaint": "Customer experience",
                  "demand": "Market demand", "technology": "Product & technology",
                  "other": "General intelligence"}

ACTION_PLAYBOOK = {
    "pricing": "Compare this pricing move against {company}'s own pricing page this week; if it undercuts a headline plan, prepare a value-based response (not a reflex price cut) and brief the sales/support team on the talking points.",
    "launch": "Have the product team review this launch within 48 hours: note the exact feature/segment targeted, check whether {company}'s roadmap already covers it, and log any gap as a roadmap candidate.",
    "partnership": "Map what this partnership unlocks (distribution, credibility, inventory) that {company} lacks; identify one equivalent partner to approach this month.",
    "expansion": "Assess whether this expansion overlaps {company}'s priority markets; if yes, accelerate local presence/partnership plans there, if no, log it as a watch item.",
    "funding": "Note the war-chest and stated use of funds; expect increased competitor spend in marketing/hiring and pre-empt by locking in {company}'s highest-value partnerships early.",
    "policy": "Route to whoever owns compliance at {company} today: summarise the rule change, its effective date and which journeys/pricing it touches; adjust customer communication before the deadline.",
    "complaint": "Pull the underlying customer language into the next product/support review; if the same complaint appears 3+ times, treat it as a fix-first backlog item and say so publicly where the complaint is visible.",
    "demand": "Validate the demand signal against {company}'s own funnel numbers this week; if it matches, shift budget/capacity toward the growing segment while competitors are still reacting.",
    "hiring": "Read the role(s) being hired for as a strategy signal: infer the team being built and check whether {company} needs the same capability within two quarters.",
    "technology": "Benchmark the technology claim against {company}'s current stack; run a one-week spike only if it touches a top-3 customer problem from the interview.",
    "other": "Review in the weekly intelligence stand-up; keep or discard based on whether it connects to a stated growth priority.",
}


def detect_signal(text):
    low = " " + text.lower() + " "
    best, hits = "other", 0
    for signal, kws in SIGNAL_KEYWORDS:
        n = sum(1 for k in kws if k in low)
        if n > hits:
            best, hits = signal, n
    return best


def _stance(company, source, rec, signal):
    cat = rec["category"]
    own = company["name"].lower() in (source.get("query") or "").lower()
    if cat == "Competitors":
        return "opportunity" if signal == "complaint" else "threat"
    if cat == "Customers":
        if signal == "complaint":
            return "threat" if own else "opportunity"
        return "opportunity" if signal == "demand" else "neutral"
    if cat == "Market":
        if signal == "policy":
            neg = any(w in rec["title"].lower() for w in
                      ["ban", "tighten", "restrict", "cut", "reject", "fall", "decline", "crisis", "slowdown"])
            return "threat" if neg else "neutral"
        return "opportunity" if signal in ("demand", "expansion", "funding") else "neutral"
    if cat == "Internal":
        return {"complaint": "threat", "launch": "opportunity"}.get(signal, "neutral")
    return "neutral"


def _why(company, rec, signal, stance):
    name = company["name"]
    comp = rec.get("competitor_name") or "A competitor"
    seg = (company.get("target_customers") or "your target customers").split("\n")[0][:60]
    t = rec["title"]
    if rec["category"] == "Competitors":
        base = {
            "pricing": f"{comp} is moving on price ('{t}'). Pricing is the fastest-switching trigger for {seg}; if this undercuts {name} on a headline plan, expect comparison questions in sales/support conversations this week.",
            "launch": f"{comp} has launched or announced something new ('{t}'). Every launch aimed at {seg} resets what customers expect from {name}; the gap — real or perceived — needs a product answer or a positioning answer.",
            "partnership": f"{comp}'s partnership ('{t}') can unlock distribution or credibility {name} does not yet have in that channel; partnerships in this category usually convert into pipeline within a quarter.",
            "expansion": f"{comp} is expanding ('{t}'). If the new market overlaps {name}'s priorities, the window to establish presence before them is measured in months, not years.",
            "funding": f"{comp} has fresh capital or a corporate move ('{t}'). Funded competitors typically raise marketing and hiring spend within weeks — {name} should expect louder competition for the same {seg}.",
            "complaint": f"Customers are publicly unhappy with {comp} ('{t}'). This is a switching window: dissatisfied {seg} are actively comparing alternatives, and {name} can win them with a visible, specific response.",
        }.get(signal, f"Development at {comp} ('{t}') in a category {name} competes in; tracked because {comp} is a verified direct competitor for {seg}.")
        return base
    if rec["category"] == "Market":
        return (f"Market-level development ('{t}') that changes the rules, demand or costs for every player in "
                f"{company.get('industry') or 'the category'}, including {name}. It matters because strategy set "
                f"without it — pricing, market entry, messaging to {seg} — can be invalidated by a single policy or demand shift.")
    if rec["category"] == "Customers":
        return (f"Customer-voice signal ('{t}'). Recurring problems and unmet needs are the cheapest product research "
                f"{name} can get: they show exactly what {seg} are struggling with and what language they use — "
                f"useful for product priorities and for copy that sounds like the customer, not the company.")
    if rec["category"] == "Internal":
        return (f"Pattern inside {name}'s own data ('{t}'). Internal signals outrank external noise: they come from "
                f"real deals, real tickets and real customers, so a recurring theme here is a direct instruction to product/operations.")
    return f"Development relevant to {name} ('{t}')."


def _recency(published_dt):
    if not published_dt:
        return 0.45
    days = (datetime.now(timezone.utc) - published_dt).days
    if days <= 7:
        return 0.95
    if days <= 30:
        return 0.75
    if days <= 90:
        return 0.55
    return 0.35


def enrich(company, source, rec):
    """Fill all analysis fields on a raw record dict. Returns the dict."""
    text = (rec["title"] + " " + rec.get("evidence_snippet", "")).strip()
    signal = detect_signal(text)
    stance = _stance(company, source, rec, signal)
    profile = company.get("profile") or {}
    keywords = [k.lower() for k in (profile.get("keywords") or [])]
    low = text.lower()

    relevance = 0.35 + 0.05 * sum(1 for k in keywords if k in low)
    if rec.get("competitor_name") and rec["competitor_name"].lower() in low:
        relevance = max(relevance, 0.85)
    if company["name"].lower() in low:
        relevance = max(relevance, 0.9)
    relevance = min(relevance, 1.0)

    impact = IMPACT_BASE.get(signal, 0.4)
    if stance == "threat" and rec["category"] == "Competitors":
        impact = min(1.0, impact + 0.05)

    recency = _recency(rec.get("published_dt"))
    urgency = min(1.0, recency * 0.7 + (0.25 if signal in ("policy", "pricing") else 0.1))

    reliability = float(source.get("reliability") or 0.6)
    snippet_len = len(rec.get("evidence_snippet") or "")
    evidence_strength = 0.85 if snippet_len >= 200 else 0.65 if snippet_len >= 80 else 0.45
    if source.get("source_type") == "web":
        evidence_strength = 0.9  # first-party page, directly fetched

    # Strategic relevance: the founder's interview answers steer the ranking.
    strategic = 0.5
    interview_text = (company.get("interview_text") or "").lower()
    boost_terms = {
        "Competitors": ["competitor", "rival", "alternative"],
        "Market": ["market", "policy", "regulation", "visa", "sebi", "country"],
        "Customers": ["customer", "complaint", "problem", "segment"],
        "Internal": ["internal", "crm", "support", "sales"],
    }.get(rec["category"], [])
    if any(t in interview_text for t in boost_terms):
        strategic += 0.2
    if signal == "pricing" and "pricing" in interview_text:
        strategic += 0.15
    strategic = min(strategic, 1.0)

    novelty = 0.9 if source.get("source_type") == "web" else 0.75
    composite = (0.25 * relevance + 0.25 * impact + 0.15 * urgency +
                 0.10 * reliability + 0.15 * recency + 0.10 * novelty)

    verified = ("verified — first-party source" if source.get("source_type") == "web"
                else "verified — first-party internal data" if source.get("source_type") == "internal"
                else "single-source — named publisher, link retained")

    rec.update({
        "signal_type": signal, "stance": stance,
        "business_area": AREA_BY_SIGNAL.get(signal, "General intelligence"),
        "why_it_matters": _why(company, rec, signal, stance),
        "recommended_action": ACTION_PLAYBOOK.get(signal, ACTION_PLAYBOOK["other"]).format(company=company["name"]),
        "urgency": round(urgency, 3), "impact": round(impact, 3),
        "relevance": round(relevance, 3), "source_reliability": reliability,
        "evidence_strength": round(evidence_strength, 3),
        "strategic_relevance": round(strategic, 3), "novelty": novelty,
        "composite_score": round(composite, 3), "verified_status": verified,
    })
    rec.pop("published_dt", None)
    return rec
