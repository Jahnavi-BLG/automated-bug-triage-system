"""Automated tests mirroring the TEST CASES slide (TC01-TC08).   Run:  pytest -q"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from app import create_app

@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"), seed=False)
    return app.test_client()

def login(c, email="lead@demo.com", pw="demo123"):
    return c.post("/api/login", json={"email": email, "password": pw})

def report(c, title, desc):
    return c.post("/api/issues", json={"title": title, "description": desc})

CRASH = "Clicking Pay Now on the checkout page crashes the app for every card type."

def test_tc01_valid_login(client):
    r = login(client); assert r.status_code == 200 and r.json["user"]["role"] == "lead"
    assert client.get("/api/stats").status_code == 200

def test_tc02_invalid_login(client):
    assert login(client, pw="wrong").status_code == 401
    assert client.get("/api/issues").status_code == 401

def test_tc03_submit_bug_report(client):
    login(client, "tester@demo.com")
    r = report(client, "Search box not working", "Typing in the search box on the dashboard page does nothing at all.")
    assert r.status_code == 201
    i = r.json["issue"]; assert i["id"] >= 1 and i["status"] in ("Assigned", "New")

def test_tc04_auto_classification(client):
    login(client, "tester@demo.com")
    i = report(client, "App crashes on payment page", CRASH).json["issue"]
    assert (i["type"], i["severity"], i["component"]) == ("Bug", "Critical", "payments")

def test_tc05_duplicate_detection(client):
    login(client, "tester@demo.com")
    first = report(client, "Payment page crashes on submit", CRASH).json["issue"]
    second = report(client, "Payment page crashing at checkout", "The payment page crashed again when I click submit at checkout.").json["issue"]
    assert second["status"] == "Duplicate" and second["duplicate_of"] == first["id"] and second["assignee_id"] is None

def test_tc06_smart_assignment(client):
    login(client, "tester@demo.com")
    i = report(client, "Dashboard dropdown menu misaligned", "The dropdown menu on the dashboard page is slightly misaligned on mobile.").json["issue"]
    assert i["component"] == "ui" and i["assignee_name"] in ("Anita Rao", "Arjun Das")  # both have the ui skill

def test_tc06b_workload_balancing(client):
    login(client, "tester@demo.com")
    names = [report(client, f"Sidebar {w} broken", f"The sidebar {w} is completely broken and unusable now, case {n}.").json["issue"]["assignee_name"]
             for n, w in enumerate(["zebra", "kiwi", "lemur", "panda"])]
    assert len(set(names)) > 1, "load should be spread across ui developers"

def test_tc07_incomplete_report(client):
    login(client, "tester@demo.com")
    r = report(client, "Bug", ""); assert r.status_code == 400 and "description" in r.json["error"].lower()

def test_tc08_sla_escalation(client):
    login(client, "tester@demo.com")
    iid = report(client, "App crashes on payment page", CRASH).json["issue"]["id"]
    from db import connect
    # force the SLA into the past directly in the DB
    con = connect(client.application.config["DB_PATH"]); con.execute("UPDATE issues SET sla_due='2000-01-01T00:00:00+00:00' WHERE id=?", (iid,)); con.commit(); con.close()
    client.post("/api/logout"); login(client)
    assert client.get("/api/stats").json["kpis"]["sla_breaches"] == 1
    msgs = [n["message"] for n in client.get("/api/notifications").json["notifications"]]
    assert any("SLA BREACH" in m for m in msgs)

def test_permissions_and_feedback_loop(client):
    login(client, "tester@demo.com")
    iid = report(client, "App crashes on payment page", CRASH).json["issue"]["id"]
    assert client.patch(f"/api/issues/{iid}", json={"severity": "Low"}).status_code == 403   # reporter cannot override
    client.post("/api/logout"); login(client)
    assert client.patch(f"/api/issues/{iid}", json={"severity": "High"}).json["issue"]["severity"] == "High"
    assert client.post("/api/model/retrain").json["corrected_issues_used"] == 1

def test_status_workflow(client):
    login(client, "tester@demo.com")
    iid = report(client, "App crashes on payment page", CRASH).json["issue"]["id"]
    client.post("/api/logout"); login(client)
    assert client.patch(f"/api/issues/{iid}", json={"status": "Closed"}).status_code == 400   # illegal jump
    assert client.patch(f"/api/issues/{iid}", json={"status": "In Progress"}).status_code == 200
