"""Step 2 — Adaptive founder interview.

Ten mandated topics (brief §3). The question text is *generated per company*:
a variant is selected by the company's archetype (classified from its own
website in research.py) and the slots are filled with facts extracted from
that company's research profile — its actual business lines, industry,
segments and the competitors discovery found for it. Two companies therefore
never receive the same ten questions: change the company and the wording,
the examples and the follow-ups all change.

Follow-ups: when an answer names something concrete (a competitor, a market,
a product), a follow-up question is generated from the answer itself.
"""
import re

TOPICS = [
    "business_lines", "customer_segments", "customer_problems", "why_us",
    "competitors", "market_changes", "material_developments",
    "growth_priorities", "internal_info", "decisions",
]

# Each topic: {archetype_group: template}. Groups: edtech, fintech, d2c, saas, generic.
# Slots: {company} {industry} {line1} {line2} {competitor} {segment_hint}
Q = {
    "business_lines": {
        "edtech": "Looking at {company}'s own site, the visible lines include {line1} and {line2}. Which of these lines actually produces most of your revenue today, and which are essentially free services that feed the paid ones?",
        "fintech": "{company} shows lines such as {line1} and {line2} on its site. Which line contributes most of your revenue today — brokerage/fees, interest, or value-added services — and how is that mix shifting?",
        "d2c": "Your storefront leads with {line1} and {line2}. Which product line drives the largest share of {company}'s revenue, and which line drives repeat purchases rather than first orders?",
        "saas": "Your site positions {line1} and {line2} as core offerings. Which one accounts for most of {company}'s recurring revenue, and which segment of plans (self-serve vs enterprise) matters most?",
        "generic": "From your website, {company}'s main lines appear to be {line1} and {line2}. Which of these produces most of your revenue today, and are any of them loss-leaders for the others?",
    },
    "customer_segments": {
        "edtech": "Which student segment is worth the most to {company} over a full journey — for example undergrad vs postgrad applicants, or students targeting the US vs the EU — and what makes that segment more valuable?",
        "fintech": "Which trader/investor segment is most valuable to {company} — high-frequency traders, long-term investors, or first-time demat users — and what does each roughly contribute?",
        "d2c": "Which buyer segment gives {company} the best lifetime value — metro early adopters, tier-2 first-time buyers, or repeat upgraders — and how do you recognise them?",
        "saas": "Which customer segment is most valuable to {company} — by company size, industry, or use case — and which segment churns fastest?",
        "generic": "Which customer segment is most valuable to {company}, and what specifically makes them worth more than the average customer?",
    },
    "customer_problems": {
        "edtech": "What are the top problems students come to {company} with before they ever talk to a counsellor — choosing countries, eligibility confusion, visa fear, loan access, or something else?",
        "fintech": "What problems do users hit most often with investing platforms like {company} — charges they don't understand, platform reliability at peak hours, or lack of guidance?",
        "d2c": "What do customers most often complain about or hesitate over before buying products like {line1} — price, battery/performance doubts, service support, or fakes in the market?",
        "saas": "What problem hurts your target customers enough that they go looking for a tool like {company}, and how do they describe it in their own words?",
        "generic": "What are the most common problems or frustrations that bring customers to {company} instead of solving it themselves?",
    },
    "why_us": {
        "edtech": "When a student chooses {company} over {competitor} or a local agent, what is the deciding reason you hear most — and when you lose a student, what reason do they give?",
        "fintech": "When an investor moves their account to {company} instead of staying with {competitor}, what tips the decision — pricing, platform trust, or features?",
        "d2c": "Why does a customer pick {company} over {competitor} at the moment of purchase — and what makes some of them switch away later?",
        "saas": "In deals you win against {competitor}, what is the deciding factor — and in deals you lose, what do prospects say?",
        "generic": "Why do customers choose {company} over alternatives like {competitor}, and what reason do you hear when you lose them?",
    },
    "competitors": {
        "edtech": "Our research surfaced {competitor} and others as alternatives students compare you with. Which 3–5 competitors or substitutes (including local agents and DIY applications) do you actually watch, and what do you watch for in each?",
        "fintech": "Research flagged {competitor} among the brokers users compare with {company}. Which competitors or substitutes (including full-service brokers and global apps) do you track seriously?",
        "d2c": "Research flagged {competitor} in your category. Which brands or substitutes — including marketplace private labels — do you consider real competition for {company}?",
        "saas": "Research flagged {competitor} as an alternative buyers evaluate. Which competitors or substitutes (including spreadsheets and internal tools) belong on {company}'s watch list?",
        "generic": "Research flagged {competitor} as an alternative in your space. Which competitors or substitutes should the system watch for {company}, and why those?",
    },
    "market_changes": {
        "edtech": "What market or policy changes most affect {company} right now — destination-country visa rules, currency moves, test requirements, or university admission caps?",
        "fintech": "Which market or regulatory changes most affect {company} — SEBI rules on F&O or margins, tax changes, or shifts in retail participation?",
        "d2c": "Which market shifts most affect {company} — component/input prices, quick-commerce growth, marketplace fee changes, or import rules?",
        "saas": "Which shifts in your market most affect {company} — AI features becoming table stakes, pricing pressure, or platform/ecosystem changes?",
        "generic": "What are the biggest changes underway in the {industry} market that could help or hurt {company} in the next year?",
    },
    "material_developments": {
        "edtech": "What kind of development would materially change {company}'s plans if it happened tomorrow — a visa-policy reversal in a top destination, a competitor acquiring a test-prep player, or a funding shift?",
        "fintech": "What single development would materially change {company}'s quarter — a SEBI circular, a competitor going zero-brokerage on a segment, or a major outage anywhere in the ecosystem?",
        "d2c": "What development would materially change {company}'s plans — a competitor launching in your price band, a marketplace policy change, or a viral review incident?",
        "saas": "What development would materially change {company}'s roadmap — a platform player bundling your category, or a competitor's major AI launch?",
        "generic": "What kinds of developments — competitor moves, regulation, pricing, technology — would materially affect {company} if they happened, and which would you want flagged within a day?",
    },
    "growth_priorities": {
        "edtech": "What are {company}'s growth priorities for the next 6–12 months — new destination countries, new services like loans or test prep, or deeper university partnerships?",
        "fintech": "What are {company}'s growth priorities for the next 6–12 months — new user acquisition, activation of dormant accounts, or new product lines?",
        "d2c": "What are {company}'s growth priorities for the next 6–12 months — new categories, offline presence, quick-commerce, or exports?",
        "saas": "What are {company}'s growth priorities for the next 6–12 months — new verticals, geographies, or moving upmarket?",
        "generic": "What are {company}'s top growth priorities for the next 6–12 months, and what would success look like for each?",
    },
    "internal_info": {
        "edtech": "What internal information should influence the system's judgement for {company} — counsellor notes, application-funnel drop-offs, visa rejection patterns, or partner-university feedback?",
        "fintech": "What internal data should shape the system's judgement for {company} — support tickets, activation funnels, trade-mix changes, or app-store reviews you collect directly?",
        "d2c": "What internal information should the system weigh for {company} — return reasons, support chats, repeat-purchase data, or marketplace reviews you track?",
        "saas": "What internal information should influence the system for {company} — churn reasons, feature requests, support themes, or sales call notes?",
        "generic": "What internal business information (CRM notes, support themes, sales feedback) should influence the intelligence the system produces for {company}?",
    },
    "decisions": {
        "edtech": "Which recurring decisions should this intelligence help you make — where to spend marketing budget by country, which university partnerships to prioritise, or when to change counsellor capacity?",
        "fintech": "Which decisions should this intelligence help {company} make — pricing responses, feature priorities, or which user segments to invest in?",
        "d2c": "Which decisions should this intelligence help {company} make — pricing and offers, category expansion, or channel mix?",
        "saas": "Which decisions should this intelligence help {company} make — roadmap bets, pricing/packaging, or competitive responses?",
        "generic": "What are the key recurring decisions you want this intelligence system to help {company} make better or faster?",
    },
}

GROUP_BY_ARCHETYPE = {
    "edtech-services": "edtech", "fintech": "fintech", "d2c-commerce": "d2c",
    "saas": "saas", "marketplace": "generic", "services": "generic",
}


def generate_questions(company, competitors):
    """Build the 10 questions for one company from its research profile."""
    profile = company.get("profile") or {}
    lines = profile.get("business_lines") or ["its main offering", "its secondary offering"]
    comp_names = [c["name"] for c in competitors]
    slots = {
        "company": company["name"],
        "industry": company.get("industry") or "your",
        "line1": lines[0],
        "line2": lines[1] if len(lines) > 1 else lines[0],
        "competitor": comp_names[0] if comp_names else "the main alternative in your market",
        "segment_hint": company.get("target_customers") or "",
    }
    group = GROUP_BY_ARCHETYPE.get(company.get("archetype") or "", "generic")
    questions = []
    for i, topic in enumerate(TOPICS, start=1):
        template = Q[topic].get(group) or Q[topic]["generic"]
        questions.append({"position": i, "topic": topic,
                          "question": template.format(**slots)})
    return questions


def followup_for(question_row, answer):
    """Generate a follow-up from the substance of an answer, or None."""
    if not answer or len(answer) < 25:
        return None
    caps = re.findall(r"\b([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)\b", answer)
    topic = question_row["topic"]
    focus = None
    for c in caps:
        if c.lower() not in ("the", "we", "our", "i"):
            focus = c
            break
    if topic == "competitors" and focus:
        return (f"You mentioned {focus}. What specific signals from {focus} — launches, "
                f"pricing, hiring, partnerships — should trigger an alert for you?")
    if topic == "customer_problems" and focus:
        return (f"You mentioned {focus}. Where do customers voice this most — and would "
                f"you like the system to watch those places weekly?")
    if topic == "growth_priorities" and focus:
        return (f"On {focus}: what external signal would tell you this priority is "
                f"working — or that a competitor is getting there first?")
    if focus:
        return (f"You mentioned {focus}. How should that change what the system "
                f"watches or how it ranks signals for you?")
    return None
