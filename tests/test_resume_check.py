from resume_check import keyword_coverage, ats_lint

def test_keyword_coverage():
    resume = "Built Python services on AWS using Docker and PyTorch."
    cov, missing = keyword_coverage(resume, ["python", "aws", "docker", "kafka"])
    assert abs(cov - 0.75) < 1e-6
    assert missing == ["kafka"]

def test_ats_lint_flags_placeholder_and_table():
    html = "<table><tr><td>Name</td></tr></table> {{linkedin}}"
    issues = ats_lint(html)
    assert any("placeholder" in i for i in issues)
    assert any("table" in i for i in issues)

def test_ats_lint_flags_image():
    issues = ats_lint('<img src="headshot.png"> <p>text</p>')
    assert any("image" in i for i in issues)

def test_ats_lint_clean_html_has_no_issues():
    html = "<h1>Alex Doe</h1><h2>Experience</h2><p>Real text here.</p>"
    assert ats_lint(html) == []
