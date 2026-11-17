"""Configuration: paths, schedule, crawl politeness limits."""
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(DATA_DIR, "signalstack.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
SCHEDULE_PATH = os.path.join(BASE_DIR, "schedule.json")

USER_AGENT = "SignalStack/1.0 (EDXSO assignment; public-source research; contact: student project)"
REQUEST_TIMEOUT = 20          # seconds
SAME_HOST_DELAY = 1.0         # seconds between requests to the same host
MAX_ITEMS_PER_SOURCE = 4      # cap per crawl per source — quality over volume
MAX_RECORD_AGE_DAYS = 120     # ignore RSS items older than this

DEFAULT_SCHEDULE = {
    "weekly_brief": {"day": "monday", "time": "07:00",
                     "description": "Crawl all approved sources, analyse new records, regenerate every company's Monday Morning Brief."},
    "monthly_audit": {"day_of_month": 1, "time": "08:00",
                      "description": "Source-health audit: dead URLs, duplicates, inactive sources, newly discovered sources, add/remove recommendations."},
}


def load_schedule():
    if os.path.exists(SCHEDULE_PATH):
        try:
            with open(SCHEDULE_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_SCHEDULE)


def save_schedule(sched):
    with open(SCHEDULE_PATH, "w") as f:
        json.dump(sched, f, indent=2)
