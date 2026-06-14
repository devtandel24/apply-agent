"""Extract structured must-have signals from a job description once, at ingest.

Pure function: text -> dict. No model, no I/O. Downstream scoring/tailoring read
this small dict instead of re-reading the full description (token savings).
"""
import re

SKILLS = [
    "python", "sql", "snowflake", "aws", "gcp", "azure", "airflow", "etl",
    "machine learning", "pytorch", "tensorflow", "scikit", "nlp", "kafka",
    "postgresql", "redis", "power bi", "tableau", "predictive", "statistics",
    "data pipeline", "recommendation", "xgboost", "deep learning", "llm",
    "genai", "generative ai", "rag", "agent", "mlops", "docker", "kubernetes",
    "ci/cd", "s3", "ec2", "data warehouse", "spark", "dbt", "fastapi",
]
NO_SPONSOR = re.compile(
    r"(no\s+(visa\s+)?sponsorship|not\s+(provide|offer|sponsor)[^.]{0,40}sponsorship|"
    r"unable\s+to\s+sponsor|cannot\s+sponsor|will\s+not\s+sponsor|"
    r"sponsorship\s+is\s+not\s+available|us\s+citizen(?:ship)?\s+(?:is\s+)?required|"
    r"must\s+be\s+a\s+u\.?s\.?\s+citizen|citizens?\s+(?:or\s+permanent\s+residents?\s+)?only)",
    re.I)
CLEARANCE = re.compile(r"security clearance|ts/sci|top secret|secret clearance|public trust", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|head|vp|architect)\b", re.I)
YEARS = re.compile(r"(\d+)\s*\+?\s*(?:or more\s*)?years?", re.I)


def years_required(text: str) -> int:
    best = 0
    for m in YEARS.finditer(text):
        n = int(m.group(1))
        if 0 < n <= 20:
            ctx = text[max(0, m.start() - 80): m.end() + 80].lower()
            if "experience" in ctx:
                best = max(best, n)
    return best


def extract_requirements(text: str) -> dict:
    low = text.lower()
    return {
        "skills": [s for s in SKILLS if s in low],
        "years_required": years_required(text),
        "no_sponsorship": bool(NO_SPONSOR.search(text)),
        "clearance": bool(CLEARANCE.search(text)),
        "senior": bool(SENIOR.search(text)),
    }
