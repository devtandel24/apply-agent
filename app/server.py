"""Career Agent UI — local web app over the file-based pipeline.

Run:  .venv/bin/python app/server.py     →  http://localhost:8377

No database. State lives in the same files Claude Code uses:
  data/jobs.csv            tracker (single source of truth)
  data/ui/approvals.json   pending questions from the agent to the human
  data/ui/tasks.json       background task queue + statuses
  output/<job-id>/         resumes, confirmations
AI work is delegated to the Claude Code CLI (`claude -p`) per task; when the
agent needs the human it blocks on scripts/ui_bridge.py, whose requests this
server surfaces in the UI.
"""
import csv, json, os, shlex, subprocess, threading, time, uuid, webbrowser

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_CSV = os.path.join(ROOT, "data", "jobs.csv")
UI_DIR = os.path.join(ROOT, "data", "ui")
APPROVALS = os.path.join(UI_DIR, "approvals.json")
TASKS = os.path.join(UI_DIR, "tasks.json")
LOGS_DIR = os.path.join(UI_DIR, "logs")
PY = os.path.join(ROOT, ".venv", "bin", "python")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
PORT = int(os.environ.get("CAREER_UI_PORT", "8377"))
AUTO_APPLY = os.environ.get("CAREER_AUTO_APPLY", "1") == "1"  # tailor done → apply queued


def model_for(kind):
    return {
        "search": os.environ.get("SEARCH_MODEL", "haiku"),
        "tailor": os.environ.get("TAILOR_MODEL", "sonnet"),
        "apply": os.environ.get("APPLY_MODEL", "sonnet"),
    }.get(kind, "sonnet")

os.makedirs(LOGS_DIR, exist_ok=True)
_lock = threading.Lock()

# ---------------------------------------------------------------- file utils

def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def read_jobs():
    if not os.path.exists(JOBS_CSV):
        return []
    with open(JOBS_CSV) as f:
        return list(csv.DictReader(f))


def write_jobs(rows):
    if not rows:
        return
    with open(JOBS_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def mac_notify(title, body=""):
    try:
        script = 'display notification "{}" with title "{}" sound name "Glass"'.format(
            body.replace('"', "'")[:180], title.replace('"', "'")[:80])
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except Exception:
        pass

# ------------------------------------------------------------- agent prompts

UI_MODE_RULES = """UI MODE — you are running headless behind a local web UI; there is no chat user.
NEVER use AskUserQuestion or ask questions in your output. Instead, whenever the
skill requires asking/confirming with the user (unknown form answers, the mandatory
submit gate, anything else), run:
  .venv/bin/python scripts/ui_bridge.py ask --job-id <id> --type <question|submit_gate> \
    --title "<short question>" --body "<full context the user needs>" --options "A,B"
and use its stdout as the user's answer (it blocks until they answer in the UI; options
are comma-separated buttons, omit --options for free text). If it prints nothing and
exits non-zero, treat it as 'user unavailable' and abort the current job safely.
All integrity rules from CLAUDE.md still apply: never fabricate, sponsorship = Yes, always."""

GAP_CHECK_RULES = """RESUME GAP CHECK (do this BEFORE writing the resume):
1. Extract the job's must-have requirements/skills from its description file.
2. Compare against profile/master_resume.md. Collect requirements with NO evidence
   in the master resume (skills, tools, domains — not years/degrees).
3. If any, write them to /tmp/gaps_<jobid>.json as
   [{"requirement": "...", "context": "<why the JD needs it>"}, ...] and run:
   .venv/bin/python scripts/ui_bridge.py gaps --job-id <id> --questions-file /tmp/gaps_<jobid>.json
4. Its stdout is JSON: [{"requirement", "have_it", "detail"}]. For every item with
   have_it=true, append the fact (with the user's detail, reworded cleanly) to the
   right section of profile/master_resume.md — these are now confirmed facts you may
   use on this and future resumes. Items with have_it=false must NOT appear on the resume.
5. Then proceed with the tailor skill as written (resume.html → PDF → tracker)."""


def task_prompt(kind, job_id=None):
    if kind == "search":
        return ("Run the job-search skill steps 1 and 2 only: discover new jobs and score "
                "every `new` row in data/jobs.csv, updating score/status/notes columns. "
                "Do NOT present a shortlist or ask for approval — the UI handles approval. "
                "Finish by printing a one-line summary of counts per score.\n" + UI_MODE_RULES)
    if kind == "tailor":
        return (f"Run the tailor skill for the job with id `{job_id}` in data/jobs.csv "
                "(status `approved`, or `tailored` for a re-tailor — regenerate from the "
                f"CURRENT master resume).\n{GAP_CHECK_RULES}\n{UI_MODE_RULES}")
    if kind == "apply":
        return (f"Run the apply skill for the job with id `{job_id}` in data/jobs.csv "
                "(status should be `tailored`). Drive the browser via `scripts/browser.py` (agent-browser): snapshot() to get refs, fill_form() to batch-fill, click/find_click to act. "
                "The mandatory submit gate MUST go through ui_bridge with --type submit_gate, "
                "--body containing a full summary of every answer you filled, and options "
                "'Submit,Cancel'. Only click the final Submit on 'Submit'.\n" + UI_MODE_RULES)
    raise ValueError(kind)

# --------------------------------------------------------------- task worker

PAUSE_FLAG = os.path.join(UI_DIR, "paused")


def queue_paused():
    return os.path.exists(PAUSE_FLAG)


def _spawn_claude(prompt, log_path, model="sonnet"):
    with open(log_path, "w") as log:
        return subprocess.Popen(
            [CLAUDE_BIN, "-p", prompt, "--model", model,
             "--permission-mode", "bypassPermissions"],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env={**os.environ, "CAREER_UI_MODE": "1"},
            start_new_session=True,  # own process group so cancel can kill the whole tree
        )


def worker():
    """Serial task runner — one agent task at a time (one application at a time)."""
    while True:
        time.sleep(1.5)
        if queue_paused():
            continue
        with _lock:
            tasks = _read_json(TASKS, [])
            running = [t for t in tasks if t["status"] == "running"]
            queued = [t for t in tasks if t["status"] == "queued"]
            if running or not queued:
                continue
            task = queued[0]
            task["status"] = "running"
            task["started"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _write_json(TASKS, tasks)

        log_path = os.path.join(LOGS_DIR, task["id"] + ".log")
        try:
            proc = _spawn_claude(task_prompt(task["kind"], task.get("job_id")),
                                 log_path, model=model_for(task["kind"]))
            with _lock:  # record pid so /cancel can kill it
                tasks = _read_json(TASKS, [])
                for t in tasks:
                    if t["id"] == task["id"]:
                        t["pid"] = proc.pid
                _write_json(TASKS, tasks)
            rc = proc.wait(timeout=3 * 3600)
        except Exception as e:
            rc = -1
            with open(log_path, "a") as f:
                f.write(f"\n[server] task crashed: {e}\n")

        with _lock:
            tasks = _read_json(TASKS, [])
            for t in tasks:
                # don't overwrite a user cancellation
                if t["id"] == task["id"] and t["status"] == "running":
                    t["status"] = "done" if rc == 0 else "failed"
                    t["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _write_json(TASKS, tasks)
            task = next(t for t in tasks if t["id"] == task["id"])
        if task["status"] == "cancelled":
            continue  # user killed it — no notification, no auto-apply
        label = f"{task['kind']} {task.get('job_id') or ''}".strip()
        mac_notify("Career Agent", f"Task {label}: {'done' if rc == 0 else 'FAILED — check Activity tab'}")

        # AUTO-APPLY: once a resume is tailored, queue the application right away.
        # The mandatory submit gate in the UI still protects the final click.
        if AUTO_APPLY and task["kind"] == "tailor" and rc == 0:
            row = next((r for r in read_jobs() if r["id"] == task.get("job_id")), None)
            if row and row["status"] == "tailored":
                enqueue("apply", row["id"])
                mac_notify("Career Agent", f"Resume ready — applying to {row['company']} next. "
                           "Stay reachable for the submit gate.")


def enqueue(kind, job_id=None):
    with _lock:
        tasks = _read_json(TASKS, [])
        # avoid duplicate queued/running task for same kind+job
        for t in tasks:
            if t["kind"] == kind and t.get("job_id") == job_id and t["status"] in ("queued", "running"):
                return t["id"]
        task = {"id": uuid.uuid4().hex[:10], "kind": kind, "job_id": job_id,
                "status": "queued", "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        tasks.append(task)
        _write_json(TASKS, tasks)
        return task["id"]

# ----------------------------------------------------------------------- app

app = FastAPI(title="Career Agent UI")


@app.get("/api/state")
def state():
    return {
        "jobs": read_jobs(),
        "approvals": _read_json(APPROVALS, []),
        "tasks": _read_json(TASKS, []),
        "paused": queue_paused(),
    }


@app.post("/api/queue/pause")
def pause_queue():
    open(PAUSE_FLAG, "w").close()
    return {"paused": True}


@app.post("/api/queue/resume")
def resume_queue():
    if os.path.exists(PAUSE_FLAG):
        os.remove(PAUSE_FLAG)
    return {"paused": False}


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    import signal
    with _lock:
        tasks = _read_json(TASKS, [])
        for t in tasks:
            if t["id"] == task_id and t["status"] in ("queued", "running"):
                if t["status"] == "running" and t.get("pid"):
                    try:
                        os.killpg(os.getpgid(t["pid"]), signal.SIGTERM)
                    except (ProcessLookupError, PermissionError):
                        pass
                t["status"] = "cancelled"
                t["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
                _write_json(TASKS, tasks)
                return {"ok": True}
    raise HTTPException(404, "task not found or already finished")


class SearchReq(BaseModel):
    pass


@app.post("/api/search")
def start_search():
    return {"task": enqueue("search")}


class ApproveReq(BaseModel):
    ids: list[str]


@app.post("/api/jobs/approve")
def approve_jobs(req: ApproveReq):
    rows = read_jobs()
    hit = []
    for r in rows:
        if r["id"] in req.ids and r["status"] in ("scored", "new"):
            r["status"] = "approved"
            hit.append(r["id"])
    write_jobs(rows)
    for jid in hit:
        enqueue("tailor", jid)
    return {"approved": hit}


@app.post("/api/jobs/{job_id}/reject")
def reject_job(job_id: str):
    rows = read_jobs()
    for r in rows:
        if r["id"] == job_id:
            r["status"] = "rejected"
    write_jobs(rows)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/apply")
def apply_job(job_id: str):
    rows = read_jobs()
    row = next((r for r in rows if r["id"] == job_id), None)
    if not row:
        raise HTTPException(404, "job not found")
    if row["status"] != "tailored":
        raise HTTPException(400, f"job status is {row['status']}, needs 'tailored'")
    return {"task": enqueue("apply", job_id)}


@app.post("/api/jobs/{job_id}/tailor")
def tailor_job(job_id: str):
    return {"task": enqueue("tailor", job_id)}


class AnswerReq(BaseModel):
    answer: object  # string for ask, list for gap_check


@app.post("/api/approvals/{approval_id}")
def answer_approval(approval_id: str, req: AnswerReq):
    with _lock:
        items = _read_json(APPROVALS, [])
        for it in items:
            if it["id"] == approval_id and it["status"] == "pending":
                it["status"] = "answered"
                it["answer"] = req.answer
                _write_json(APPROVALS, items)
                return {"ok": True}
    raise HTTPException(404, "approval not found or already answered")


@app.get("/api/resumes")
def list_resumes():
    """Every generated artifact in output/, joined to its job row."""
    jobs = {j["id"]: j for j in read_jobs()}
    out = []
    outdir = os.path.join(ROOT, "output")
    if os.path.isdir(outdir):
        for d in sorted(os.listdir(outdir)):
            pdf = os.path.join(outdir, d, "resume.pdf")
            if not os.path.exists(pdf):
                continue
            j = jobs.get(d, {})
            out.append({
                "job_id": d,
                "title": j.get("title", d),
                "company": j.get("company", ""),
                "status": j.get("status", ""),
                "pdf": f"output/{d}/resume.pdf",
                "confirmation": f"output/{d}/confirmation.png"
                    if os.path.exists(os.path.join(outdir, d, "confirmation.png")) else None,
                "generated": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(pdf))),
            })
    out.sort(key=lambda r: r["generated"], reverse=True)
    return out


ALLOWED_STATUS = {"applied", "interviewing", "offer", "rejected", "no-response", "withdrawn"}


class StatusReq(BaseModel):
    status: str
    note: str = ""


@app.post("/api/jobs/{job_id}/status")
def set_status(job_id: str, req: StatusReq):
    if req.status not in ALLOWED_STATUS:
        raise HTTPException(400, f"status must be one of {sorted(ALLOWED_STATUS)}")
    rows = read_jobs()
    for r in rows:
        if r["id"] == job_id:
            r["status"] = req.status
            if req.status == "applied" and not r.get("applied_date"):
                r["applied_date"] = time.strftime("%Y-%m-%d")
            if req.note:
                r["notes"] = (r.get("notes", "") + " | " + req.note).strip(" |")
            write_jobs(rows)
            return {"ok": True}
    raise HTTPException(404, "job not found")


SAFE_PREFIXES = ("output/", "data/descriptions/", "profile/", "data/ui/logs/")


@app.get("/api/file")
def get_file(path: str):
    norm = os.path.normpath(path).lstrip("/")
    if not norm.startswith(SAFE_PREFIXES):
        raise HTTPException(403, "path not allowed")
    full = os.path.join(ROOT, norm)
    if not os.path.exists(full):
        raise HTTPException(404, "not found")
    return FileResponse(full)


class ProfileReq(BaseModel):
    file: str  # "master_resume.md" | "profile.yaml"
    content: str


@app.get("/api/profile")
def get_profile(file: str):
    if file not in ("master_resume.md", "profile.yaml"):
        raise HTTPException(403, "not allowed")
    full = os.path.join(ROOT, "profile", file)
    return PlainTextResponse(open(full).read())


@app.post("/api/profile")
def save_profile(req: ProfileReq):
    if req.file not in ("master_resume.md", "profile.yaml"):
        raise HTTPException(403, "not allowed")
    full = os.path.join(ROOT, "profile", req.file)
    with open(full, "w") as f:
        f.write(req.content)
    return {"ok": True}


@app.get("/api/tasks/{task_id}/log")
def task_log(task_id: str):
    path = os.path.join(LOGS_DIR, task_id + ".log")
    if not os.path.exists(path):
        return PlainTextResponse("")
    with open(path) as f:
        data = f.read()
    return PlainTextResponse(data[-20000:])


app.mount("/", StaticFiles(directory=os.path.join(ROOT, "app", "static"), html=True))


def _recover_stale_tasks():
    """Tasks left 'running' by a previous server process can never finish — mark
    them failed so they don't block the serial queue forever."""
    tasks = _read_json(TASKS, [])
    changed = False
    for t in tasks:
        if t["status"] == "running":
            t["status"] = "failed"
            t["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            changed = True
    if changed:
        _write_json(TASKS, tasks)


def main():
    _recover_stale_tasks()
    threading.Thread(target=worker, daemon=True).start()
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
