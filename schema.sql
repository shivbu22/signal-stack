-- Signal Stack — SQLite schema
-- Storage for companies, derived competitors, adaptive interviews, the Signal
-- Stack (sources), collected intelligence records, generated briefs, scheduled
-- run history and monthly audits. Plain SQLite, no extensions required.

CREATE TABLE IF NOT EXISTS companies (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    website           TEXT NOT NULL,
    industry          TEXT DEFAULT '',
    archetype         TEXT DEFAULT '',          -- platform / saas / fintech / d2c / services / edtech ...
    business_model    TEXT DEFAULT '',
    product_summary   TEXT DEFAULT '',
    revenue_streams   TEXT DEFAULT '',          -- newline separated
    target_customers  TEXT DEFAULT '',
    value_prop        TEXT DEFAULT '',
    context_notes     TEXT DEFAULT '',          -- free-text business context; edits trigger reassessment
    growth_focus      TEXT DEFAULT '',          -- current growth focus; edits trigger reassessment
    profile_json      TEXT DEFAULT '{}',        -- raw research extraction (headings, keywords, meta)
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(id),
    name                TEXT NOT NULL,
    website             TEXT DEFAULT '',
    why_relevant        TEXT DEFAULT '',
    derivation_evidence TEXT DEFAULT '',        -- pages/queries that surfaced this competitor
    profile_summary     TEXT DEFAULT '',        -- extracted from the competitor's own homepage
    discovered_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interview_questions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL REFERENCES companies(id),
    position    INTEGER NOT NULL,
    topic       TEXT NOT NULL,                  -- one of the 10 mandated topics
    question    TEXT NOT NULL,
    answer      TEXT DEFAULT '',
    skipped     INTEGER DEFAULT 0,
    is_followup INTEGER DEFAULT 0,
    parent_id   INTEGER,
    seed_answer INTEGER DEFAULT 0               -- 1 = demo seed answer (editable), 0 = entered in UI
);

CREATE TABLE IF NOT EXISTS sources (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id             INTEGER NOT NULL REFERENCES companies(id),
    category               TEXT NOT NULL,       -- Customers / Competitors / Market / Internal
    name                   TEXT NOT NULL,
    url                    TEXT NOT NULL,
    source_type            TEXT NOT NULL,       -- rss / web / internal
    competitor_id          INTEGER REFERENCES competitors(id),
    query                  TEXT DEFAULT '',     -- for rss sources built from a search query
    justification_specific TEXT DEFAULT '',
    justification_recent   TEXT DEFAULT '',
    justification_credible TEXT DEFAULT '',
    reason                 TEXT DEFAULT '',     -- plain-language reason for inclusion
    status                 TEXT DEFAULT 'approved',  -- approved / pending / removed / stale
    reliability            REAL DEFAULT 0.6,    -- 0..1 source reliability measure
    last_checked_at        TEXT,
    last_status            TEXT DEFAULT 'never',     -- ok / error / empty / blocked
    last_hash              TEXT DEFAULT '',
    fail_count             INTEGER DEFAULT 0,
    records_total          INTEGER DEFAULT 0,
    created_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL REFERENCES companies(id),
    source_id           INTEGER NOT NULL REFERENCES sources(id),
    category            TEXT NOT NULL,
    competitor_name     TEXT DEFAULT '',
    title               TEXT NOT NULL,
    url                 TEXT NOT NULL,
    published_at        TEXT DEFAULT '',
    discovered_at       TEXT NOT NULL,
    evidence_snippet    TEXT DEFAULT '',        -- verbatim evidence from the source (kept separate)
    content_hash        TEXT NOT NULL,
    signal_type         TEXT DEFAULT 'other',   -- launch/pricing/partnership/hiring/expansion/funding/policy/complaint/demand/technology/other
    stance              TEXT DEFAULT 'neutral', -- opportunity / threat / neutral
    business_area       TEXT DEFAULT '',
    why_it_matters      TEXT DEFAULT '',        -- interpretation (kept separate from evidence)
    recommended_action  TEXT DEFAULT '',
    urgency             REAL DEFAULT 0.5,       -- 0..1
    impact              REAL DEFAULT 0.5,       -- 0..1
    relevance           REAL DEFAULT 0.5,       -- 0..1
    source_reliability  REAL DEFAULT 0.5,       -- 0..1 (copied from source, adjustable)
    evidence_strength   REAL DEFAULT 0.5,       -- 0..1
    strategic_relevance REAL DEFAULT 0.5,       -- 0..1 (boosted by interview priorities)
    novelty             REAL DEFAULT 0.5,       -- 0..1
    composite_score     REAL DEFAULT 0.0,       -- weighted ranking score
    verified_status     TEXT DEFAULT 'single-source',  -- verified / single-source / unverified
    UNIQUE(company_id, content_hash)
);

CREATE TABLE IF NOT EXISTS briefs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   INTEGER NOT NULL REFERENCES companies(id),
    generated_at TEXT NOT NULL,
    period_label TEXT DEFAULT '',
    content_md   TEXT NOT NULL,
    file_path    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,        -- setup_research / crawl / weekly_brief / monthly_audit / reassessment / internal_import
    company_id  INTEGER,
    started_at  TEXT NOT NULL,
    finished_at TEXT DEFAULT '',
    status      TEXT DEFAULT 'running',  -- success / failed / partial
    log         TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS audits (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   INTEGER,
    generated_at TEXT NOT NULL,
    summary_json TEXT DEFAULT '{}',
    report_md    TEXT NOT NULL,
    file_path    TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
