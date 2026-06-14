/* Career Agent UI — polls /api/state and renders the pipeline. No build step. */
let STATE = { jobs: [], approvals: [], tasks: [] };
let lastPendingIds = new Set();
let lastApprovalsSig = "";
let lastJobsSig = "";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => (s || "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ---------------------------------------------------------------- polling */
async function refresh() {
  try {
    const r = await fetch("/api/state");
    STATE = await r.json();
    render();
  } catch (e) { /* server restarting; keep last state */ }
}
setInterval(refresh, 2500);
refresh();

/* ----------------------------------------------------------------- render */
function render() {
  renderStats();
  renderApprovals();
  renderJobs();
  renderApplications();
  renderResumes();
  renderTasks();
}

function renderStats() {
  const counts = {};
  for (const j of STATE.jobs) counts[j.status] = (counts[j.status] || 0) + 1;
  const order = ["scored", "approved", "tailored", "applied"];
  const labels = { scored: "scored", approved: "tailoring", tailored: "ready to apply", applied: "applied" };
  $("#stats").innerHTML = order
    .map((s) => `<span class="stat"><b>${counts[s] || 0}</b>${labels[s]}</span>`)
    .join("");
}

/* -------------------------------------------------------------- approvals */
function renderApprovals() {
  const pending = STATE.approvals.filter((a) => a.status === "pending");
  const badge = $("#approvalBadge");
  badge.textContent = pending.length;
  badge.classList.toggle("hidden", pending.length === 0);
  $("#approvalsEmpty").classList.toggle("hidden", pending.length > 0);

  // flash title when new approvals arrive
  const ids = new Set(pending.map((a) => a.id));
  for (const id of ids) {
    if (!lastPendingIds.has(id)) document.title = "🔔 Career Agent — needs you";
  }
  if (pending.length === 0) document.title = "Career Agent";
  lastPendingIds = ids;

  // CRITICAL: only rebuild the cards when the pending set actually changes —
  // rebuilding every poll wipes radio selections and text the user is typing.
  const sig = JSON.stringify(pending.map((a) => a.id));
  if (sig === lastApprovalsSig) return;
  lastApprovalsSig = sig;

  const list = $("#approvalsList");
  list.innerHTML = pending.map((a) => {
    if (a.type === "gap_check") return gapCard(a);
    const cls = a.type === "submit_gate" ? "gate" : "gap";
    const buttons = (a.options && a.options.length)
      ? a.options.map((o) =>
          `<button class="${o.toLowerCase().includes("submit") || o.toLowerCase() === "yes" ? "good" : ""}"
              onclick="answer('${a.id}', '${esc(o)}')">${esc(o)}</button>`).join("")
      : `<input type="text" id="ans-${a.id}" placeholder="type your answer…">
         <button class="primary" onclick="answer('${a.id}', document.getElementById('ans-${a.id}').value)">Send</button>`;
    return `<div class="card ${cls}">
      <h3>${a.type === "submit_gate" ? "🚦 " : "❓ "}${esc(a.title)}</h3>
      <div class="meta">${esc(a.job_id)} · ${esc(a.created)}</div>
      ${a.body ? `<pre>${esc(a.body)}</pre>` : ""}
      <div class="actions">${buttons}</div>
    </div>`;
  }).join("");
}

function gapCard(a) {
  const qs = (a.questions || []).map((q, i) => `
    <div class="gapq" data-i="${i}">
      <div class="req">${esc(q.requirement)}</div>
      <div class="ctx">${esc(q.context || "")}</div>
      <label><input type="radio" name="gap-${a.id}-${i}" value="yes"> I've done this</label>
      <label><input type="radio" name="gap-${a.id}-${i}" value="no" checked> Not really</label>
      <input type="text" id="gapdetail-${a.id}-${i}"
             placeholder="if yes: where/how? e.g. 'used Docker daily to package ML services'">
    </div>`).join("");
  return `<div class="card gap">
    <h3>🧩 ${esc(a.title)}</h3>
    <div class="meta">${esc(a.job_id)} · ${esc(a.created)}</div>
    <pre>${esc(a.body)}</pre>
    ${qs}
    <div class="actions"><button class="primary" onclick="answerGaps('${a.id}', ${a.questions.length})">Send answers</button></div>
  </div>`;
}

async function answer(id, value) {
  await fetch(`/api/approvals/${id}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer: value }),
  });
  refresh();
}

async function answerGaps(id, n) {
  const a = STATE.approvals.find((x) => x.id === id);
  const answers = [];
  for (let i = 0; i < n; i++) {
    const yes = document.querySelector(`input[name="gap-${id}-${i}"][value="yes"]`).checked;
    const detail = document.getElementById(`gapdetail-${id}-${i}`).value.trim();
    answers.push({ requirement: a.questions[i].requirement, have_it: yes, detail });
  }
  const missing = answers.filter((x) => x.have_it && !x.detail);
  if (missing.length && !confirm(
    `You said yes to ${missing.length} item(s) without a detail line. The agent can only ` +
    `add facts to your resume with some substance. Send anyway?`)) return;
  await fetch(`/api/approvals/${id}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer: answers }),
  });
  refresh();
}

/* ------------------------------------------------------------------- jobs */
const FILTERS = {
  shortlist: (j) => j.status === "scored" && ["A", "B"].includes(j.score),
  approved: (j) => j.status === "approved",
  tailored: (j) => j.status === "tailored",
  applied: (j) => j.status === "applied",
  all: () => true,
};

function liveState(j) {
  // join the task queue + pending approvals onto each job so progress is visible
  const waiting = STATE.approvals.find((a) => a.status === "pending" && a.job_id === j.id);
  if (waiting) return { pill: "🔔 needs you — see Needs You tab", cls: "needsyou", busy: false };
  const tasks = STATE.tasks.filter((t) => t.job_id === j.id);
  const active = tasks.find((t) => t.status === "running");
  if (active) return { pill: active.kind === "apply" ? "⚙️ applying…" : "⚙️ writing resume…", cls: "busy", busy: true };
  const queued = tasks.find((t) => t.status === "queued");
  if (queued) return { pill: `⏳ ${queued.kind} queued`, cls: "queuedpill", busy: true };
  const last = tasks[tasks.length - 1];
  if (last && last.status === "failed" && j.status === "approved")
    return { pill: "⚠️ tailoring failed — retry", cls: "failedpill", busy: false, retry: true };
  if (j.status === "approved") return { pill: "approved", cls: "approved", busy: false, retry: true };
  return null;
}

function renderJobs() {
  const f = FILTERS[$("#statusFilter").value] || FILTERS.all;
  const q = $("#searchBox").value.toLowerCase();
  const rows = STATE.jobs.filter(f).filter((j) =>
    !q || (j.title + " " + j.company).toLowerCase().includes(q));
  rows.sort((a, b) => (a.score || "Z").localeCompare(b.score || "Z"));

  // skip rebuild when nothing visible changed (preserves checkboxes/focus)
  const sig = JSON.stringify([$("#statusFilter").value, q,
    rows.map((j) => [j.id, j.status, j.resume_file]),
    STATE.tasks.map((t) => [t.id, t.status]),
    STATE.approvals.filter((a) => a.status === "pending").map((a) => a.id)]);
  if (sig === lastJobsSig) return;
  lastJobsSig = sig;

  const shortlistMode = $("#statusFilter").value === "shortlist";
  $("#jobsList").innerHTML = rows.length ? rows.map((j) => {
    const live = liveState(j);
    const pill = live
      ? `<span class="status-pill ${live.cls}">${live.pill}</span>`
      : `<span class="status-pill ${esc(j.status)}">${esc(j.status)}</span>`;
    return `
    <div class="job">
      ${shortlistMode ? `<input type="checkbox" class="jobcheck" value="${esc(j.id)}" onchange="toggleApproveBtn()">` : ""}
      <div class="score ${esc(j.score || "")}">${esc(j.score || "·")}</div>
      <div class="info">
        <div class="title">${esc(j.title)}</div>
        <div class="co">${esc(j.company)} · ${esc(j.location || "?")}${j.remote === "True" ? " · remote" : ""}
          ${j.salary_max ? ` · $${Math.round(j.salary_min / 1000)}–${Math.round(j.salary_max / 1000)}k` : ""}
          ${j.sponsor_risk === "YES" ? ' · <b style="color:var(--bad)">SPONSOR-RISK</b>' : ""}</div>
      </div>
      ${pill}
      <div class="actions">
        <button onclick="showJob('${esc(j.id)}')">details</button>
        ${j.resume_file ? `<button onclick="showResume('${esc(j.id)}')">resume</button>` : ""}
        ${live && live.retry ? `<button onclick="retryTailor('${esc(j.id)}')">tailor now</button>` : ""}
        ${j.status === "tailored" && !(live && live.busy) ? `<button class="good" onclick="applyJob('${esc(j.id)}')">apply</button>` : ""}
        ${j.status === "scored" ? `<button class="danger" onclick="rejectJob('${esc(j.id)}')">✕</button>` : ""}
      </div>
    </div>`;
  }).join("")
    : `<div class="empty"><h3>No jobs here</h3><p>Try another filter, or hit Find Jobs.</p></div>`;
}

async function retryTailor(id) {
  await fetch(`/api/jobs/${id}/tailor`, { method: "POST" });
  refresh();
}

function toggleApproveBtn() {
  const any = document.querySelectorAll(".jobcheck:checked").length > 0;
  $("#approveSelectedBtn").classList.toggle("hidden", !any);
}

$("#approveSelectedBtn").onclick = async () => {
  const ids = [...document.querySelectorAll(".jobcheck:checked")].map((c) => c.value);
  await fetch("/api/jobs/approve", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  $("#approveSelectedBtn").classList.add("hidden");
  refresh();
};

async function applyJob(id) {
  if (!confirm("Start the application in a visible Chrome window? You'll get the final Submit gate here before anything is sent.")) return;
  await fetch(`/api/jobs/${id}/apply`, { method: "POST" });
  refresh();
}
async function rejectJob(id) {
  await fetch(`/api/jobs/${id}/reject`, { method: "POST" });
  refresh();
}

function showJob(id) {
  const j = STATE.jobs.find((x) => x.id === id);
  openDrawer(`${j.title} — ${j.company}`,
    `<p style="margin-bottom:10px"><a style="color:var(--acc)" href="${esc(j.url)}" target="_blank">open posting ↗</a>
     &nbsp; score <b>${esc(j.score)}</b> · ${esc(j.status)}${j.notes ? ` · ${esc(j.notes)}` : ""}</p>
     <div id="jdContent"><pre>loading…</pre></div>`);
  fetch(`/api/file?path=${encodeURIComponent(j.description_file)}`)
    .then((r) => r.text())
    .then((t) => { $("#jdContent").innerHTML = `<pre>${esc(t)}</pre>`; })
    .catch(() => { $("#jdContent").innerHTML = "<pre>couldn't load description</pre>"; });
}

function showResume(id) {
  const j = STATE.jobs.find((x) => x.id === id);
  openDrawer(`Resume — ${j.title}`,
    `<iframe src="/api/file?path=${encodeURIComponent(j.resume_file)}"></iframe>`);
}

/* ----------------------------------------------------------- applications */
const APP_STAGES = ["applied", "interviewing", "offer", "rejected", "no-response", "withdrawn"];
let lastAppsSig = "";

function renderApplications() {
  const rows = STATE.jobs.filter((j) => APP_STAGES.includes(j.status));
  rows.sort((a, b) => (b.applied_date || "").localeCompare(a.applied_date || ""));
  const sig = JSON.stringify(rows.map((j) => [j.id, j.status, j.notes]));
  if (sig === lastAppsSig) return;
  lastAppsSig = sig;

  $("#applicationsList").innerHTML = rows.length ? rows.map((j) => `
    <div class="card">
      <h3>${esc(j.title)} <span style="color:var(--dim);font-weight:400">@ ${esc(j.company)}</span></h3>
      <div class="meta">applied ${esc(j.applied_date || "?")} ·
        <a style="color:var(--acc)" href="${esc(j.url)}" target="_blank">posting ↗</a>
        ${j.resume_file ? ` · <a style="color:var(--acc)" href="/api/file?path=${encodeURIComponent(j.resume_file)}" target="_blank">resume sent</a>` : ""}
        ${j.notes ? `<br>${esc(j.notes)}` : ""}</div>
      <div class="actions">
        <span class="status-pill ${esc(j.status)}" style="align-self:center">${esc(j.status)}</span>
        ${APP_STAGES.filter((s) => s !== j.status).map((s) =>
          `<button onclick="setStage('${esc(j.id)}','${s}')">${s === "no-response" ? "no response" : s}</button>`).join("")}
      </div>
    </div>`).join("")
    : `<div class="empty"><h3>No applications yet</h3><p>Tailored jobs get an <b>apply</b> button in the Jobs tab.</p></div>`;
}

async function setStage(id, status) {
  const note = prompt(`Moving to "${status}" — add a note? (recruiter name, interview date…)`, "") || "";
  await fetch(`/api/jobs/${id}/status`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, note }),
  });
  refresh();
}

/* ---------------------------------------------------------------- resumes */
let lastResumesSig = "";
async function renderResumes() {
  const r = await fetch("/api/resumes");
  const items = await r.json();
  const sig = JSON.stringify(items.map((x) => [x.job_id, x.generated, x.status]));
  if (sig === lastResumesSig) return;
  lastResumesSig = sig;
  $("#resumesList").innerHTML = items.length ? items.map((x) => `
    <div class="job">
      <div class="score" style="background:var(--panel2)">📄</div>
      <div class="info">
        <div class="title">${esc(x.title)}</div>
        <div class="co">${esc(x.company)} · generated ${esc(x.generated)} · job status: ${esc(x.status)}</div>
      </div>
      <div class="actions">
        <button onclick="openDrawer('Resume — ${esc(x.title)}', '<iframe src=\\'/api/file?path=${encodeURIComponent(x.pdf)}\\'></iframe>')">preview</button>
        <a href="/api/file?path=${encodeURIComponent(x.pdf)}" target="_blank"><button>open ↗</button></a>
        ${x.confirmation ? `<button onclick="openDrawer('Confirmation', '<img src=\\'/api/file?path=${encodeURIComponent(x.confirmation)}\\'>')">confirmation</button>` : ""}
      </div>
    </div>`).join("")
    : `<div class="empty"><h3>No resumes generated yet</h3><p>Approve a job and the tailored PDF will appear here.</p></div>`;
}

/* ------------------------------------------------------------------ tasks */
function renderTasks() {
  const pauseBtn = $("#pauseBtn");
  pauseBtn.textContent = STATE.paused ? "▶ Resume queue" : "⏸ Pause queue";
  pauseBtn.classList.toggle("danger", !STATE.paused);
  pauseBtn.classList.toggle("good", !!STATE.paused);

  const tasks = [...STATE.tasks].reverse();
  $("#tasksList").innerHTML = tasks.length ? tasks.map((t) => `
    <div class="task">
      <div class="dot ${esc(t.status)}"></div>
      <b>${esc(t.kind)}</b> ${esc(t.job_id || "")}
      <span>${esc(t.status)}</span>
      <button onclick="showLog('${esc(t.id)}','${esc(t.kind)}')">log</button>
      ${["queued", "running"].includes(t.status)
        ? `<button class="danger" onclick="cancelTask('${esc(t.id)}')">✕ cancel</button>` : ""}
      <span class="when">${esc(t.finished || t.started || t.created)}</span>
    </div>`).join("")
    : `<div class="empty"><h3>No activity yet</h3></div>`;
}

$("#pauseBtn").onclick = async () => {
  await fetch(STATE.paused ? "/api/queue/resume" : "/api/queue/pause", { method: "POST" });
  refresh();
};

async function cancelTask(id) {
  await fetch(`/api/tasks/${id}/cancel`, { method: "POST" });
  refresh();
}

function showLog(id, kind) {
  openDrawer(`Log — ${kind}`, `<pre id="logBody">loading…</pre>`);
  fetch(`/api/tasks/${id}/log`).then((r) => r.text())
    .then((t) => { $("#logBody").textContent = t || "(empty)"; });
}

/* ----------------------------------------------------------------- search */
$("#findJobsBtn").onclick = async () => {
  $("#findJobsBtn").disabled = true;
  $("#findJobsBtn").textContent = "⏳ searching…";
  await fetch("/api/search", { method: "POST" });
  setTimeout(() => {
    $("#findJobsBtn").disabled = false;
    $("#findJobsBtn").textContent = "🔍 Find Jobs";
  }, 4000);
  refresh();
};

/* ---------------------------------------------------------------- profile */
async function loadProfile() {
  const f = $("#profileFile").value;
  const r = await fetch(`/api/profile?file=${f}`);
  $("#profileEditor").value = await r.text();
}
$("#profileFile").onchange = loadProfile;
$("#saveProfileBtn").onclick = async () => {
  await fetch("/api/profile", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file: $("#profileFile").value, content: $("#profileEditor").value }),
  });
  $("#profileSavedMsg").classList.remove("hidden");
  setTimeout(() => $("#profileSavedMsg").classList.add("hidden"), 1800);
};

/* ------------------------------------------------------------- tabs/drawer */
document.querySelectorAll(".tab").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tabpane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "profile") loadProfile();
  };
});
$("#statusFilter").onchange = renderJobs;
$("#searchBox").oninput = renderJobs;

function openDrawer(title, html) {
  $("#drawerTitle").textContent = title;
  $("#drawerBody").innerHTML = html;
  $("#drawer").classList.remove("hidden");
  $("#overlay").classList.remove("hidden");
}
$("#drawerClose").onclick = $("#overlay").onclick = () => {
  $("#drawer").classList.add("hidden");
  $("#overlay").classList.add("hidden");
};
