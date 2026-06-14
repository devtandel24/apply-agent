"""Token-cheap browser control via the agent-browser CLI (Rust daemon over CDP).

Skills call these functions through Bash instead of Playwright MCP. snapshot()
returns a compact, interactive-only accessibility tree with refs (@e1, @e2); a
whole form is filled in ONE `batch` invocation. Backend (Chrome now, Lightpanda
later) is hidden behind this wrapper.
"""
import json  # reserved — snapshot JSON parsing planned
import shutil
import subprocess

BIN = "agent-browser"


def _require():
    if shutil.which(BIN) is None:
        raise RuntimeError(
            "agent-browser not found. Install it (see README) — it is a free local "
            "binary; no subscription needed.")


def _run(argv):
    _require()
    out = subprocess.run([BIN, *argv], capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"agent-browser {argv[0]} failed: {out.stderr.strip()}")
    return out.stdout


def navigate(url):
    return _run(["navigate", url])


def snapshot(selector=None, depth=None):
    """Compact, interactive-only accessibility tree with refs."""
    argv = ["snapshot", "-i", "-c"]
    if depth is not None:
        argv += ["-d", str(depth)]
    if selector:
        argv += ["-s", selector]
    return _run(argv)


def fill_form(fields: dict):
    """Fill every {ref: value} in a single batch call."""
    argv = ["batch"]
    for ref, value in fields.items():
        argv += ["fill", ref, value]
    return _run(argv)


def click(ref):
    return _run(["click", ref])


def find_click(role, name):
    return _run(["find", "role", role, "click", "--name", name])


def screenshot(path):
    return _run(["screenshot", "--path", str(path)])
