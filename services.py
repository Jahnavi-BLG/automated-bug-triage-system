"""Business logic: create/triage issues, workflow, notifications, SLA, stats."""
import json, time
from datetime import datetime, timedelta, timezone
import triage

ALLOWED = {  # status workflow
    "New": ["Assigned", "In Progress"], "Assigned": ["In Progress", "Resolved"],
    "In Progress": ["Resolved", "Assigned"], "Resolved": ["Closed", "In Progress"],
    "Closed": ["In Progress"], "Duplicate": ["New", "Closed"]}
OPEN_STATES = ("New", "Assigned", "In Progress")


class ValidationError(Exception): pass
class Forbidden(Exception): pass
class NotFound(Exception): pass


def now(): return datetime.now(timezone.utc).replace(microsecond=0)
def iso(dt): return dt.isoformat()


def log(db, issue_id, user_id, action, detail=""):
    db.execute("INSERT INTO history(issue_id,user_id,action,detail,created_at) VALUES(?,?,?,?,?)",
               (issue_id, user_id, action, detail, iso(now())))


def notify(db, user_id, issue_id, message, channel="in-app"):
    if user_id is None: return
    db.execute("INSERT INTO notifications(user_id,issue_id,message,channel,created_at) VALUES(?,?,?,?,?)",
               (user_id, issue_id, message, channel, iso(now())))
    print(f"[NOTIFY:{channel}] user={user_id} issue={issue_id} -> {message}")  # stub for real Email/Slack


def developers_with_load(db):
    rows = db.execute("""SELECT u.id,u.name,u.skills,
        (SELECT COUNT(*) FROM issues i WHERE i.assignee_id=u.id AND i.status IN ('Assigned','In Progress')) AS load
        FROM users u WHERE u.role='developer'""").fetchall()
    return [dict(r) for r in rows]


def _issue_select(where="", args=()):
    return f"""SELECT i.*, r.name AS reporter_name, a.name AS assignee_name FROM issues i
        JOIN users r ON r.id=i.reporter_id LEFT JOIN users a ON a.id=i.assignee_id {where}"""


def serialize(row):
    d = dict(row)
    d["sla_breached"] = bool(d["status"] in OPEN_STATES and d["sla_due"] and d["sla_due"] < iso(now()))
    return d


def get_issue(db, issue_id):
    row = db.execute(_issue_select("WHERE i.id=?"), (issue_id,)).fetchone()
    if not row: raise NotFound("Issue not found")
    return serialize(row)


def list_issues(db, status=None, severity=None, component=None, q=None):
    where, args = [], []
    for col, val in (("status", status), ("severity", severity), ("component", component)):
        if val: where.append(f"i.{col}=?"); args.append(val)
    if q: where.append("(i.title LIKE ? OR i.description LIKE ?)"); args += [f"%{q}%"] * 2
    sql = _issue_select(("WHERE " + " AND ".join(where)) if where else "") + " ORDER BY i.id DESC"
    return [serialize(r) for r in db.execute(sql, args).fetchall()]


def create_issue(db, clf, reporter_id, title, description):
    title, description = (title or "").strip(), (description or "").strip()
    if len(title) < 5 or len(description) < 20:
        raise ValidationError("Please provide a clear title (min 5 characters) and a description of at least "
                              "20 characters: steps to reproduce, expected vs actual behaviour.")
    t0 = time.perf_counter()
    text = f"{title}. {description}"
    pred = clf.predict(text)                                                    # classify
    open_rows = db.execute("SELECT id,title,description FROM issues WHERE status NOT IN ('Closed','Duplicate')").fetchall()
    dups = triage.find_duplicates(text, [{"id": r["id"], "text": f"{r['title']}. {r['description']}"} for r in open_rows])
    ranking, assignee, status, dup_of, dup_score = [], None, "New", None, None
    if dups:
        status, dup_of, dup_score = "Duplicate", dups[0]["id"], dups[0]["score"]
    else:
        ranking = triage.rank_developers(pred["component"], developers_with_load(db))
        if ranking: assignee, status = ranking[0]["id"], "Assigned"
    ms = int((time.perf_counter() - t0) * 1000)
    ts = now()
    cur = db.execute("""INSERT INTO issues(title,description,reporter_id,assignee_id,status,type,severity,priority,component,
        confidence,duplicate_of,duplicate_score,triage_ms,sla_due,created_at,updated_at,predicted_type,predicted_severity,predicted_component)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (title, description, reporter_id, assignee, status, pred["type"], pred["severity"], pred["priority"], pred["component"],
         round(sum(pred["confidence"].values()) / 3, 2), dup_of, dup_score, ms,
         iso(ts + timedelta(hours=triage.SLA_HOURS[pred["severity"]])), iso(ts), iso(ts),
         pred["type"], pred["severity"], pred["component"]))
    iid = cur.lastrowid
    log(db, iid, reporter_id, "created", "Issue reported")
    log(db, iid, None, "auto-triage", json.dumps({k: pred[k] for k in ("type", "severity", "priority", "component")}))
    if dup_of:
        log(db, iid, None, "duplicate", f"Linked to #{dup_of} (similarity {dup_score})")
        notify(db, reporter_id, iid, f"Your report #{iid} looks like a duplicate of #{dup_of} and was linked to it.")
    else:
        name = next((r["name"] for r in ranking if r["id"] == assignee), None)
        if assignee:
            log(db, iid, None, "assigned", f"Auto-assigned to {name}")
            notify(db, assignee, iid, f"New {pred['severity']} issue #{iid} assigned to you: {title}", "email")
        notify(db, reporter_id, iid, f"Report #{iid} received: {pred['severity']} {pred['type']} ({pred['component']})"
               + (f", assigned to {name}." if name else "."))
        if pred["severity"] == "Critical":
            for l in db.execute("SELECT id FROM users WHERE role='lead'"):
                notify(db, l["id"], iid, f"CRITICAL issue #{iid} reported: {title}", "slack")
    db.commit()
    return {"issue": get_issue(db, iid), "triage": {"prediction": pred, "duplicates": dups, "ranking": ranking[:3], "triage_ms": ms}}


def update_issue(db, user, issue_id, changes):
    issue = get_issue(db, issue_id)
    is_lead = user["role"] == "lead"
    sets, events = {}, []
    # --- status workflow
    new_status = changes.get("status")
    if new_status and new_status != issue["status"]:
        if new_status not in ALLOWED.get(issue["status"], []):
            raise ValidationError(f"Cannot move from {issue['status']} to {new_status}.")
        verifier = user["id"] == issue["reporter_id"] and issue["status"] == "Resolved"
        if not (is_lead or user["id"] == issue["assignee_id"] or verifier):
            raise Forbidden("Only the assignee, the reporter (to verify) or a triage lead can change status.")
        sets["status"] = new_status
        if new_status == "Resolved": sets["resolved_at"] = iso(now())
        events.append(("status", f"{issue['status']} -> {new_status}"))
    # --- lead-only overrides (also recorded as feedback for the ML model)
    overrides = {k: changes[k] for k in ("type", "severity", "component", "priority", "assignee_id") if k in changes and changes[k] not in (None, "", issue[k])}
    if overrides and not is_lead:
        raise Forbidden("Only a triage lead can override triage results or reassign issues.")
    for k, v in overrides.items():
        if k == "severity" and v not in triage.SEV_ORDER: raise ValidationError("Invalid severity")
        if k == "assignee_id":
            v = int(v)
            dev = db.execute("SELECT name FROM users WHERE id=? AND role='developer'", (v,)).fetchone()
            if not dev: raise ValidationError("Assignee must be a developer")
            events.append(("reassigned", f"Assigned to {dev['name']}"))
            notify(db, v, issue_id, f"Issue #{issue_id} was assigned to you by a triage lead.", "email")
            if issue["status"] in ("New", "Duplicate"): sets["status"] = "Assigned"
        else:
            events.append(("override", f"{k}: {issue[k]} -> {v}"))
            if k in ("type", "severity", "component"):
                db.execute("INSERT INTO feedback(issue_id,field,predicted,corrected,created_at) VALUES(?,?,?,?,?)",
                           (issue_id, k, issue[k], v, iso(now())))
        sets[k] = v
    if "severity" in sets:
        comp = sets.get("component", issue["component"])
        sets["priority"] = sets.get("priority") or triage.priority_from(sets["severity"], comp)
        sets["sla_due"] = iso(now() + timedelta(hours=triage.SLA_HOURS[sets["severity"]]))
    if not sets: return issue
    sets["updated_at"] = iso(now())
    db.execute(f"UPDATE issues SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), issue_id))
    for a, d in events: log(db, issue_id, user["id"], a, d)
    if "status" in sets and sets["status"] in ("Resolved", "Closed"):
        notify(db, issue["reporter_id"], issue_id, f"Issue #{issue_id} is now {sets['status']}.")
    db.commit()
    return get_issue(db, issue_id)


def add_comment(db, user, issue_id, text):
    get_issue(db, issue_id)
    if not (text or "").strip(): raise ValidationError("Comment cannot be empty")
    db.execute("INSERT INTO comments(issue_id,user_id,text,created_at) VALUES(?,?,?,?)", (issue_id, user["id"], text.strip(), iso(now())))
    log(db, issue_id, user["id"], "comment", text.strip()[:80]); db.commit()


def check_sla(db):
    """Escalate open issues past their SLA to the triage leads (once)."""
    for i in list_issues(db):
        if i["sla_breached"] and not i["escalated"]:
            for l in db.execute("SELECT id FROM users WHERE role='lead'"):
                notify(db, l["id"], i["id"], f"SLA BREACH: {i['severity']} issue #{i['id']} is overdue and still {i['status']}.", "slack")
            db.execute("UPDATE issues SET escalated=1 WHERE id=?", (i["id"],)); log(db, i["id"], None, "escalated", "SLA breached")
    db.commit()


def stats(db, clf):
    check_sla(db)
    issues = list_issues(db)
    count = lambda key: {k: sum(1 for i in issues if i[key] == k) for k in sorted({i[key] for i in issues if i[key]})}
    ms = [i["triage_ms"] for i in issues if i["triage_ms"] is not None]
    n_fb = db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    return {"kpis": {"total": len(issues), "open": sum(i["status"] in OPEN_STATES for i in issues),
                     "resolved": sum(i["status"] in ("Resolved", "Closed") for i in issues),
                     "duplicates": sum(i["status"] == "Duplicate" for i in issues),
                     "sla_breaches": sum(i["sla_breached"] for i in issues),
                     "avg_triage_ms": round(sum(ms) / len(ms)) if ms else 0,
                     "overrides": n_fb, "override_rate": round(n_fb / max(1, 3 * len(issues)), 3)},
            "by_severity": count("severity"), "by_component": count("component"), "by_status": count("status"),
            "workload": developers_with_load(db),
            "model": {"training_rows": clf.n_train, "holdout_accuracy": clf.accuracy}}


def retrain(db, clf):
    rows = db.execute("""SELECT i.title,i.description,i.type,i.severity,i.component FROM issues i
        WHERE i.id IN (SELECT issue_id FROM feedback)""").fetchall()
    extra = [{"text": f"{r['title']}. {r['description']}", "type": r["type"], "severity": r["severity"], "component": r["component"]}
             for r in rows] * 5  # corrected examples are up-weighted
    clf.train(extra)
    return {"corrected_issues_used": len(rows), "training_rows": clf.n_train, "holdout_accuracy": clf.accuracy}


DEMO_REPORTS = [
    ("Payment page crashes on submit", "Clicking Pay Now on the checkout page crashes the app. Happens for every card type on production."),
    ("Login button misaligned on mobile", "On small screens the login button overlaps the password field. Only a visual issue, login still works."),
    ("Report export takes forever", "Exporting the monthly report from the reporting query takes more than 30 seconds and sometimes times out."),
    ("Add dark mode to the dashboard", "It would be great to have a dark theme option in the settings page for night usage."),
    ("SQL injection possible in password reset", "The password reset form accepts quotes and the backend query breaks, looks vulnerable to SQL injection."),
    ("Typo on profile page", "The profile page footer says 'Setings' instead of 'Settings'. Small text typo only."),
    ("Database connection drops intermittently", "The database connection fails with an exception a few times per hour and the orders service stops responding."),
    ("Coupon code ignores selected option", "Applying a coupon code on the billing page ignores the selected plan and shows a wrong total sometimes."),
    ("Payment page crashing at checkout", "The payment page crashed again when I click submit at checkout, the app crashes completely."),
]


def seed_demo(db, clf):
    if db.execute("SELECT COUNT(*) FROM issues").fetchone()[0]: return
    tester = db.execute("SELECT id FROM users WHERE role='reporter'").fetchone()["id"]
    for t, d in DEMO_REPORTS: create_issue(db, clf, tester, t, d)
