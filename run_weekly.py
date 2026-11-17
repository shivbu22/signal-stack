#!/usr/bin/env python3
"""Weekly Intelligence Brief job (brief §10A).

For every configured company: crawl all approved sources -> analyse new
records -> regenerate and save the Monday Morning Brief. Each company's run
is written to the runs table (success / partial / failed with the full log),
so a failed scheduled run is visible in the dashboard's Run History.

Run manually:   python3 run_weekly.py
Schedule it:    see schedule.json + README (cron line provided).
"""
import sys

from signalstack import brief, crawler, db


def main(only_company=None):
    conn = db.init_db()
    companies = db.rows(conn, "SELECT id, name FROM companies")
    if only_company:
        companies = [c for c in companies if c["id"] == only_company]
    overall_failed = False
    for c in companies:
        run_id = db.start_run(conn, "weekly_brief", c["id"])
        log = [f"Weekly brief run for {c['name']}"]
        try:
            stats = crawler.crawl_company(conn, c["id"], log)
            log.append(f"Crawl stats: {stats}")
            company = db.get_company(conn, c["id"])
            _, path = brief.generate_brief(conn, company)
            log.append(f"Brief regenerated: {path}")
            status = "partial" if stats["errors"] else "success"
            if stats["errors"]:
                overall_failed = True
            db.finish_run(conn, run_id, status, "\n".join(log))
            print(f"[weekly] {c['name']}: {status} — {stats['new_records']} new records, brief at {path}")
        except Exception as e:
            overall_failed = True
            log.append(f"FAILED: {type(e).__name__}: {e}")
            db.finish_run(conn, run_id, "failed", "\n".join(log))
            print(f"[weekly] {c['name']}: FAILED — {e}")
    return 1 if overall_failed else 0


if __name__ == "__main__":
    cid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(cid))
