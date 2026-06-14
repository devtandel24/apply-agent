import browser

def test_missing_binary_raises(monkeypatch):
    monkeypatch.setattr(browser.shutil, "which", lambda _: None)
    try:
        browser.snapshot()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "agent-browser" in str(e)

def test_snapshot_builds_compact_interactive_argv(monkeypatch):
    calls = {}
    monkeypatch.setattr(browser.shutil, "which", lambda _: "/usr/bin/agent-browser")
    monkeypatch.setattr(browser, "_run", lambda argv: calls.setdefault("argv", argv) or "ok")
    browser.snapshot()
    assert calls["argv"][:2] == ["snapshot", "-i"]
    assert "-c" in calls["argv"]

def test_fill_form_uses_batch(monkeypatch):
    calls = {}
    monkeypatch.setattr(browser.shutil, "which", lambda _: "/usr/bin/agent-browser")
    monkeypatch.setattr(browser, "_run", lambda argv: calls.setdefault("argv", argv) or "ok")
    browser.fill_form({"@e1": "test@example.com", "@e2": "Alex Doe"})
    assert calls["argv"][0] == "batch"
    joined = " ".join(calls["argv"])
    assert "test@example.com" in joined and "Alex Doe" in joined
