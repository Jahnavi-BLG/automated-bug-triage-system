/* BugTriage single-page frontend (vanilla JS, no build step) */
const $ = (s, e = document) => e.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = d => d ? new Date(d).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "-";
const COMPONENTS = ["ui", "backend", "database", "payments", "auth"];
const TYPES = ["Bug", "Performance", "Security", "Feature Request"];
const SEVS = ["Critical", "High", "Medium", "Low"];
const STATUSES = ["New", "Assigned", "In Progress", "Resolved", "Closed", "Duplicate"];
let me = null, unread = 0;

async function api(path, { method = "GET", body } = {}) {
  const r = await fetch("/api" + path, { method, credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(j.error || "Request failed"); e.status = r.status; throw e; }
  return j;
}
const sev = s => `<span class="pill ${esc(s)}">${esc(s)}</span>`;
const stat = s => `<span class="pill st ${esc(s)}">${esc(s)}</span>`;
const bars = (obj, order) => {
  const keys = order || Object.keys(obj), max = Math.max(1, ...Object.values(obj));
  return keys.map(k => `<div class="bar"><span class="l">${esc(k)}</span><span class="tr"><span class="fi" style="width:${(obj[k] || 0) / max * 100}%"></span></span><span class="n">${obj[k] || 0}</span></div>`).join("") || '<div class="empty">No data yet</div>';
};
const opts = (arr, sel, blank) => (blank ? `<option value="">${blank}</option>` : "") + arr.map(a => `<option ${a === sel ? "selected" : ""}>${esc(a)}</option>`).join("");
const issueTable = list => list.length ? `<table><tr><th>ID</th><th>Title</th><th>Type</th><th>Severity</th><th>Component</th><th>Assignee</th><th>Status</th></tr>${list.map(i =>
  `<tr class="click" onclick="location.hash='#/issue/${i.id}'"><td>#${i.id}</td><td>${esc(i.title)}${i.sla_breached ? ' <span class="chip" style="background:#FDE4E7;color:#A31F34">SLA overdue</span>' : ""}</td><td>${esc(i.type)}</td><td>${sev(i.severity)}</td><td>${esc(i.component)}</td><td>${esc(i.assignee_name || "-")}</td><td>${stat(i.status)}</td></tr>`).join("")}</table>` : '<div class="empty">No issues found</div>';

/* ---------- shell ---------- */
function shell(active, html) {
  const nav = [["dashboard", "Dashboard"], ["issues", "All Issues"], ["new", "Report Bug"], ["team", "Team"], ["notifications", "Notifications"]];
  if (me.role === "lead") nav.push(["model", "ML Model"]);
  $("#app").innerHTML = `<div class="shell"><aside class="side"><div class="brand">BugTriage<small>Automated triage system</small></div>
    ${nav.map(([h, t]) => `<a class="${active === h ? "on" : ""}" href="#/${h}"><span class="t">${t}</span>${h === "notifications" && unread ? `<span class="badge">${unread}</span>` : ""}</a>`).join("")}
    <div class="who"><b>${esc(me.name)}</b>${esc(me.role)}<br><a style="padding:6px 0" onclick="logout()">Sign out</a></div></aside><main class="main">${html}</main></div>`;
}
async function logout() { await api("/logout", { method: "POST" }); me = null; route(); }

/* ---------- login ---------- */
function loginView(err = "") {
  $("#app").innerHTML = `<div class="login"><h1 style="text-align:center;margin-bottom:6px">BugTriage</h1><p class="muted" style="text-align:center;margin-top:0">Automated Bug Triage &amp; Issue Management System</p>
  <div class="card"><label>Email</label><input id="em" value="lead@demo.com"><label>Password</label><input id="pw" type="password" value="demo123">
  ${err ? `<div class="err">${esc(err)}</div>` : ""}<p><button class="btn" style="width:100%" id="go">Sign in</button></p>
  <div class="demo"><b>Demo accounts</b> (password <code>demo123</code>)<br>lead@demo.com &middot; triage lead<br>ravi@demo.com / anita@demo.com &middot; developers<br>tester@demo.com &middot; reporter</div></div></div>`;
  const go = async () => { try { me = (await api("/login", { method: "POST", body: { email: $("#em").value, password: $("#pw").value } })).user; location.hash = "#/dashboard"; route(); } catch (e) { loginView(e.message); } };
  $("#go").onclick = go; $("#pw").onkeydown = e => e.key === "Enter" && go();
}

/* ---------- pages ---------- */
async function dashboard() {
  const [s, l] = await Promise.all([api("/stats"), api("/issues")]); const k = s.kpis;
  shell("dashboard", `<div class="top"><h1>Dashboard</h1><a class="btn" href="#/new" style="text-decoration:none">+ Report a bug</a></div>
  <div class="grid g4"><div class="kpi"><small>Open issues</small><b>${k.open}</b></div><div class="kpi"><small>Avg. triage time</small><b>${k.avg_triage_ms} ms</b></div>
  <div class="kpi"><small>Duplicates caught</small><b>${k.duplicates}</b></div><div class="kpi ${k.sla_breaches ? "warn" : ""}"><small>SLA breaches</small><b>${k.sla_breaches}</b></div></div>
  <div class="grid g3"><div class="card"><h2>Issues by severity</h2>${bars(s.by_severity, SEVS)}</div><div class="card"><h2>Issues by component</h2>${bars(s.by_component, COMPONENTS)}</div>
  <div class="card"><h2>Issues by status</h2>${bars(s.by_status, STATUSES)}</div></div>
  <div class="card"><h2>Recent issues</h2>${issueTable(l.issues.slice(0, 8))}</div>`);
}

async function issues() {
  shell("issues", `<div class="top"><h1>All Issues</h1></div><div class="card"><div class="row"><div><label>Search</label><input id="q" placeholder="Search title or description"></div>
  <div><label>Status</label><select id="fs">${opts(STATUSES, "", "All")}</select></div><div><label>Severity</label><select id="fv">${opts(SEVS, "", "All")}</select></div>
  <div><label>Component</label><select id="fc">${opts(COMPONENTS, "", "All")}</select></div></div></div><div class="card" id="list"></div>`);
  const load = async () => {
    const p = new URLSearchParams({ q: $("#q").value, status: $("#fs").value, severity: $("#fv").value, component: $("#fc").value });
    $("#list").innerHTML = issueTable((await api("/issues?" + p)).issues);
  };
  ["#q", "#fs", "#fv", "#fc"].forEach(s => $(s).oninput = load); load();
}

function newIssue() {
  shell("new", `<div class="top"><h1>Report a Bug</h1></div><div class="grid g2" style="align-items:start"><div class="card"><label>Title</label><input id="t" placeholder="e.g. Payment page crashes on submit">
  <label>Description</label><textarea id="d" placeholder="Steps to reproduce, expected vs actual behaviour, environment..."></textarea>
  <div id="msg"></div><p><button class="btn" id="sub">Submit &amp; auto-triage</button></p>
  <p class="note">Try a duplicate: report "Payment page crashing at checkout" twice.</p></div><div id="res"></div></div>`);
  $("#sub").onclick = async () => {
    $("#msg").innerHTML = ""; $("#sub").disabled = true;
    try {
      const r = await api("/issues", { method: "POST", body: { title: $("#t").value, description: $("#d").value } }); showTriage(r);
    } catch (e) { $("#msg").innerHTML = `<div class="err">${esc(e.message)}</div>`; $("#res").innerHTML = ""; }
    $("#sub").disabled = false;
  };
}
function showTriage({ issue: i, triage: t }) {
  const c = t.prediction.confidence;
  $("#res").innerHTML = `<div class="card"><h2>Triage result for #${i.id}</h2>
  <div class="ok">Triaged automatically in ${t.triage_ms} ms</div>
  <p>${sev(i.severity)} <span class="chip">${esc(i.type)}</span><span class="chip">${esc(i.component)}</span><span class="chip">Priority ${esc(i.priority)}</span></p>
  <div class="note">Model confidence: type ${Math.round(c.type * 100)}% &middot; severity ${Math.round(c.severity * 100)}% &middot; component ${Math.round(c.component * 100)}%</div>
  <h2 style="margin-top:16px">${i.status === "Duplicate" ? "Duplicate detected" : "Assignment"}</h2>
  ${i.status === "Duplicate" ? `<div class="err">Linked to <a href="#/issue/${i.duplicate_of}">#${i.duplicate_of}</a> (similarity ${Math.round(i.duplicate_score * 100)}%). No new work item was created.</div>`
    : `<p>Assigned to <b>${esc(i.assignee_name || "nobody")}</b>. Due by ${fmt(i.sla_due)}.</p>` + t.ranking.map((r, n) => `<div class="rank"><span>${n + 1}. <b>${esc(r.name)}</b> <span class="muted">${esc(r.reason)}</span></span><b>${Math.round(r.score * 100)}</b></div>`).join("")}
  <p style="margin-top:14px"><a class="btn sm" style="text-decoration:none" href="#/issue/${i.id}">Open issue</a></p></div>`;
}

async function issueDetail(id) {
  const r = await api("/issues/" + id), i = r.issue, lead = me.role === "lead";
  const devs = lead ? (await api("/team")).developers : [];
  shell("issues", `<div class="top"><h1>Issue #${i.id}</h1><a href="#/issues">&larr; All issues</a></div>
  <div class="card"><h2 style="font-size:23px">${esc(i.title)}</h2><p>${sev(i.severity)} ${stat(i.status)} <span class="chip">${esc(i.type)}</span><span class="chip">${esc(i.component)}</span><span class="chip">${esc(i.priority)}</span>
  ${i.sla_breached ? '<span class="chip" style="background:#FDE4E7;color:#A31F34">SLA overdue</span>' : ""}</p>
  <p style="white-space:pre-wrap">${esc(i.description)}</p>
  <div class="meta"><div><small>Reporter</small>${esc(i.reporter_name)}</div><div><small>Assignee</small>${esc(i.assignee_name || "-")}</div><div><small>Created</small>${fmt(i.created_at)}</div>
  <div><small>SLA due</small>${fmt(i.sla_due)}</div><div><small>Model confidence</small>${Math.round((i.confidence || 0) * 100)}%</div>
  ${i.duplicate_of ? `<div><small>Duplicate of</small><a href="#/issue/${i.duplicate_of}">#${i.duplicate_of}</a> (${Math.round(i.duplicate_score * 100)}%)</div>` : ""}</div></div>
  <div id="msg"></div>
  <div class="grid g2" style="align-items:start"><div>
   <div class="card"><h2>Update status</h2>${r.allowed_status.map(s => `<button class="btn sm" data-s="${esc(s)}">Move to ${esc(s)}</button>`).join("") || '<span class="muted">No further transitions</span>'}</div>
   ${lead ? `<div class="card"><h2>Triage lead override</h2><p class="note" style="margin-top:0">Corrections are saved as feedback to improve the ML model.</p>
    <div class="row"><div><label>Severity</label><select id="o-sev">${opts(SEVS, i.severity)}</select></div><div><label>Type</label><select id="o-type">${opts(TYPES, i.type)}</select></div></div>
    <div class="row"><div><label>Component</label><select id="o-comp">${opts(COMPONENTS, i.component)}</select></div>
    <div><label>Assignee</label><select id="o-as"><option value="">(unchanged)</option>${devs.map(d => `<option value="${d.id}" ${d.id === i.assignee_id ? "selected" : ""}>${esc(d.name)} (${d.load} open)</option>`).join("")}</select></div></div>
    <p><button class="btn" id="ov">Apply override</button></p></div>` : ""}
   <div class="card"><h2>Comments</h2>${r.comments.map(c => `<div class="cmt"><small><b>${esc(c.name)}</b> &middot; ${fmt(c.created_at)}</small><div>${esc(c.text)}</div></div>`).join("") || '<div class="muted">No comments yet</div>'}
    <label>Add a comment</label><textarea id="ct" style="min-height:70px"></textarea><p><button class="btn sm" id="cb">Post comment</button></p></div>
  </div><div class="card"><h2>Activity timeline</h2><div class="tl">${r.history.map(h => `<div><b>${esc(h.action)}</b> &mdash; ${esc(h.detail)}<br><span class="muted">${esc(h.name || "System")} &middot; ${fmt(h.created_at)}</span></div>`).join("")}</div></div></div>`);
  const act = async (fn) => { try { await fn(); issueDetail(id); } catch (e) { $("#msg").innerHTML = `<div class="err">${esc(e.message)}</div>`; } };
  document.querySelectorAll("[data-s]").forEach(b => b.onclick = () => act(() => api("/issues/" + id, { method: "PATCH", body: { status: b.dataset.s } })));
  $("#cb").onclick = () => act(() => api(`/issues/${id}/comments`, { method: "POST", body: { text: $("#ct").value } }));
  if (lead) $("#ov").onclick = () => act(() => api("/issues/" + id, { method: "PATCH", body: { severity: $("#o-sev").value, type: $("#o-type").value, component: $("#o-comp").value, assignee_id: $("#o-as").value || null } }));
}

async function team() {
  const d = (await api("/team")).developers;
  shell("team", `<div class="top"><h1>Team workload</h1></div><div class="grid g3">${d.map(x => `<div class="card"><div class="dev"><div class="avatar">${esc(x.name[0])}</div><div><b>${esc(x.name)}</b><br>${x.skills.split(",").map(s => `<span class="chip">${esc(s)}</span>`).join("")}</div></div>
  <div class="bar" style="margin-top:14px"><span class="l">Open</span><span class="tr"><span class="fi" style="width:${Math.min(100, x.load / 8 * 100)}%"></span></span><span class="n">${x.load}</span></div><div class="note">Capacity: 8 open issues</div></div>`).join("")}</div>`);
}

async function notifications() {
  const n = (await api("/notifications")).notifications; unread = 0;
  shell("notifications", `<div class="top"><h1>Notifications</h1></div><div class="card">${n.map(x => `<div class="rank"><span><span class="chip">${esc(x.channel)}</span> ${esc(x.message)}</span><span class="muted">${fmt(x.created_at)}</span></div>`).join("") || '<div class="empty">Nothing yet</div>'}
  <p class="note">Email and Slack channels are simulated: messages are stored here and printed in the server console.</p></div>`);
}

async function model() {
  const s = await api("/stats"), m = s.model, k = s.kpis;
  shell("model", `<div class="top"><h1>ML model</h1></div><div class="grid g4">${["type", "severity", "component"].map(t => `<div class="kpi"><small>${t} hold-out accuracy</small><b>${Math.round(m.holdout_accuracy[t] * 100)}%</b></div>`).join("")}<div class="kpi"><small>Training rows</small><b>${m.training_rows}</b></div></div>
  <div class="card"><h2>Feedback loop</h2><p>The triage lead has corrected <b>${k.overrides}</b> predictions (override rate ${(k.override_rate * 100).toFixed(1)}%). Retraining adds those corrected issues to the training data (weighted x5).</p>
  <div id="msg"></div><button class="btn" id="rt">Retrain model now</button>
  <p class="note">Accuracy is measured on synthetic seed data, so it is optimistic. It reflects real behaviour better as real reports are added.</p></div>`);
  $("#rt").onclick = async () => { try { const r = await api("/model/retrain", { method: "POST" }); $("#msg").innerHTML = `<div class="ok">Retrained with ${r.corrected_issues_used} corrected issue(s). Training rows: ${r.training_rows}.</div>`; } catch (e) { $("#msg").innerHTML = `<div class="err">${esc(e.message)}</div>`; } };
}

/* ---------- router ---------- */
async function route() {
  if (!me) { try { me = (await api("/me")).user; } catch { return loginView(); } }
  try { unread = (await api("/notifications")).notifications.filter(n => !n.is_read).length; } catch {}
  const [, page, arg] = (location.hash || "#/dashboard").split("/");
  try {
    if (page === "issue") await issueDetail(arg);
    else await ({ dashboard, issues, new: newIssue, team, notifications, model }[page] || dashboard)();
  } catch (e) { if (e.status === 401) { me = null; loginView("Session expired"); } else shell("", `<div class="err">${esc(e.message)}</div>`); }
}
window.addEventListener("hashchange", route); route();
