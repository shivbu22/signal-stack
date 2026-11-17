#!/usr/bin/env python3
"""Signal Stack dashboard — Flask web app with a fully working backend.

Pages: Home · Company Setup · Company Intelligence Profile · AI Interview ·
Signal Stack · Source Manager · Intelligence Feed · Monday Morning Brief ·
Run History & Logs · Audits · Settings.

Run:  python3 app.py            (http://127.0.0.1:5000)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import markdown as md
from flask import Flask, flash, redirect, render_template, request, url_for

from signalstack import (audit, brief, config, crawler, db, discovery, engine,
                         internal_docs, interview, reassess)

app = Flask(__name__)
app.secret_key = "signalstack-demo-key"


def conn():
    return db.init_db()


def md_html(text):
    return md.markdown(text or "", extensions=["tables", "fenced_code"])


@app.template_filter("md")
def _md(text):
    return md_html(text)


@app.context_processor
def inject_globals():
    c = conn()
    companies = db.rows(c, "SELECT id, name FROM companies ORDER BY id")
    return {"all_companies": companies}


# ---------------------------------------------------------------- home
@app.route("/")
def home():
    c = conn()
    companies = []
    for comp in db.rows(c, "SELECT * FROM companies ORDER BY id"):
        cid = comp["id"]
        comp["n_sources"] = db.row(c, "SELECT COUNT(*) n FROM sources WHERE company_id=? AND status='approved'", (cid,))["n"]
        comp["n_records"] = db.row(c, "SELECT COUNT(*) n FROM records WHERE company_id=?", (cid,))["n"]
        comp["n_competitors"] = db.row(c, "SELECT COUNT(*) n FROM competitors WHERE company_id=?", (cid,))["n"]
        comp["latest_brief"] = db.row(c, "SELECT generated_at FROM briefs WHERE company_id=? ORDER BY id DESC LIMIT 1", (cid,))
        companies.append(comp)
    runs = db.rows(c, "SELECT * FROM runs ORDER BY id DESC LIMIT 6")
    totals = {
        "records": db.row(c, "SELECT COUNT(*) n FROM records")["n"],
        "sources": db.row(c, "SELECT COUNT(*) n FROM sources WHERE status='approved'")["n"],
    }
    return render_template("home.html", companies=companies, runs=runs,
                           totals=totals, schedule=config.load_schedule())


# ---------------------------------------------------------------- setup
@app.route("/setup", methods=["GET", "POST"])
def setup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        website = request.form.get("website", "").strip()
        if not name or not website:
            flash("Company name and website are both required.")
            return redirect(url_for("setup"))
        c = conn()
        log = []
        cid = engine.setup_company(c, name, website, log)
        if cid is None:
            flash("Setup failed — see Run History for the log.")
            return redirect(url_for("runs"))
        flash(f"{name} configured: research, competitor discovery, interview and Signal Stack are ready.")
        return redirect(url_for("company_profile", company_id=cid))
    return render_template("setup.html")


# ---------------------------------------------------------------- profile
@app.route("/company/<int:company_id>", methods=["GET", "POST"])
def company_profile(company_id):
    c = conn()
    if request.method == "POST":
        fields = ["industry", "business_model", "product_summary", "revenue_streams",
                  "target_customers", "value_prop", "context_notes", "growth_focus"]
        vals = [request.form.get(f, "") for f in fields]
        c.execute(f"UPDATE companies SET {', '.join(f + '=?' for f in fields)} WHERE id=?",
                  (*vals, company_id))
        c.commit()
        flash("Profile saved. If the business context changed materially, run a reassessment from the Signal Stack page.")
        return redirect(url_for("company_profile", company_id=company_id))
    company = db.get_company(c, company_id)
    competitors = db.rows(c, "SELECT * FROM competitors WHERE company_id=?", (company_id,))
    answers = db.rows(c, "SELECT topic, question, answer, skipped FROM interview_questions WHERE company_id=? AND is_followup=0 ORDER BY position", (company_id,))
    return render_template("company.html", company=company, competitors=competitors, answers=answers)


# ---------------------------------------------------------------- interview
@app.route("/company/<int:company_id>/interview", methods=["GET", "POST"])
def company_interview(company_id):
    c = conn()
    if request.method == "POST":
        qid = int(request.form["question_id"])
        q = db.row(c, "SELECT * FROM interview_questions WHERE id=?", (qid,))
        if "skip" in request.form:
            c.execute("UPDATE interview_questions SET skipped=1, answer='' WHERE id=?", (qid,))
            c.commit()
            flash("Question skipped (confidential). You can answer it later.")
        else:
            answer = request.form.get("answer", "").strip()
            c.execute("UPDATE interview_questions SET answer=?, skipped=0, seed_answer=0 WHERE id=?",
                      (answer, qid))
            c.commit()
            if answer and not q["is_followup"]:
                fu = interview.followup_for(q, answer)
                if fu and not db.row(c, "SELECT id FROM interview_questions WHERE parent_id=?", (qid,)):
                    c.execute(
                        "INSERT INTO interview_questions(company_id, position, topic, question, is_followup, parent_id) VALUES (?,?,?,?,1,?)",
                        (company_id, q["position"], q["topic"] + " (follow-up)", fu, qid))
                    c.commit()
                    flash("Answer saved — a follow-up question was generated from your answer.")
                else:
                    flash("Answer saved.")
            engine.apply_interview_to_profile(c, company_id)
            if q["topic"] == "competitors" and answer:
                log = []
                added = engine.absorb_interview_competitors(c, company_id, log)
                if added:
                    flash(f"Competitor(s) you named were verified live and added to the stack: {', '.join(added)}")
        return redirect(url_for("company_interview", company_id=company_id))
    company = db.get_company(c, company_id)
    questions = db.rows(c, """SELECT * FROM interview_questions WHERE company_id=?
                              ORDER BY position, is_followup, id""", (company_id,))
    current = next((q for q in questions if not q["is_followup"] and not q["answer"] and not q["skipped"]), None)
    return render_template("interview.html", company=company, questions=questions, current=current)


# ---------------------------------------------------------------- stack + sources
@app.route("/company/<int:company_id>/stack")
def company_stack(company_id):
    c = conn()
    company = db.get_company(c, company_id)
    competitors = db.rows(c, "SELECT * FROM competitors WHERE company_id=?", (company_id,))
    sources = db.rows(c, "SELECT * FROM sources WHERE company_id=? ORDER BY category, id", (company_id,))
    by_cat = {}
    for s in sources:
        by_cat.setdefault(s["category"], []).append(s)
    return render_template("stack.html", company=company, competitors=competitors, by_cat=by_cat)


@app.route("/company/<int:company_id>/reassess", methods=["POST"])
def company_reassess(company_id):
    c = conn()
    company = db.get_company(c, company_id)
    run_id = db.start_run(c, "reassessment", company_id)
    log = []
    changes = reassess.reassess_company(c, company, log)
    db.finish_run(c, run_id, "success", "\n".join(changes + ["", "Discovery log:"] + log))
    for ch in changes:
        flash(ch)
    return redirect(url_for("company_stack", company_id=company_id))


@app.route("/sources", methods=["GET", "POST"])
def sources_manager():
    c = conn()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            cid = int(request.form["company_id"])
            url = request.form.get("url", "").strip()
            stype = request.form.get("source_type", "web")
            if stype == "rss" and not url.startswith("http"):
                url = discovery.gnews_url(url)
            c.execute(
                """INSERT INTO sources(company_id, category, name, url, source_type, query,
                     justification_specific, justification_recent, justification_credible, reason,
                     status, reliability, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,'approved',?,?)""",
                (cid, request.form.get("category", "Market"), request.form.get("name", "").strip(),
                 url, stype, request.form.get("name", "") if stype == "rss" else "",
                 "Specific: added manually by the operator for this company.",
                 "Recent: checked on every crawl; dated items only.",
                 "Credible: operator-approved source; records keep original links.",
                 request.form.get("reason", ""), 0.65, db.now_iso()))
            c.commit()
            flash("Source added and approved.")
        elif action in ("remove", "approve", "stale"):
            sid = int(request.form["source_id"])
            new_status = {"remove": "removed", "approve": "approved", "stale": "stale"}[action]
            c.execute("UPDATE sources SET status=? WHERE id=?", (new_status, sid))
            c.commit()
            flash(f"Source {new_status}.")
        elif action == "crawl":
            cid = int(request.form["company_id"])
            run_id = db.start_run(c, "crawl", cid)
            log = []
            stats = crawler.crawl_company(c, cid, log)
            db.finish_run(c, run_id, "partial" if stats["errors"] else "success", "\n".join(log))
            flash(f"Crawl complete: {stats['new_records']} new records, {stats['errors']} source errors (see Run History).")
        return redirect(url_for("sources_manager", company_id=request.args.get("company_id", "")))
    cid = request.args.get("company_id", type=int)
    sql = "SELECT s.*, co.name AS company_name FROM sources s JOIN companies co ON co.id=s.company_id"
    params = ()
    if cid:
        sql += " WHERE s.company_id=?"
        params = (cid,)
    sources = db.rows(c, sql + " ORDER BY co.name, s.category, s.id", params)
    return render_template("sources.html", sources=sources, filter_company=cid)


# ---------------------------------------------------------------- feed
@app.route("/feed")
def feed():
    c = conn()
    f = {k: request.args.get(k, "") for k in
         ("company_id", "category", "competitor", "min_impact", "verified", "from_date")}
    sql = "SELECT r.*, co.name AS company_name FROM records r JOIN companies co ON co.id=r.company_id WHERE 1=1"
    params = []
    if f["company_id"]:
        sql += " AND r.company_id=?"; params.append(int(f["company_id"]))
    if f["category"]:
        sql += " AND r.category=?"; params.append(f["category"])
    if f["competitor"]:
        sql += " AND r.competitor_name LIKE ?"; params.append("%" + f["competitor"] + "%")
    if f["min_impact"]:
        sql += " AND r.impact>=?"; params.append(float(f["min_impact"]))
    if f["verified"]:
        sql += " AND r.verified_status LIKE ?"; params.append(f["verified"] + "%")
    if f["from_date"]:
        sql += " AND r.published_at>=?"; params.append(f["from_date"])
    records = db.rows(c, sql + " ORDER BY r.discovered_at DESC, r.composite_score DESC LIMIT 200", params)
    competitors = [r["name"] for r in db.rows(c, "SELECT DISTINCT name FROM competitors ORDER BY name")]
    return render_template("feed.html", records=records, f=f, competitors=competitors)


# ---------------------------------------------------------------- brief
@app.route("/company/<int:company_id>/brief", methods=["GET", "POST"])
def company_brief(company_id):
    c = conn()
    company = db.get_company(c, company_id)
    if request.method == "POST":
        if "crawl_first" in request.form:
            run_id = db.start_run(c, "crawl", company_id)
            log = []
            stats = crawler.crawl_company(c, company_id, log)
            db.finish_run(c, run_id, "partial" if stats["errors"] else "success", "\n".join(log))
            flash(f"Crawl complete: {stats['new_records']} new records.")
        brief.generate_brief(c, db.get_company(c, company_id))
        flash("Monday Morning Brief regenerated from the current intelligence feed.")
        return redirect(url_for("company_brief", company_id=company_id))
    latest = db.row(c, "SELECT * FROM briefs WHERE company_id=? ORDER BY id DESC LIMIT 1", (company_id,))
    history = db.rows(c, "SELECT id, generated_at, period_label FROM briefs WHERE company_id=? ORDER BY id DESC", (company_id,))
    return render_template("brief.html", company=company, latest=latest, history=history)


# ---------------------------------------------------------------- internal
@app.route("/company/<int:company_id>/internal", methods=["GET", "POST"])
def company_internal(company_id):
    c = conn()
    company = db.get_company(c, company_id)
    if request.method == "POST":
        file = request.files.get("file")
        if file and file.filename:
            src = db.row(c, "SELECT * FROM sources WHERE company_id=? AND source_type='internal'", (company_id,))
            run_id = db.start_run(c, "internal_import", company_id)
            added, log = internal_docs.import_internal_file(c, company, src, file.filename, file.read())
            db.finish_run(c, run_id, "success", "\n".join(log))
            flash(f"Imported {file.filename}: {added} pattern records created.")
        return redirect(url_for("company_internal", company_id=company_id))
    records = db.rows(c, "SELECT * FROM records WHERE company_id=? AND category='Internal' ORDER BY composite_score DESC", (company_id,))
    return render_template("internal.html", company=company, records=records)


# ---------------------------------------------------------------- runs / audits / settings
@app.route("/runs")
def runs():
    c = conn()
    all_runs = db.rows(c, "SELECT r.*, co.name AS company_name FROM runs r LEFT JOIN companies co ON co.id=r.company_id ORDER BY r.id DESC LIMIT 40")
    return render_template("runs.html", runs=all_runs)


@app.route("/audits", methods=["GET", "POST"])
def audits():
    c = conn()
    if request.method == "POST":
        run_id = db.start_run(c, "monthly_audit")
        _, path, _summary = audit.run_audit(c)
        db.finish_run(c, run_id, "success", f"Audit report: {path}")
        flash("Monthly audit complete.")
        return redirect(url_for("audits"))
    latest = db.row(c, "SELECT * FROM audits ORDER BY id DESC LIMIT 1")
    history = db.rows(c, "SELECT id, generated_at, file_path FROM audits ORDER BY id DESC")
    return render_template("audits.html", latest=latest, history=history)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        sched = config.load_schedule()
        sched["weekly_brief"]["day"] = request.form.get("weekly_day", "monday")
        sched["weekly_brief"]["time"] = request.form.get("weekly_time", "07:00")
        sched["monthly_audit"]["day_of_month"] = int(request.form.get("audit_day", 1))
        sched["monthly_audit"]["time"] = request.form.get("audit_time", "08:00")
        sched["weekly_brief"]["cron"] = f"{sched['weekly_brief']['time'].split(':')[1]} {sched['weekly_brief']['time'].split(':')[0]} * * 1"
        sched["monthly_audit"]["cron"] = f"{sched['monthly_audit']['time'].split(':')[1]} {sched['monthly_audit']['time'].split(':')[0]} {sched['monthly_audit']['day_of_month']} * *"
        config.save_schedule(sched)
        flash("Schedule saved to schedule.json. Apply the cron lines from the README to activate on a server.")
        return redirect(url_for("settings"))
    c = conn()
    last_runs = db.rows(c, """SELECT kind, status, started_at FROM runs
                              WHERE kind IN ('weekly_brief','monthly_audit')
                              ORDER BY id DESC LIMIT 8""")
    return render_template("settings.html", schedule=config.load_schedule(), last_runs=last_runs)


if __name__ == "__main__":
    db.init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
