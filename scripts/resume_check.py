"""Model-independent resume quality checks: keyword coverage + ATS lint.

ATS-friendliness is mostly structure, not model intelligence. These run in the
tailor flow as objective gates before a resume is accepted.
"""
import re


def keyword_coverage(resume_text: str, must_haves: list[str]):
    """Return (coverage_fraction, sorted_missing_keywords)."""
    low = resume_text.lower()
    if not must_haves:
        return 1.0, []
    present = [k for k in must_haves if k.lower() in low]
    missing = sorted(k for k in must_haves if k.lower() not in low)
    return len(present) / len(must_haves), missing


def ats_lint(html: str) -> list[str]:
    """Return a list of ATS problems; empty means clean."""
    issues = []
    if re.search(r"\{\{.*?\}\}", html):
        issues.append("leftover {{placeholder}} found")
    if re.search(r"<table", html, re.I):
        issues.append("layout <table> found (breaks ATS parsing)")
    if re.search(r"<img\b", html, re.I):
        issues.append("<img> found (text-in-image is unreadable to ATS)")
    return issues
