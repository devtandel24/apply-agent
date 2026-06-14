import json, importlib
from pathlib import Path

def test_write_req_json_helper(tmp_path):
    import search_jobs
    importlib.reload(search_jobs)
    out = tmp_path / "acme.req.json"
    search_jobs.write_req_json(out, "Python and AWS. 6+ years experience. No sponsorship.")
    data = json.loads(out.read_text())
    assert "python" in data["skills"]
    assert data["no_sponsorship"] is True
    assert data["years_required"] == 6
