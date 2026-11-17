"""Step 1 — Company research.

Given a company name + website, fetch the homepage and the most relevant
internal pages (about / products / services / pricing), then extract a draft
Company Intelligence Profile: industry, archetype, business lines, target
customers, value proposition. Everything extracted here is traceable to the
company's own public pages; nothing is invented — fields that cannot be
supported by the site copy are left for the founder interview.
"""
import re
from collections import Counter
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import http_util

INDUSTRY_KEYWORDS = {
    "Study-abroad & admissions consulting": ["study abroad", "admissions", "university", "ielts", "gre", "visa", "scholarship", "counsell", "overseas education", "college"],
    "Fintech — broking & investing": ["broker", "trading", "demat", "stocks", "invest", "mutual fund", "fno", "equity", "portfolio", "sebi"],
    "Consumer electronics (D2C audio/wearables)": ["headphones", "earbuds", "smartwatch", "speaker", "wearable", "soundbar", "neckband", "audio"],
    "SaaS / B2B software": ["saas", "software", "platform", "api", "dashboard", "workflow", "subscription", "enterprise"],
    "EdTech — online learning": ["course", "learn", "upskill", "bootcamp", "mentor", "curriculum", "students", "training"],
    "HealthTech": ["health", "doctor", "clinic", "patient", "diagnos", "pharmacy", "wellness"],
    "Travel & hospitality": ["flight", "hotel", "travel", "booking", "holiday", "trip"],
    "E-commerce / D2C retail": ["shop", "buy", "cart", "delivery", "products", "store"],
}

ARCHETYPE_RULES = [
    ("fintech", ["demat", "trading", "broker", "mutual fund"]),
    ("edtech-services", ["study abroad", "admissions", "counsell"]),
    ("d2c-commerce", ["add to cart", "shop now", "free shipping", "cod available"]),
    ("saas", ["start free trial", "book a demo", "api docs", "per user/month"]),
    ("marketplace", ["marketplace", "sellers", "vendors", "list your"]),
    ("services", ["our services", "consulting", "agency"]),
]


def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _page_facts(html, url):
    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text()) if soup.title else ""
    meta = ""
    m = soup.find("meta", attrs={"name": "description"})
    if m:
        meta = _clean(m.get("content", ""))
    headings = [_clean(h.get_text()) for h in soup.find_all(["h1", "h2"])][:14]
    headings = [h for h in headings if 3 <= len(h) <= 110]
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = _clean(soup.get_text(" "))
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if urlparse(href).netloc == urlparse(url).netloc:
            links.append((href, _clean(a.get_text())[:40]))
    return {"title": title, "meta": meta, "headings": headings,
            "text": text[:20000], "links": links}


def classify(text, headings):
    low = (text + " " + " ".join(headings)).lower()
    scores = {ind: sum(low.count(k) for k in kws) for ind, kws in INDUSTRY_KEYWORDS.items()}
    industry = max(scores, key=scores.get) if max(scores.values()) > 0 else "General business"
    archetype = "services"
    for arch, kws in ARCHETYPE_RULES:
        if any(k in low for k in kws):
            archetype = arch
            break
    return industry, archetype, scores


def research_company(name, website):
    """Returns (profile_dict, log_lines)."""
    log = []
    if not website.startswith("http"):
        website = "https://" + website
    home = http_util.fetch(website, check_robots=True)
    if not home["ok"]:
        return None, [f"Homepage fetch failed for {website}: {home['error']}"]
    log.append(f"Fetched homepage {home['final_url']} (HTTP {home['status']})")
    facts = _page_facts(home["text"], home["final_url"])

    # Follow up to 3 relevant internal pages (about / services / products / pricing).
    wanted = ("about", "service", "product", "pricing", "solution", "program", "course", "offer")
    extra_text, extra_headings = [], []
    seen = set()
    for href, label in facts["links"]:
        low = (href + " " + label).lower()
        if any(w in low for w in wanted) and href not in seen and len(seen) < 3:
            seen.add(href)
            r = http_util.fetch(href, check_robots=True)
            if r["ok"]:
                f2 = _page_facts(r["text"], href)
                extra_text.append(f2["text"][:6000])
                extra_headings.extend(f2["headings"])
                log.append(f"Fetched internal page {href}")
            else:
                log.append(f"Internal page skipped {href}: {r['error']}")

    all_text = facts["text"] + " " + " ".join(extra_text)
    industry, archetype, scores = classify(all_text, facts["headings"] + extra_headings)

    # Business-line candidates: the site's own headings, preferring ones that
    # name an actual service (contain an industry keyword) over marketing
    # slogans; slogans are only a fallback.
    ind_kws = INDUSTRY_KEYWORDS.get(industry, [])
    raw_headings, seen_h = [], set()
    for h in facts["headings"] + extra_headings:
        key = h.lower()
        if key not in seen_h and len(h) >= 4:
            seen_h.add(key)
            raw_headings.append(h)
    service_lines = [h for h in raw_headings
                     if any(k in h.lower() for k in ind_kws) and len(h) <= 60]
    lines = (service_lines + [h for h in raw_headings if h not in service_lines])[:6]

    # Frequent meaningful words -> keyword profile used later for relevance scoring.
    words = re.findall(r"[a-z][a-z\-]{3,}", all_text.lower())
    stop = set("with from this that your their more than have will been were about into when what".split())
    keywords = [w for w, _ in Counter(w for w in words if w not in stop).most_common(25)]

    profile = {
        "name": name,
        "website": website,
        "industry": industry,
        "archetype": archetype,
        "product_summary": facts["meta"] or (facts["headings"][0] if facts["headings"] else ""),
        "business_lines": lines,
        "keywords": keywords,
        "industry_scores": {k: v for k, v in scores.items() if v > 0},
        "site_title": facts["title"],
        "pages_fetched": 1 + len(seen),
    }
    log.append(f"Industry classified as '{industry}' (archetype: {archetype}) "
               f"from site copy; {len(lines)} business-line headings extracted.")
    return profile, log
