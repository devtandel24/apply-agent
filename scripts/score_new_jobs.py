#!/usr/bin/env python3
"""Score every status=='new' row in data/jobs.csv against the candidate's profile.

Applies the job-search skill rubric mechanically and consistently:
  must-have skills overlap (40%), title/seniority fit (20%), domain fit (10%),
  salary vs the configured floor (10%), remote/location (10%), sponsorship risk (10%).
Caps sponsor_risk=YES jobs at C. Hard disqualifiers -> F.
Writes score + status='scored' + a one-line notes rationale back to the CSV.
"""
import csv, os, re, sys

CSV = "data/jobs.csv"
FLOOR = 90000

# --- skill vocabulary, grouped by domain ---
SKILLS = {
    "aws": ["aws", "s3", "cloudfront", " rds", "aurora", "ec2", "lambda", "cloudwatch",
            "guardduty", "cloudtrail", " kms", "secrets manager", "eventbridge",
            "api gateway", " ses ", "elasticache", "waf", "vpc"],
    "devops": ["docker", "kubernetes", "k8s", "ci/cd", "cicd", "jenkins", "terraform",
               "github actions", "infrastructure as code", "iac", "devops", "sre",
               "observability", "monitoring", "deployment"],
    "genai": ["claude", "openai", "anthropic", "llm", "large language model", "generative ai",
              "genai", "gen ai", "agentic", " agent", "rag", "retrieval augmented",
              "langchain", "langgraph", "prompt engineering", "prompt-engineering",
              "pinecone", "pgvector", "vector database", "vector db", "embeddings",
              "fine-tuning", "fine tuning", "mcp", "copilot", "cursor"],
    "ml": ["machine learning", " ml ", "ml/", "/ml", "pytorch", "tensorflow", "scikit",
           "sklearn", "hugging face", "huggingface", "transformers", "nlp",
           "natural language", "predictive model", "xgboost", "deep learning",
           "mlflow", "mlops", "model serving", "feature engineering", "data science"],
    "fullstack": ["next.js", "nextjs", "react", "typescript", "javascript", "node.js",
                  "nodejs", "node ", "graphql", "tailwind", "rest api", "restful",
                  "front-end", "frontend", "full-stack", "full stack", "fullstack"],
    "data": ["python", " sql", "etl", "airflow", "kafka", "snowflake", "postgres",
             "postgresql", "mongodb", "redis", "data pipeline", "data warehouse",
             "data engineering", "spark", "dbt"],
}

# Targeted titles, split by how directly they hit the sweet spot.
# Strong: AI/ML/GenAI/agentic/cloud/devops/data — her named target domains.
STRONG_TITLE = ["ai engineer", "ml engineer", "machine learning", "genai", "gen ai",
                "generative ai", "agentic", "data scientist", "mlops", "devops",
                "cloud engineer", "data engineer", "forward deployed", "ai/ml",
                "applied ai", "applied scientist", "ai developer", "ai solutions",
                "llm engineer", "ai/ml engineer", "full-stack ai", "full stack ai"]
# Generic: adjacent but broad — credit, but not enough alone for an A.
GENERIC_TITLE = ["software engineer", "full stack", "full-stack", "fullstack",
                 "platform engineer", "solutions engineer", "backend engineer",
                 "frontend engineer", "developer", "sde"]

SENIOR = ["senior", "sr.", "sr ", "staff", "principal", "lead ", " lead", "director",
          "vp ", "vice president", "head of", "manager", "architect", "distinguished",
          "fellow"]

# Hard disqualifiers
CLEARANCE = ["security clearance", "ts/sci", "top secret", "secret clearance",
             "active clearance", "polygraph", "ts /sci", "dod clearance",
             "must be a u.s. citizen", "us citizenship", "u.s. citizenship",
             "citizenship is required", "citizen or green card", "must be us citizen"]
NO_SPONSOR = ["no sponsorship", "not provide sponsorship", "unable to sponsor",
              "will not sponsor", "cannot sponsor", "without sponsorship",
              "not offer sponsorship", "no visa sponsorship", "do not sponsor",
              "without the need for sponsorship", "not require sponsorship now or in the future",
              "not require visa sponsorship", "sponsorship is not available",
              "are not able to sponsor", "we do not provide visa"]

OFFDOMAIN = ["propulsion", "mechanical engineer", "telecommunications", "5g", "6g",
             "civil engineer", "nurse", "physician", "accountant", "salesperson",
             "account manager", "recruiter", "electrical engineer", "hvac",
             "aerospace", "spacecraft", "warehouse", "driver", "technician",
             "phlebotom", "dental", "pharmacist", "teacher ", "barista", "chef"]


def years_required(text):
    m = re.findall(r"(\d{1,2})\+?\s*(?:-\s*\d{1,2}\s*)?years", text)
    yrs = [int(x) for x in m if int(x) <= 25]
    return max(yrs) if yrs else 0


def skill_overlap(text):
    matched = {}
    for dom, kws in SKILLS.items():
        hits = sum(1 for kw in kws if kw in text)
        if hits:
            matched[dom] = hits
    # total distinct domains touched + weighted hit count
    return matched


def score_job(row, text):
    t = text.lower()
    title = row["title"].lower()
    reasons = []

    # ---- Hard disqualifiers -> F ----
    if any(c in t for c in CLEARANCE):
        return "F", "Disqualified: security clearance / US citizenship required."
    if any(s in t for s in NO_SPONSOR):
        return "F", "Disqualified: explicit no-visa-sponsorship language."

    yrs = years_required(t)
    is_senior = any(s in title for s in SENIOR)
    off = [o for o in OFFDOMAIN if o in title]

    # Off-domain title with no AI/ML/cloud relevance
    matched = skill_overlap(t)
    core_domains = {"aws", "devops", "genai", "ml", "fullstack", "data"} & set(matched)
    strong_domains = sum(1 for d in matched if matched[d] >= 2)

    if off and not ({"genai", "ml", "aws"} & set(matched)):
        return "F", f"Disqualified: off-domain role ({off[0]})."

    # Very senior + high YoE hard requirement
    if (is_senior and yrs >= 8) or yrs >= 10:
        return "F", f"Disqualified: {yrs}+ yrs / senior-staff level beyond ~2 yrs experience."

    # ---- Weighted 0-100 score ----
    # must-have skills overlap (40): weight her PRIMARY domains far above
    # generic python/sql/react presence.
    primary = {"genai", "ml", "aws", "devops"} & set(matched)
    secondary = {"fullstack", "data"} & set(matched)
    primary_depth = sum(min(matched[d], 3) for d in primary)  # 0..12
    skill_pts = min(40, primary_depth * 3 + len(secondary) * 3)
    if not primary:
        skill_pts = min(skill_pts, 8)  # no AI/ML/cloud signal -> weak match

    # title/seniority fit (20)
    strong_title = any(tt in title for tt in STRONG_TITLE)
    generic_title = any(tt in title for tt in GENERIC_TITLE)
    if strong_title and not is_senior:
        title_pts = 20
    elif strong_title and is_senior:
        title_pts = 12
    elif generic_title and not is_senior:
        title_pts = 12
    elif generic_title and is_senior:
        title_pts = 7
    elif core_domains:
        title_pts = 6
    else:
        title_pts = 1

    # domain fit (10)
    domain_pts = 10 if primary else (4 if core_domains else 0)

    # salary vs floor (10)
    smin = row.get("salary_min", "")
    smax = row.get("salary_max", "")
    try:
        smin_v = float(smin) if smin and smin != "nan" else None
    except ValueError:
        smin_v = None
    try:
        smax_v = float(smax) if smax and smax != "nan" else None
    except ValueError:
        smax_v = None
    if smax_v is not None and smax_v < FLOOR:
        sal_pts = 0
        reasons.append(f"salary tops out ${int(smax_v/1000)}k < ${FLOOR//1000}k floor")
    elif smin_v is not None and smin_v >= FLOOR:
        sal_pts = 10
    elif smax_v is not None and smax_v >= FLOOR:
        sal_pts = 8  # range straddles floor
    else:
        sal_pts = 6  # unknown salary -> neutral-ish

    # remote/location (10)
    remote_pts = 10 if str(row.get("remote", "")).lower() in ("true", "1", "yes") else 5

    # sponsorship risk (10)
    spons_yes = row.get("sponsor_risk", "") == "YES"
    spons_pts = 0 if spons_yes else 10

    total = skill_pts + title_pts + domain_pts + sal_pts + remote_pts + spons_pts

    # YoE soft penalty
    if 5 <= yrs <= 7:
        total -= 8
        reasons.append(f"{yrs}+ yrs preferred")
    if is_senior:
        reasons.append("senior-titled")

    # ---- Map to letter ----
    if total >= 82:
        letter = "A"
    elif total >= 68:
        letter = "B"
    elif total >= 52:
        letter = "C"
    elif total >= 36:
        letter = "D"
    else:
        letter = "F"

    # sponsor risk caps at C
    if spons_yes and letter in ("A", "B"):
        letter = "C"
        reasons.insert(0, "sponsor_risk=YES (capped at C)")

    dom_str = "/".join(sorted(core_domains)) or "weak skill overlap"
    note = f"[{total}] {dom_str}; " + ("; ".join(reasons) if reasons else "title & skills fit")
    return letter, note[:240]


def main():
    rows = list(csv.DictReader(open(CSV)))
    fields = rows[0].keys()
    from collections import Counter
    counts = Counter()
    n = 0
    for r in rows:
        if r["status"] not in ("new", "scored"):
            continue
        df = r["description_file"]
        text = ""
        if df and os.path.exists(df):
            text = open(df, encoding="utf-8", errors="ignore").read()
        letter, note = score_job(r, text)
        r["score"] = letter
        r["status"] = "scored"
        r["notes"] = note
        counts[letter] += 1
        n += 1
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        w.writerows(rows)
    print(f"Scored {n} new jobs.")
    for g in "ABCDF":
        print(f"  {g}: {counts.get(g,0)}")
    print("SUMMARY:", ", ".join(f"{g}={counts.get(g,0)}" for g in "ABCDF"))


if __name__ == "__main__":
    main()
