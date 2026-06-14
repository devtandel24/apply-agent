import importlib


def test_lint_html_returns_issue_list(tmp_path):
    import make_pdf
    importlib.reload(make_pdf)
    bad = tmp_path / "resume.html"
    bad.write_text("<table></table> {{x}}")
    issues = make_pdf.lint_html(bad)
    assert issues  # non-empty -> would block
