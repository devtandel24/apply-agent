"""Bridge between headless agent tasks and the local UI.

The agent (running as `claude -p`) calls this script when it needs the human:
    .venv/bin/python scripts/ui_bridge.py ask \
        --job-id zillow-mle --type submit_gate \
        --title "Submit application to Zillow?" \
        --body "Summary of all answers..." \
        --options "Submit,Cancel"            # omit for free-text answer

It appends a request to data/ui/approvals.json, fires a macOS notification,
then blocks (polling the file) until the UI writes an answer. The chosen
option / typed text is printed to stdout so the agent can read it.

Other commands:
    notify --title ... --body ...      fire-and-forget macOS notification
    gaps --job-id X --questions-file f ask a batch of resume-gap questions
"""
import argparse, json, os, subprocess, sys, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPROVALS = os.path.join(ROOT, "data", "ui", "approvals.json")


def _load():
    if not os.path.exists(APPROVALS):
        return []
    try:
        with open(APPROVALS) as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def _save(items):
    tmp = APPROVALS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(items, f, indent=2)
    os.replace(tmp, APPROVALS)  # atomic


UI_URL = "http://localhost:" + os.environ.get("CAREER_UI_PORT", "8377")


def mac_notify(title, body, open_ui=False):
    try:
        script = 'display notification "{}" with title "{}" sound name "Glass"'.format(
            (body + " — answer at " + UI_URL).replace('"', "'")[:180],
            title.replace('"', "'")[:80])
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
        if open_ui:
            # bring the UI to the user: macOS notifications can't deep-link,
            # so open/focus the browser tab directly
            subprocess.run(["open", UI_URL], capture_output=True, timeout=10)
    except Exception:
        pass  # notifications are best-effort


def _find_match(items, job_id, rtype, title):
    """Agent Bash calls can time out and retry the same ask — reattach to the
    matching request instead of creating a duplicate card."""
    for it in reversed(items):
        if (it["job_id"] == job_id and it["type"] == rtype and it["title"] == title
                and it["status"] in ("pending", "answered") and not it.get("consumed")):
            return it
    return None


def ask(args):
    items = _load()
    match = _find_match(items, args.job_id or "", args.type, args.title)
    if match and match["status"] == "answered":
        match["consumed"] = True
        _save(items)
        print(match["answer"] if match["answer"] is not None else "")
        return 0
    if match:  # pending — reattach, don't duplicate
        req = match
    else:
        req = {
            "id": uuid.uuid4().hex[:10],
            "job_id": args.job_id or "",
            "type": args.type,
            "title": args.title,
            "body": args.body or "",
            "options": [o.strip() for o in args.options.split(",")] if args.options else [],
            "status": "pending",
            "answer": None,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        items.append(req)
        _save(items)
        mac_notify("Career Agent needs you", args.title, open_ui=True)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        time.sleep(2)
        items = _load()
        for it in items:
            if it["id"] == req["id"] and it["status"] == "answered":
                it["consumed"] = True
                _save(items)
                print(it["answer"] if it["answer"] is not None else "")
                return 0
    # timeout: leave the card pending — a retried ask will reattach to it
    print("TIMEOUT", file=sys.stderr)
    return 2


def gaps(args):
    """Ask a batch of yes/no+detail gap questions defined in a JSON file:
    [{"requirement": "Docker", "context": "JD asks for container deployment"}]
    Prints the answers as JSON: [{"requirement":..., "have_it": true, "detail": "..."}]
    """
    with open(args.questions_file) as f:
        questions = json.load(f)
    title = f"Resume gap check ({len(questions)} questions)"
    items = _load()
    match = _find_match(items, args.job_id or "", "gap_check", title)
    if match and match["status"] == "answered":
        match["consumed"] = True
        _save(items)
        print(json.dumps(match["answer"]))
        return 0
    if match:
        req = match
    else:
        req = {
            "id": uuid.uuid4().hex[:10],
            "job_id": args.job_id or "",
            "type": "gap_check",
            "title": title,
            "body": "The job asks for things not found on your master resume. "
                    "Mark anything you HAVE actually done and add a one-line detail.",
            "questions": questions,
            "options": [],
            "status": "pending",
            "answer": None,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        items.append(req)
        _save(items)
        mac_notify("Career Agent: resume gap check", f"{len(questions)} questions about your experience", open_ui=True)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        time.sleep(2)
        items = _load()
        for it in items:
            if it["id"] == req["id"] and it["status"] == "answered":
                it["consumed"] = True
                _save(items)
                print(json.dumps(it["answer"]))
                return 0
    print("TIMEOUT", file=sys.stderr)
    return 2


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask")
    a.add_argument("--job-id", default="")
    a.add_argument("--type", default="question",
                   choices=["question", "submit_gate", "shortlist", "info"])
    a.add_argument("--title", required=True)
    a.add_argument("--body", default="")
    a.add_argument("--options", default="")
    a.add_argument("--timeout", type=int, default=3600)

    g = sub.add_parser("gaps")
    g.add_argument("--job-id", default="")
    g.add_argument("--questions-file", required=True)
    g.add_argument("--timeout", type=int, default=3600)

    n = sub.add_parser("notify")
    n.add_argument("--title", required=True)
    n.add_argument("--body", default="")

    args = p.parse_args()
    if args.cmd == "ask":
        sys.exit(ask(args))
    if args.cmd == "gaps":
        sys.exit(gaps(args))
    if args.cmd == "notify":
        mac_notify(args.title, args.body)


if __name__ == "__main__":
    main()
