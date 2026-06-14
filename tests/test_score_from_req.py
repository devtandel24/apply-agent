from score_jobs import score_from_req

BASE = {"title": "Machine Learning Engineer", "remote": "True",
        "salary_min": "120000", "salary_max": "160000", "sponsor_risk": ""}

def test_clearance_is_disqualified():
    req = {"skills": ["python"], "years_required": 0, "no_sponsorship": False,
           "clearance": True, "senior": False}
    grade, _ = score_from_req(BASE, req)
    assert grade == "F"

def test_strong_match_is_A_or_B():
    req = {"skills": ["python", "aws", "pytorch", "llm", "rag", "docker",
                      "mlops", "machine learning", "agent", "sql"],
           "years_required": 2, "no_sponsorship": False,
           "clearance": False, "senior": False}
    grade, _ = score_from_req(BASE, req)
    assert grade in ("A", "B")

def test_senior_is_disqualified():
    req = {"skills": ["python"], "years_required": 0, "no_sponsorship": False,
           "clearance": False, "senior": True}
    grade, _ = score_from_req(BASE, req)
    assert grade == "F"
