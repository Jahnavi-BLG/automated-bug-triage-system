"""Flask REST API + static single-page frontend.   Run:  python app.py"""
import os
from functools import wraps
from flask import Flask, jsonify, request, session, g, send_from_directory
from werkzeug.security import check_password_hash
import db as dbm, services as svc, triage

BASE = os.path.dirname(os.path.abspath(__file__))


def create_app(db_path=None, seed=True):
    app = Flask(__name__, static_folder=os.path.join(BASE, "static"), static_url_path="")
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    path = db_path or os.path.join(BASE, "bugtriage.db")
    app.config["DB_PATH"] = path
    dbm.init_db(path)
    clf = triage.Classifier()
    if seed:
        c = dbm.connect(path); svc.seed_demo(c, clf); c.close()

    def conn():
        if "db" not in g: g.db = dbm.connect(path)
        return g.db

    @app.teardown_appcontext
    def close(_):
        d = g.pop("db", None)
        if d: d.close()

    def user():
        if "uid" not in session: return None
        r = conn().execute("SELECT id,name,email,role,skills FROM users WHERE id=?", (session["uid"],)).fetchone()
        return dict(r) if r else None

    def auth(*roles):
        def deco(f):
            @wraps(f)
            def w(*a, **k):
                u = user()
                if not u: return jsonify(error="Please log in"), 401
                if roles and u["role"] not in roles: return jsonify(error="Not allowed for your role"), 403
                g.user = u
                return f(*a, **k)
            return w
        return deco

    @app.errorhandler(svc.ValidationError)
    def _v(e): return jsonify(error=str(e)), 400
    @app.errorhandler(svc.Forbidden)
    def _f(e): return jsonify(error=str(e)), 403
    @app.errorhandler(svc.NotFound)
    def _n(e): return jsonify(error=str(e)), 404

    @app.get("/")
    def index(): return send_from_directory(app.static_folder, "index.html")

    # ---------- auth
    @app.post("/api/login")
    def login():
        d = request.get_json(silent=True) or {}
        r = conn().execute("SELECT * FROM users WHERE email=?", ((d.get("email") or "").strip().lower(),)).fetchone()
        if not r or not check_password_hash(r["password_hash"], d.get("password") or ""):
            return jsonify(error="Invalid email or password"), 401   # TC02
        session["uid"] = r["id"]
        return jsonify(user={k: r[k] for k in ("id", "name", "email", "role", "skills")})

    @app.post("/api/logout")
    def logout(): session.clear(); return jsonify(ok=True)

    @app.get("/api/me")
    @auth()
    def me(): return jsonify(user=g.user)

    # ---------- issues
    @app.get("/api/issues")
    @auth()
    def issues():
        a = request.args
        return jsonify(issues=svc.list_issues(conn(), a.get("status"), a.get("severity"), a.get("component"), a.get("q")))

    @app.post("/api/issues")
    @auth()
    def new_issue():
        d = request.get_json(silent=True) or {}
        return jsonify(svc.create_issue(conn(), clf, g.user["id"], d.get("title"), d.get("description"))), 201

    @app.get("/api/issues/<int:iid>")
    @auth()
    def one(iid):
        c = conn(); issue = svc.get_issue(c, iid)
        q = lambda sql: [dict(r) for r in c.execute(sql, (iid,)).fetchall()]
        return jsonify(issue=issue,
            comments=q("SELECT c.*,u.name FROM comments c JOIN users u ON u.id=c.user_id WHERE issue_id=? ORDER BY c.id"),
            history=q("SELECT h.*,u.name FROM history h LEFT JOIN users u ON u.id=h.user_id WHERE issue_id=? ORDER BY h.id"),
            allowed_status=svc.ALLOWED.get(issue["status"], []))

    @app.patch("/api/issues/<int:iid>")
    @auth()
    def patch(iid): return jsonify(issue=svc.update_issue(conn(), g.user, iid, request.get_json(silent=True) or {}))

    @app.post("/api/issues/<int:iid>/comments")
    @auth()
    def comment(iid):
        svc.add_comment(conn(), g.user, iid, (request.get_json(silent=True) or {}).get("text")); return jsonify(ok=True), 201

    # ---------- dashboard / team / notifications / model
    @app.get("/api/stats")
    @auth()
    def stats(): return jsonify(svc.stats(conn(), clf))

    @app.get("/api/team")
    @auth()
    def team(): return jsonify(developers=svc.developers_with_load(conn()))

    @app.get("/api/notifications")
    @auth()
    def notifs():
        rows = conn().execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (g.user["id"],)).fetchall()
        return jsonify(notifications=[dict(r) for r in rows])

    @app.post("/api/model/retrain")
    @auth("lead")
    def retrain(): return jsonify(svc.retrain(conn(), clf))

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Bug Triage System running at  http://127.0.0.1:{port}\n  Demo login: lead@demo.com / demo123\n")
    create_app().run(host="127.0.0.1", port=port, debug=False)
