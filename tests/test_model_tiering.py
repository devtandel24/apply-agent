import importlib, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

def test_model_for_kinds(monkeypatch):
    monkeypatch.delenv("SEARCH_MODEL", raising=False)
    monkeypatch.delenv("TAILOR_MODEL", raising=False)
    monkeypatch.delenv("APPLY_MODEL", raising=False)
    import server
    importlib.reload(server)
    assert server.model_for("search") == "haiku"
    assert server.model_for("tailor") == "sonnet"
    assert server.model_for("apply") == "sonnet"

def test_tailor_model_env_override(monkeypatch):
    monkeypatch.setenv("TAILOR_MODEL", "opus")
    import server
    importlib.reload(server)
    assert server.model_for("tailor") == "opus"
