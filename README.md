# BugTriage: Automated Bug Triage & Issue Management System
Software Engineering Lab, project-based learning.

A web app that automatically **classifies** new bug reports (type, severity, priority, component), **detects duplicates**,
**assigns the best developer** (skills + workload), tracks the **lifecycle and SLA**, and shows an **analytics dashboard**.

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, vanilla JavaScript (no build step) |
| Backend | Python 3.9+, Flask REST API |
| Database | SQLite (a single file, created automatically) |
| ML / NLP | scikit-learn: TF-IDF + Logistic Regression, cosine similarity |

---
## 1. How to run

**Prerequisite:** Python 3.9 or newer (`python --version`).

```bash
# 1) open a terminal inside the bugtriage folder
cd bugtriage

# 2) (recommended) create a virtual environment
python -m venv venv
#   Windows:      venv\Scripts\activate
#   Mac / Linux:  source venv/bin/activate

# 3) install dependencies
pip install -r requirements.txt

# 4) start the server
python app.py
```
Open **http://127.0.0.1:5000** in your browser. On first start the database is created and 9 demo issues are triaged automatically.

> Windows: if `python` is not found, try `py`. Mac/Linux: try `python3` / `pip3`.
> Different port: `PORT=8000 python app.py` (Windows PowerShell: `$env:PORT=8000; python app.py`).
> Reset all data: stop the server, delete `bugtriage.db`, start again.

### Demo accounts (password for all: `demo123`)
| Email | Role | Can do |
|---|---|---|
| lead@demo.com | Triage lead | everything: override predictions, reassign, retrain model |
| ravi@demo.com, anita@demo.com, kiran@demo.com, meera@demo.com, arjun@demo.com | Developer | update status of issues assigned to them, comment |
| tester@demo.com | Reporter | report bugs, verify/close resolved ones |

---
## 2. Run the automated tests
```bash
pytest -q
```
The tests mirror the **Test Cases** slide:

| Test | What it checks |
|---|---|
| TC01 / TC02 | valid login works, wrong password is denied |
| TC03 | bug report is created with an ID |
| TC04 | "App crashes on payment page" becomes Bug / Critical / payments |
| TC05 | similar report is linked as a duplicate and not assigned |
| TC06 | assignee has the right skill, load is spread across developers |
| TC07 | incomplete report is rejected with a validation message |
| TC08 | SLA breach creates an escalation notification for the lead |
| extra | role permissions, status workflow rules, feedback loop and retraining |

---
## 3. 5-minute demo script
1. Sign in as `lead@demo.com`. The **Dashboard** shows KPIs, charts and the issue queue.
2. **Report Bug** with title `Checkout page crashes on pay`, description `The payment page crashes every time I click the pay button at checkout.`
   It is classified (Critical, Bug, payments), and shows model confidence and the developer ranking.
3. Submit a similar report again. It is flagged **Duplicate** and linked, with no new work item.
4. Open an issue. As lead, **override** the severity. This is saved as feedback.
5. Go to **ML Model**, click **Retrain**. Corrected issues are added to the training data.
6. Sign in as a developer and move an issue to *In Progress*, then *Resolved*. The reporter gets a notification.
7. **Team** page shows each developer's skills and workload. **Notifications** shows the simulated Email/Slack alerts.

---
## 4. How it maps to the presentation
| Slide / module | Where in the code |
|---|---|
| Issue Intake | `POST /api/issues` in `app.py`, `create_issue()` in `services.py` |
| Classification | `Classifier` in `triage.py` (`preprocess`, TF-IDF + Logistic Regression + severity keyword rules) |
| Duplicate Detection | `find_duplicates()` in `triage.py` (cosine similarity, threshold 0.60) |
| Assignment Engine | `rank_developers()` in `triage.py` (60% skill match + 40% free capacity) |
| Lifecycle & SLA | `ALLOWED` workflow, `check_sla()` in `services.py` (Critical 4h, High 24h, Medium 72h, Low 7d) |
| Notifications | `notify()` in `services.py` (stored in DB and printed to the console; swap in SMTP or Slack here) |
| Dashboard & Feedback | `stats()`, `retrain()`, and `static/app.js` |
| Class diagram | users, issues, comments, history, notifications, feedback tables in `db.py` |

## 5. REST API
All endpoints except login need a signed-in session cookie.

| Method & path | Purpose |
|---|---|
| `POST /api/login`, `POST /api/logout`, `GET /api/me` | authentication |
| `GET /api/issues?status=&severity=&component=&q=` | list / filter / search |
| `POST /api/issues` `{title, description}` | report a bug, returns the issue plus triage details |
| `GET /api/issues/<id>` | issue, comments, history, allowed next statuses |
| `PATCH /api/issues/<id>` | change status; lead-only: severity, type, component, priority, assignee_id |
| `POST /api/issues/<id>/comments` | add a comment |
| `GET /api/stats`, `GET /api/team`, `GET /api/notifications` | dashboard data |
| `POST /api/model/retrain` | lead only: retrain with corrected issues |

## 6. Project structure
```
bugtriage/
  app.py                  Flask app + REST routes
  services.py             business logic (triage flow, workflow, SLA, stats)
  triage.py               ML: preprocessing, classifier, duplicates, assignment
  db.py                   SQLite schema + demo users
  make_training_data.py   generates data/training.csv (728 labelled reports)
  data/training.csv       training data
  static/                 index.html, style.css, app.js  (the website)
  tests/test_app.py       automated tests
  requirements.txt
```

## 7. Honest limitations (good to mention in your viva)
* The classifier is trained on **synthetic template data**, so its hold-out accuracy (about 100%) is optimistic. Real reports are messier. The **override, then retrain** loop is how it adapts.
* Duplicate detection uses TF-IDF keyword similarity, not deep semantic embeddings. A sentence-transformer model could replace `find_duplicates()` for better paraphrase matching.
* Email/Slack are simulated. Authentication is basic (session cookie); a production system would add HTTPS, CSRF protection and password policies.
* SQLite is fine for a lab project; use PostgreSQL for a multi-user deployment.

## 8. Troubleshooting
| Problem | Fix |
|---|---|
| `ModuleNotFoundError: flask` or `sklearn` | activate the venv and run `pip install -r requirements.txt` |
| `Address already in use` | another app uses port 5000, so run with `PORT=5001 python app.py` |
| Page is blank / login fails | hard refresh (Ctrl+Shift+R); check the terminal for errors |
| Want a fresh start | delete `bugtriage.db` and restart |
