#!/usr/bin/env python3
"""Monthly Signal Stack Audit job (brief §10B).

Checks dead URLs, duplicate/inactive sources, declining relevance and
newly discovered sources; writes a source-health report with add/remove
recommendations and logs the run (failures included) to the runs table.

Run manually:   python3 run_monthly_audit.py
Schedule it:    see schedule.json + README (cron line provided).
"""
import sys

from signalstack import audit, db


def main():
    conn = db.init_db()
    run_id = db.start_run(conn, "monthly_audit")
    try:
        _, path, summary = audit.run_audit(conn)
        db.finish_run(conn, run_id, "success", f"Audit report: {path}\nSummary: {summary}")
        print(f"[audit] success — report at {path}")
        return 0
    except Exception as e:
        db.finish_run(conn, run_id, "failed", f"FAILED: {type(e).__name__}: {e}")
        print(f"[audit] FAILED — {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
