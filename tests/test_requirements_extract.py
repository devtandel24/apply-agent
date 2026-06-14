from requirements_extract import extract_requirements

def test_extracts_skills_seniority_and_sponsorship():
    jd = """
    Senior Machine Learning Engineer. We need strong Python and AWS,
    experience with PyTorch and Docker. 5+ years experience required.
    This role does not offer visa sponsorship. Remote within the US.
    """
    req = extract_requirements(jd)
    assert "python" in req["skills"]
    assert "aws" in req["skills"]
    assert "pytorch" in req["skills"]
    assert req["years_required"] == 5
    assert req["no_sponsorship"] is True
    assert req["senior"] is True

def test_clean_entry_level_role():
    jd = "AI Engineer. Python, LLM, RAG. Visa sponsorship available."
    req = extract_requirements(jd)
    assert req["no_sponsorship"] is False
    assert req["senior"] is False
    assert req["years_required"] == 0
    assert "llm" in req["skills"]
