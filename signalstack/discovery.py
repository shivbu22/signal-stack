"""Step 3 — Source & competitor discovery.

Nothing here is hard-coded per company. Competitors are *derived* at setup
time by a documented multi-signal pipeline (see the long comment above
discover_competitors): Wikipedia's link graph, news listicle/comparison
mining, news-corpus co-mention mining, and a co-mention expansion round —
followed, for every candidate, by live verification against the target
company's own researched keyword profile. Only candidates whose own
homepage confirms they operate in the same space survive, and each
survivor stores its derivation evidence.

Signal Stack sources are then assembled per company from the discovered
competitors plus market/customer news queries derived from the industry,
each with a written Specific / Recent / Credible justification.
"""
import re
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

from . import http_util

# News index: Bing News RSS — a publisher-syndication endpoint whose item
# links carry the *real* publisher URL (in the apiclick `url` parameter),
# so every record can cite its original article directly. (Google News RSS
# was evaluated first; its article links are opaque redirect tokens that
# rate-limit programmatic resolution, so Bing News is the primary index and
# the choice is documented in docs/TECHNICAL.md.)
NEWS_INDEX = "https://www.bing.com/news/search?q={q}&format=rss&mkt=en-IN"

# Domains that are publishers/platforms, never competitor candidates.
NOT_COMPETITORS = {
    "google.com", "youtube.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "linkedin.com", "wikipedia.org", "amazon.in", "amazon.com",
    "flipkart.com", "play.google.com", "apps.apple.com", "quora.com",
    "reddit.com", "medium.com", "substack.com",
}
NEWS_DOMAINS = {
    "timesofindia.indiatimes.com", "economictimes.indiatimes.com", "indiatimes.com",
    "moneycontrol.com", "livemint.com", "business-standard.com", "thehindu.com",
    "thehinducentre.com", "hindustantimes.com", "ndtv.com", "yourstory.com", "inc42.com",
    "entrackr.com", "thehindubusinessline.com", "financialexpress.com",
    "businesstoday.in", "forbesindia.com", "indiatoday.in", "news18.com",
    "firstpost.com", "theprint.in", "scroll.in", "bloombergquint.com",
    "bqprime.com", "cnbctv18.com", "zeebiz.com", "techcrunch.com", "livemintmoney.com",
    "livehindustan.com", "medianama.com",
    "indianexpress.com", "deccanherald.com", "theweek.in", "outlookindia.com",
    "freepressjournal.in", "telegraphindia.com", "dnaindia.com",
}

# Per-industry *query vocabulary* (keyed by the industry the research step
# classified — never by company). Generic fallback uses the company's own
# extracted keywords.
INDUSTRY_VOCAB = {
    "Study-abroad & admissions consulting": {
        "category_phrase": "study abroad consultants",
        "market_queries": ["study abroad visa policy changes", "international student admissions policy",
                           "Indian students studying abroad trends"],
        "customer_queries": ["students study abroad problems complaints", "study abroad visa rejection students experience"],
    },
    "Fintech — broking & investing": {
        "category_phrase": "discount stock brokers",
        "market_queries": ["SEBI broking regulations circular", "retail investors India demat growth",
                           "stock market India retail participation"],
        "customer_queries": ["traders complaints brokerage app charges", "demat account users problems reviews"],
    },
    "Consumer electronics (D2C audio/wearables)": {
        "category_phrase": "audio wearables brands",
        "market_queries": ["India wearables market growth", "TWS earbuds market India",
                           "consumer electronics India demand trends"],
        "customer_queries": ["earbuds buyers complaints India", "smartwatch users problems reviews India"],
    },
}
GENERIC_VOCAB = {
    "category_phrase": "companies",
    "market_queries": ["{industry} market India trends", "{industry} regulation policy India"],
    "customer_queries": ["{industry} customers complaints", "{industry} users reviews problems"],
}


def vocab_for(company):
    v = INDUSTRY_VOCAB.get(company.get("industry") or "")
    if v:
        return v
    g = dict(GENERIC_VOCAB)
    ind = (company.get("industry") or "business").split("—")[0].strip().lower()
    g["market_queries"] = [q.format(industry=ind) for q in g["market_queries"]]
    g["customer_queries"] = [q.format(industry=ind) for q in g["customer_queries"]]
    g["category_phrase"] = ind + " companies"
    return g


def news_index_url(query):
    return NEWS_INDEX.format(q=quote_plus(query))


# Backwards-compatible alias
gnews_url = news_index_url


def resolve_news_link(link):
    """Bing News item links are apiclick URLs carrying the real publisher
    URL in the `url` query parameter. Decode it; pass other links through."""
    if link and "apiclick" in link:
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(link).query)
        if qs.get("url"):
            return qs["url"][0]
    return link


def _rss_items(url, limit=10):
    r = http_util.fetch(url)
    if not r["ok"]:
        return []
    try:
        soup = BeautifulSoup(r["text"], "xml")
    except Exception:
        return []
    items = []
    for item in soup.find_all("item")[:limit]:
        title = item.title.get_text() if item.title else ""
        link = item.link.get_text() if item.link else ""
        pub = item.pubDate.get_text() if item.pubDate else ""
        desc = item.description.get_text() if item.description else ""
        items.append({"title": title, "link": link, "pub": pub, "desc": desc})
    return items


GNEWS_INDEX = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def _gnews_items(query, limit=15):
    """Google News RSS items — used ONLY for name mining in discovery (its
    article links are opaque redirect tokens, so records never cite it;
    the record index is Bing News, whose links resolve to publishers)."""
    from urllib.parse import quote_plus as _qp
    return _rss_items(GNEWS_INDEX.format(q=_qp(query)), limit=limit)


def _candidate_name(anchor, domain):
    a = re.sub(r"\s+", " ", anchor or "").strip()
    if 2 <= len(a) <= 32 and not a.lower().startswith(("read", "click", "visit", "official", "website", "home")):
        return a
    base = domain.split(".")[0]
    return base.replace("-", " ").title()


# --------------------------------------------------------------------------
# Competitor discovery — multi-signal, everything verified live.
#
# General web search is not programmatically accessible on free tiers from
# most networks (documented in docs/TECHNICAL.md), so candidates are
# generated from four independent public signals and then *verified*:
#   S1 Wikipedia graph — the company's and the industry concept's articles
#      link to peer companies; their official websites come from the
#      articles themselves.
#   S2 News listicles — comparison/best-of articles from the news index;
#      company names appear in their headings and outbound links.
#   S3 News corpus mining — capitalised names recurring across category
#      news titles/descriptions (co-mentions, "X vs Y" coverage).
#   S4 Expansion — one co-mention query per verified competitor surfaces
#      the next ring of players named alongside them.
#   S5 Founder interview — the brief's own interview asks which competitors
#      the company watches (engine.absorb_interview_competitors); those
#      names go through the identical resolve + verify gate before being
#      added. The interview informs; the system verifies.
# A candidate only becomes a competitor after its own homepage is fetched
# and scores a keyword-overlap with the target company's researched
# profile — names that cannot be verified are discarded, and the log
# (Run History) shows every rejection and why.
# --------------------------------------------------------------------------

WIKI_API = "https://en.wikipedia.org/w/api.php"

NAME_STOPWORDS = set("""
the a an and or of for in on to with from by at as is are was were be been it its this that these those
india indian new top best how why what when where who will would can could should may might must
news today latest update updates report reports market markets growth global international national
study abroad students student visa university universities college colleges education educational
school schools council board association group company companies limited ltd inc corp corporation
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday year years month week day time times
us uk usa america american canada canadian australia australian germany german europe european china
english hindi delhi mumbai bangalore bengaluru hyderabad chennai pune kolkata ahmedabad
said says say new one two three four five first second third also more most other others
i me my we our you your he she they them his her their not no yes if but so than then there here
""".split())


def _wiki(params):
    import requests
    params = dict(params, format="json")
    try:
        r = requests.get(WIKI_API, params=params,
                         headers={"User-Agent": http_util.config.USER_AGENT}, timeout=20)
        return r.json()
    except Exception:
        return {}


def _wiki_search_titles(query, limit=5):
    d = _wiki({"action": "query", "list": "search", "srsearch": query, "srlimit": limit})
    return [x["title"] for x in d.get("query", {}).get("search", [])]


def _wiki_article(title):
    """Return {links, website, extract} for a Wikipedia article."""
    d = _wiki({"action": "query", "prop": "links|extracts|extlinks", "titles": title,
               "pllimit": "500", "plnamespace": "0", "exintro": "1", "explaintext": "1",
               "ellimit": "500"})
    pages = d.get("query", {}).get("pages", {})
    for pg in pages.values():
        links = [l["title"] for l in pg.get("links", [])]
        extract = pg.get("extract", "")
        name_key = re.sub(r"[^a-z0-9]", "", title.lower().split("(")[0])
        options = []
        for el in pg.get("extlinks", []):
            u = el.get("*", "")
            dom = http_util.domain_of(u)
            from urllib.parse import urlparse as _up
            if (u.startswith("http") and dom and dom not in NOT_COMPETITORS
                    and "archive.org" not in dom and "wikimedia" not in dom
                    and not dom.endswith("gov") and "facebook" not in dom
                    and "instagram" not in dom and "twitter" not in dom
                    and "linkedin" not in dom and "youtube" not in dom
                    and len([p for p in _up(u).path.split("/") if p]) <= 1):
                # official sites live at the root; a deep link is an article
                # (one Wikipedia citation once made a TV company's news
                # article its 'official website')
                base = re.sub(r"[^a-z0-9]", "", dom.split(".")[0])
                score = 2 if base and (base in name_key or name_key.startswith(base)) else 0
                options.append((score, u))
        options.sort(key=lambda x: -x[0])
        website = options[0][1] if options else ""
        return {"links": links, "website": website, "extract": extract}
    return {"links": [], "website": "", "extract": ""}


def _looks_like_company(extract):
    low = extract.lower()
    if not any(w in low for w in ("company", "platform", "firm", "brand", "broker",
                                  "provider", "service", "organisation", "organization")):
        return False
    if "founded" in low or "headquarter" in low:
        return True
    # "X is an Indian financial services company…" style leads also count.
    return bool(re.search(r"\bis an?\b[^.]{0,60}\b(company|firm|platform|brokerage|brand|manufacturer|retailer|provider|organisation|organization|agency|network)\b", low))


def _name_phrases(text):
    """Capitalised candidate names from a text fragment."""
    out = []
    for m in re.findall(r"\b([A-Z][a-zA-Z&.\-]+(?: [A-Z][a-zA-Z&.\-]+){0,2})\b", text or ""):
        words = [w.strip(".&-") for w in m.split()]
        if all(w.lower() in NAME_STOPWORDS for w in words):
            continue  # pure generic phrase; a distinctive word saves the name
            # (e.g. 'IDP Education', 'Edwise International' are real brands)
        if len(m) < 3 or m.isupper() and len(m) <= 2:
            continue
        out.append(m.strip(" .&-"))
    return out


MEDIA_OR_GENERIC = ("News", "Times", "Today", "Post", "Express", "Herald", "Tribune",
                    "Chronicle", "Magazine", "Gazette", "Journal", "Channel",
                    "Hindi", "Bangla", "Tamil", "Telugu", "Malayalam", "Kannada",
                    "Punjabi", "Marathi", "Gujarati", "Odia", "Wikipedia", "Reuters", "BBC")


def _is_media_domain(dom):
    """True for news/publisher/platform domains — including their
    subdomains (frontline.thehindu.com is The Hindu, not a competitor)."""
    if not dom:
        return True
    return any(dom == d or dom.endswith("." + d) for d in NEWS_DOMAINS | NOT_COMPETITORS)


GENERIC_VERIFY_TERMS = {
    "every", "started", "meet", "help", "helps", "helping", "support", "process",
    "experience", "expert", "journey", "personalized", "best", "new", "free",
    "online", "digital", "team", "work", "works", "make", "makes", "get", "one",
    "also", "across", "within", "trusted", "leading", "quality", "care", "easy",
    "simple", "fast", "secure", "safe", "smart", "powerful", "innovative",
    "offer", "offers", "offering", "provides", "provide", "including", "include",
    "includes", "range", "wide", "assistance", "guidance",
}


def _verify_homepage(url, keywords, min_overlap, name=None, min_distinctive=1):
    """Fetch a candidate homepage; return (overlap, title) or (0, '').
    When a candidate name is given, the site must actually brand itself
    with that name (in its title or its domain) — this kills generic
    one-word phrases mined from news text ('Tech', 'Bit', 'Bangla')
    that happen to resolve to keyword-rich unrelated sites."""
    r = http_util.fetch(url, check_robots=True, timeout=12)
    if not r["ok"]:
        return 0, ""
    soup = BeautifulSoup(r["text"], "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if any(p in (title + r["text"][:2000]).lower() for p in ("domain for sale", "coming soon", "parked")):
        return 0, ""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ").lower()
    overlap = sum(1 for k in keywords if k in text)
    distinctive = sum(1 for k in keywords if k not in GENERIC_VERIFY_TERMS and k in text)
    if overlap < min_overlap or distinctive < min_distinctive:
        return 0, title  # generic-word overlap alone proves nothing (a food
        # site matches 'expert/support/experience' too — measured: Slurrp
        # scored 6 generic matches, 0 distinctive); a real category peer
        # always shares at least 1 distinctive industry term
    if name:
        token = re.sub(r"[^a-z0-9]", "", name.lower().split()[0])
        dom_base = re.sub(r"[^a-z0-9]", "", http_util.domain_of(url).split(".")[0])
        if token and token not in title.lower().replace(" ", "") and token not in dom_base \
                and token not in text[:1500].replace(" ", ""):
            return 0, title
    return overlap, title


GENERIC_SINGLE_WORDS = {"world", "wearables", "telecom", "global", "gadgets",
                        "electronics", "mobiles", "audio", "fashion", "travel",
                        "hotels", "flights", "insurance", "loans", "jobs",
                        "according", "however", "meanwhile", "overall",
                        "recently", "additionally", "furthermore", "moreover",
                        "therefore", "among", "bluetooth", "wireless",
                        "issues", "report", "reports", "update", "updates",
                        "analysis", "review", "reviews"}

NAV_PHRASES = {"about us", "contact us", "read more", "learn more", "know more",
               "view all", "our team", "home", "blog", "careers", "sign in",
               "log in", "get started", "click here", "see more", "show more",
               "privacy policy", "terms & conditions", "terms and conditions",
               "terms of use", "terms of service", "cookie policy"}

# Media outlets, platforms and generic nouns that corpus mining surfaces as
# if they were companies. Matched against the spaceless lowercase name.
MEDIA_FRAGMENTS = ("news", "times", "outlook", "herald", "tribune", "chronicle",
                   "gazette", "journal", "magazine", "subscription", "whatsapp",
                   "facebook", "instagram", "youtube", "twitter", "linkedin",
                   "telegram", "wikipedia", "reuters", "bloomberg", "epaper",
                   "sportstar", "statista")


REGULATOR_ACRONYMS = {"NSE", "BSE", "SEBI", "RBI", "IRDAI", "TRAI", "FSSAI",
                      "DGCA", "MCA", "EPFO", "NPCI", "UIDAI", "CBDT", "CBIC"}

# Well-known *products/services* of larger companies that corpus mining
# surfaces as if they were companies in their own right.
PRODUCT_NAMES = {"itunes", "airpods", "ipad", "iphone", "kindle", "alexa",
                 "siri"}


def _implausible_name(name):
    """Corpus mining surfaces navigation labels and sentence fragments
    ('ABOUT US', 'Read More') that are not companies. Reject them cheaply.
    Regulators/exchanges are market actors (tracked as Market sources),
    never competitors."""
    low = re.sub(r"\s+", " ", (name or "").strip().lower())
    if low in NAV_PHRASES or low.replace(" ", "") in PRODUCT_NAMES:
        return True
    if name.strip() in REGULATOR_ACRONYMS:
        return True
    if " " in name and name.isupper():
        return True  # ALL-CAPS multiword strings are page furniture, not brands
    spaceless = low.replace(" ", "")
    if any(f in spaceless for f in MEDIA_FRAGMENTS):
        return True
    if low.endswith(" desk"):
        return True  # newsroom bylines ('TOI World Desk') are not companies
    words = name.split()
    if len(words) == 1:
        if words[0].isupper() and len(words[0]) <= 4 \
                or re.fullmatch(r"[A-Z]{2,4}s?", words[0]):
            return True  # bare acronyms from news text (MTF, IPO, KPIs) are
            # concepts, not brands; founder-named acronyms (JBL) enter via
            # the interview, which does not use this filter
        if words[0].lower() in GENERIC_SINGLE_WORDS:
            return True  # category nouns / sentence fragments ('Wearables',
            # 'Telecom', 'According', 'Bluetooth')
    return False


def _wiki_says_not_company(name):
    """Wikipedia gate for single-word and ambiguous names: if an article
    with the exact name exists and neither it nor the '<name> company'
    article reads as a company, the name is a thing, not a firm
    ('Bluetooth' the standard, 'AirPods' the product). 'Apple' survives:
    its exact article is a fruit, but 'Apple Inc.' reads as a company."""
    exact = _wiki_article(name)
    if exact["extract"] and _looks_like_company(exact["extract"]):
        return False
    for t in _wiki_search_titles(f"{name} company", limit=2):
        art = _wiki_article(t)
        if art["extract"] and _looks_like_company(art["extract"]):
            return False
    return bool(exact["extract"])


def _is_wiki_concept(name):
    """A multi-word name that Wikipedia defines as a *concept* ('Technical
    analysis', 'Vehicle subscription') is not a company, however
    keyword-rich the matching website is. Near-titles count too ('Trading
    Strategies' -> 'Trading strategy'). Checked on EVERY channel: a
    listicle content link once paired the phrase 'Trading Strategies' with
    a real trading firm's homepage."""
    def _norm(s):
        def stem(w):
            if w.endswith("ies") and len(w) > 3:
                return w[:-3] + "y"  # strategies -> strategy
            return w.rstrip("s")
        return " ".join(stem(w) for w in s.lower().split())
    art = _wiki_article(name)
    if not art["extract"]:
        for t in _wiki_search_titles(name, limit=2):
            if _norm(t) == _norm(name):
                art = _wiki_article(t)
                break
    return bool(art["extract"]) and not _looks_like_company(art["extract"])


def _resolve_website(name, keywords, allow_acronym=False):
    """Resolve a candidate name to a verified website, or None.
    Order: Wikipedia article's official link, then domain derivation."""
    if _implausible_name(name):
        return None
    if not allow_acronym and " " not in name and name.isupper() and len(name) <= 4:
        return None  # bare acronyms from news text are concepts (MTF, IPO);
        # founder-named acronyms (JBL, AECC) pass allow_acronym=True
    if " " in name and _is_wiki_concept(name):
        return None
    # Exact-title article first: 'Sony' the group (sony.com) must win over
    # 'Sony Pictures', which a relevance search may rank higher.
    titles = [name] + [t for t in _wiki_search_titles(f"{name} company", limit=3) if t != name]
    name_base = re.sub(r"[^a-z0-9]", "", name.lower())
    for t in titles:
        if name.lower().split()[0] in t.lower():
            art = _wiki_article(t)
            if art["website"] and not _is_media_domain(http_util.domain_of(art["website"])):
                ov, _ = _verify_homepage(art["website"], keywords, 3, name=name)
                if ov:
                    # Wikipedia may hand back a *division's* site ('Sony' ->
                    # sonypictures.com). If the exact-name domain verifies
                    # about as well, it is the canonical company site.
                    dom_base = re.sub(r"[^a-z0-9]", "",
                                      http_util.domain_of(art["website"]).split(".")[0])
                    if dom_base != name_base and len(name_base) >= 3:
                        for tld in ("com", "in", "co.in"):
                            cand = f"https://{name_base}.{tld}"
                            if http_util.domain_of(cand) == http_util.domain_of(art["website"]):
                                continue
                            ov2, _ = _verify_homepage(cand, keywords, 3, name=name)
                            if ov2 and ov2 >= ov - 1:
                                return cand, ov2, "exact-name domain preferred over Wikipedia division link: " + t
                    return art["website"], ov, "Wikipedia article: " + t
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    variants = [base]
    for suffix in ("education", "global", "india", "overseas", "online", "group", "company"):
        if base.endswith(suffix) and len(base) > len(suffix) + 3:
            variants.append(base[:-len(suffix)])
    seen = set()
    for v in variants:
        for tld in ("com", "in", "co.in"):
            dom = f"{v}.{tld}"
            if dom in seen:
                continue
            seen.add(dom)
            if _is_media_domain(dom):
                continue
            ov, _ = _verify_homepage("https://" + dom, keywords, 5, name=name,
                                     min_distinctive=2)  # derivation is the
            # weakest provenance (a guessed domain): demand a stronger,
            # more distinctive match than the Wikipedia/hint channels
            if ov:
                return "https://" + dom, ov, "domain derivation + homepage verification"
    return None


def discover_competitors(company, log):
    """Run the multi-signal derivation pipeline. Returns competitor dicts."""
    profile = company.get("profile") or {}
    keywords = set(profile.get("keywords") or [])
    vocab = vocab_for(company)
    self_domain = http_util.domain_of(company["website"])
    self_name = company["name"].lower()

    candidates = {}  # name(lower) -> {name, evidence:set, mentions, website_hint, signal}

    def add_candidate(name, evidence, signal, website_hint=""):
        name = re.sub(r"\s+", " ", (name or "")).strip(" .&-")
        if not name or len(name) < 3 or len(name) > 34:
            return
        if name.lower() == self_name or name.lower() in NAME_STOPWORDS:
            return
        c = candidates.setdefault(name.lower(), {"name": name, "evidence": set(),
                                                 "mentions": 0, "website_hint": website_hint,
                                                 "signals": set()})
        c["mentions"] += 1
        c["signals"].add(signal)
        if evidence:
            c["evidence"].add(evidence)
        if website_hint and not c["website_hint"]:
            c["website_hint"] = website_hint

    # ---- S1: Wikipedia graph -------------------------------------------
    wiki_titles = _wiki_search_titles(company["name"], limit=3)
    concept_queries = [vocab["category_phrase"], (company.get("industry") or "").split("—")[0]]
    for q in concept_queries:
        wiki_titles += _wiki_search_titles(q, limit=2)
    institution_words = ("University", "College", "Institute", "School", "Ministry",
                         "Polytechnic", "Academy of")
    seen_titles = set()
    for title in wiki_titles[:5]:
        if title in seen_titles:
            continue
        seen_titles.add(title)
        art = _wiki_article(title)
        extract_low = art["extract"].lower()
        topical = sum(1 for k in keywords if k in extract_low)
        if company["name"].lower() not in title.lower() and topical < 3:
            log.append(f"S1 seed article off-topic, skipped: {title}")
            continue
        for link in art["links"]:
            if any(w in link for w in ("List of", "Category:", "Template:", "disambiguation")):
                continue
            if any(w in link for w in institution_words):
                continue  # institutions are customers/partners here, not rivals
            add_candidate(link.replace(" (company)", ""), f"Wikipedia: {title}", "wikipedia")
    log.append(f"S1 Wikipedia graph: {len(candidates)} candidate names so far")

    # ---- S2 + S3: news listicles and corpus mining ----------------------
    queries = [
        f"best {vocab['category_phrase']} India",
        f"{company['name']} competitors alternatives",
        f"top {vocab['category_phrase']} comparison",
        f'"{company["name"]}"',
        vocab["market_queries"][0] if vocab["market_queries"] else vocab["category_phrase"],
    ]
    article_urls, seen_art = [], set()
    corpus = []
    for q in queries:
        items = _rss_items(news_index_url(q), limit=10)
        for item in items:
            corpus.append(item["title"] + " " + item["desc"])
            link = resolve_news_link(item["link"])
            if link and link not in seen_art:
                seen_art.add(link)
                article_urls.append(link)
        for item in _gnews_items(q, limit=12):
            corpus.append(item["title"] + " " + item["desc"])
    for text in corpus:
        for phrase in _name_phrases(text):
            add_candidate(phrase, "", "news-corpus")
    log.append(f"S3 news corpus mining (Bing + Google News text): {len(candidates)} candidate names so far")

    # Two passes: a domain linked from *many* articles is publisher
    # furniture (footers/sister-site links — The Hindu's page furniture
    # produced 'Frontline', 'Young World Club'…), while a real listicle
    # names each competitor in one or two articles.
    from collections import Counter as _Counter
    fetched_pages = []
    domain_articles = _Counter()
    for url in article_urls[:6]:
        if not http_util.robots_allowed(url):
            continue
        r = http_util.fetch(url)
        if not r["ok"]:
            continue
        soup = BeautifulSoup(r["text"], "html.parser")
        page_links = []
        seen_dom = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            dom = http_util.domain_of(href)
            if not dom or dom == self_domain or _is_media_domain(dom) or dom.endswith("google.com"):
                continue
            page_links.append((_candidate_name(a.get_text(), dom), dom))
            if dom not in seen_dom:
                seen_dom.add(dom)
                domain_articles[dom] += 1
        fetched_pages.append((r["final_url"], soup, page_links))
    for final_url, soup, page_links in fetched_pages:
        for h in soup.find_all(["h2", "h3"]):
            txt = re.sub(r"\s+", " ", h.get_text()).strip()
            txt = re.sub(r"^[\d\.\s\)\-–]+", "", txt)
            if 3 <= len(txt) <= 34 and not any(w in txt.lower() for w in
                                               ("how", "why", "what", "best", "top", "conclusion", "faq")):
                add_candidate(txt, final_url, "listicle-heading")
        for nm, dom in page_links:
            if domain_articles[dom] >= 3:
                continue  # publisher furniture, not a listicle entry
            add_candidate(nm, final_url, "listicle-link", website_hint="https://" + dom)
    log.append(f"S2 listicle mining: {len(candidates)} candidate names total")

    # ---- Resolution + verification --------------------------------------
    def try_verify(c):
        if _implausible_name(c["name"]):
            return None
        if " " in c["name"] and _is_wiki_concept(c["name"]):
            return None
        if _wiki_says_not_company(c["name"]):
            return None  # Wikipedia defines it as a thing, not a firm
        if any(w in c["name"] for w in ("University", "College", "Institute", "Ministry")):
            return None
        if any(w in c["name"] for w in MEDIA_OR_GENERIC):
            return None  # a publisher or language/region word, not a rival company
        words = c["name"].split()
        if len(words) == 1 and (len(words[0]) < 5 or c["mentions"] < 2):
            return None  # one-word corpus fragments are noise unless recurrent
        hint = c.get("website_hint")
        if hint and len([s for s in urlparse(hint).path.split("/") if s]) >= 2:
            hint = None  # a deep article URL is evidence, not a homepage;
            # resolve the name properly instead of adopting the article
        if hint:
            dom = http_util.domain_of(hint)
            if dom != self_domain and not _is_media_domain(dom):
                # A listicle *content* link's anchor describes its topic, not
                # the company ('Trading Strategies' -> dhan.co). For
                # multi-word names, the brand token must be in the domain.
                words = c["name"].split()
                if len(words) > 1:
                    token = re.sub(r"[^a-z0-9]", "", words[0].lower())
                    dom_base = re.sub(r"[^a-z0-9]", "", dom.split(".")[0])
                    # brand tokens are domain prefixes ('kotak'->kotakneo);
                    # a mere substring ('trading' in chicagotrading) is a
                    # topic word, not the brand
                    if token and not dom_base.startswith(token):
                        pass  # fall through to name-only resolution
                    else:
                        ov, title = _verify_homepage(hint, keywords, 3, name=c["name"])
                        if ov:
                            return hint, ov, title, "listicle link + homepage verification"
                else:
                    ov, title = _verify_homepage(hint, keywords, 3, name=c["name"])
                    if ov:
                        return hint, ov, title, "listicle link + homepage verification"
        res = _resolve_website(c["name"], keywords)
        if res:
            url, ov, how = res
            if http_util.domain_of(url) == self_domain or _is_media_domain(http_util.domain_of(url)):
                return None
            _, title = _verify_homepage(url, keywords, 3, name=c["name"])
            return url, ov, title, how
        return None

    import time as _time
    deadline = _time.time() + 150  # keep setup interactive; misses are logged
    verified = []
    ranked = sorted(candidates.values(),
                    key=lambda c: (-bool(c.get("website_hint")), -len(c["signals"]), -c["mentions"]))
    attempts = 0
    for c in ranked:
        if len(verified) >= 10 or attempts >= 30 or _time.time() > deadline:
            break
        # Gate for Wikipedia-only names: the linked article itself must
        # actually be about a company (concept articles like
        # 'Technical analysis' or 'Vehicle subscription' link out to news
        # stories that otherwise masquerade as a candidate's website).
        if c["signals"] == {"wikipedia"} and not c.get("website_hint"):
            art = _wiki_article(c["name"])
            if art["extract"] and not _looks_like_company(art["extract"]):
                continue
            if art["website"]:
                c["website_hint"] = art["website"]
        attempts += 1
        out = try_verify(c)
        if not out:
            log.append(f"  candidate not verified, discarded: {c['name']} "
                       f"(signals: {', '.join(sorted(c['signals']))}, mentions: {c['mentions']})")
            continue
        url, ov, title, how = out
        if any(http_util.domain_of(v["website"]) == http_util.domain_of(url) for v in verified):
            continue  # same company under another name (e.g. a product name)
        verified.append({
            "name": c["name"], "website": url,
            "why_relevant": (f"Derived from {', '.join(sorted(c['signals']))} signal(s) and verified live: "
                             f"its own homepage shares {ov} of {company['name']}'s researched industry "
                             f"keywords, i.e. it sells to the same customers in the same category."),
            "derivation_evidence": ("; ".join(sorted(c["evidence"])[:3]) or how),
            "profile_summary": title[:160],
            "overlap": ov,
        })
        log.append(f"  competitor verified: {c['name']} -> {url} (overlap {ov}, via {how})")

    # ---- S4: one expansion round over verified competitors --------------
    if len(verified) < 10:
        extra_names = []
        for v in verified[:4]:
            items = _rss_items(news_index_url(f'"{v["name"]}" {vocab["category_phrase"]}'), limit=8)
            for item in items:
                for phrase in _name_phrases(item["title"] + " " + item["desc"]):
                    extra_names.append(phrase)
        from collections import Counter
        for nm, freq in Counter(extra_names).most_common(14):
            if len(verified) >= 10:
                break
            if nm.lower() in candidates or nm.lower() == self_name or freq < 2 \
                    or _implausible_name(nm):
                continue
            c = {"name": nm, "evidence": set(), "mentions": freq,
                 "website_hint": "", "signals": {"co-mention-expansion"}}
            out = try_verify(c)
            if out:
                url, ov, title, how = out
                if any(http_util.domain_of(v["website"]) == http_util.domain_of(url) for v in verified):
                    continue
                verified.append({
                    "name": nm, "website": url,
                    "why_relevant": (f"Surfaced by co-mention expansion: named alongside verified competitors "
                                     f"in {freq} category news items, then verified live (homepage keyword "
                                     f"overlap {ov} with {company['name']}'s profile)."),
                    "derivation_evidence": how,
                    "profile_summary": title[:160], "overlap": ov,
                })
                log.append(f"  competitor verified (expansion): {nm} -> {url} (overlap {ov})")
    verified.sort(key=lambda c: -c["overlap"])
    log.append(f"Discovery complete: {len(verified)} verified competitors")
    return verified[:10]


def sources_for_competitor(company_name, c):
    """The two standard sources watching one competitor (used both at stack
    build time and when a competitor is absorbed later, e.g. from the
    founder interview)."""
    return [
        {
            "category": "Competitors", "name": f"{c['name']} — official website",
            "url": c["website"], "source_type": "web", "query": "",
            "competitor_id": c.get("id"),
            "reason": f"{c['name']}'s own site is where launches, pricing and positioning changes appear first.",
            "justification_specific": f"Specific: the official domain of a verified direct competitor of {company_name}.",
            "justification_recent": "Recent: product/pricing pages change exactly when a move is made; the crawler hashes content to catch changes.",
            "justification_credible": "Credible: first-party source — claims are the competitor's own, labelled as such.",
            "reliability": 0.85,
        },
        {
            "category": "Competitors", "name": f"News index: \"{c['name']}\"",
            "url": gnews_url(f'"{c["name"]}"'), "source_type": "rss",
            "query": f'"{c["name"]}"', "competitor_id": c.get("id"),
            "reason": f"News coverage of {c['name']}: launches, pricing, partnerships, hiring and expansion that {company_name} must react to.",
            "justification_specific": f"Specific: news index restricted to the exact phrase \"{c['name']}\".",
            "justification_recent": "Recent: the index is continuously updated; items are dated and filtered to the last 120 days.",
            "justification_credible": "Credible: aggregates established publishers; every record keeps its publisher link for verification.",
            "reliability": 0.7,
        },
    ]


def build_sources(company, competitors, vocab):
    """Assemble the Signal Stack for one company. Returns list of source dicts."""
    name = company["name"]
    sources = []

    def rss_source(category, q, reason, specific, recent, credible, reliability=0.7, competitor_id=None):
        sources.append({
            "category": category, "name": f"News index: {q}", "url": gnews_url(q),
            "source_type": "rss", "query": q, "competitor_id": competitor_id,
            "reason": reason, "justification_specific": specific,
            "justification_recent": recent, "justification_credible": credible,
            "reliability": reliability,
        })

    # --- Competitors: official site (change watch) + dedicated news index per competitor
    for c in competitors:
        sources.extend(sources_for_competitor(name, c))

    # --- Market: industry-level developments
    for q in vocab["market_queries"]:
        rss_source("Market", q,
                   f"Market/regulatory developments that change demand, rules or costs for {name}: {q}.",
                   f"Specific: query scoped to '{q}' rather than general news.",
                   "Recent: continuously updated index; dated items only.",
                   "Credible: established news publishers; policy items are cross-checkable against the regulator's site.",
                   reliability=0.7)
    rss_source("Market", f'"{name}"',
               f"Direct coverage of {name} itself — partnerships, funding, leadership and press mentions.",
               f"Specific: exact-phrase index on the company name '{name}'.",
               "Recent: continuously updated index; dated items only.",
               "Credible: established publishers; records link to the original article.",
               reliability=0.7)

    # --- Customers: the customer's own language
    rss_source("Customers", f'"{name}" reviews complaints',
               f"Reviews and complaints about {name} in customers' own words — recurring problems and unmet needs.",
               f"Specific: query combines the company name with review/complaint language.",
               "Recent: continuously updated; dated items only.",
               "Credible: customer voice is reported speech — treated as sentiment evidence, not fact, and labelled so.",
               reliability=0.55)
    for q in vocab["customer_queries"]:
        rss_source("Customers", q,
                   f"Category-level customer problems {name}'s buyers face: {q}. Shows unmet needs {name} can win on.",
                   f"Specific: query scoped to the problem space ('{q}'), not to brand mentions.",
                   "Recent: continuously updated index; dated items only.",
                   "Credible: multiple publishers/forums; used for problem patterns, not single anecdotes.",
                   reliability=0.55)

    # --- Internal placeholder (activated by uploads in internal_docs.py)
    sources.append({
        "category": "Internal", "name": f"{name} — internal uploads (CRM / support / call notes)",
        "url": f"internal://{name.lower().replace(' ', '-')}", "source_type": "internal",
        "query": "", "competitor_id": None,
        "reason": "First-party internal data: recurring objections, lost-deal reasons, product requests and emerging risks from the company's own files.",
        "justification_specific": "Specific: the company's own CRM exports, support logs and call notes.",
        "justification_recent": "Recent: reflects the current book of business at upload time.",
        "justification_credible": "Credible: first-party operational data, highest reliability in the stack.",
        "reliability": 0.9,
    })
    return sources
