"""Score `new` jobs in data/jobs.csv against the candidate's profile.

Heuristic first pass per .claude/skills/job-search scoring dimensions:
must-have skills overlap 40%, title/seniority 20%, domain 10%, salary 10%,
remote/location 10%, sponsorship risk 10%. Hard disqualifiers -> F.
Top-ranked jobs still get a human (agent) read before presenting.
"""
import csv, json, re, sys
from pathlib import Path

from requirements_extract import SKILLS  # canonical skill list (shared with the .req.json path)

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "jobs.csv"
TITLE_GOOD = re.compile(r"data scientist|machine learning|ml engineer|ai engineer|mlops|data engineer|genai|generative|agentic|analytics engineer", re.I)
TITLE_SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|director|head|vp|manager|architect)\b", re.I)
TITLE_WRONG = re.compile(r"intern\b|sales|account|recruiter|attorney|nurse|mechanical|civil|electrician|professor|faculty", re.I)

NO_SPONSOR = re.compile(
    r"(no sponsorship|not (?:provide|offer|sponsor)[^.]{0,40}sponsorship|"
    r"unable to sponsor|cannot sponsor|will not sponsor|without sponsorship now or in the future|"
    r"sponsorship is not available|us citizen(?:ship)? (?:is )?required|must be a u\.?s\.? citizen|"
    r"green card (?:holders? )?(?:only|required)|citizens? or permanent residents? only)", re.I)
CLEARANCE = re.compile(r"security clearance|ts/sci|top secret|secret clearance|public trust", re.I)
YEARS = re.compile(r"(\d+)\s*\+?\s*(?:or more\s*)?years?", re.I)

def years_required(text: str) -> int:
    # max years figure that appears near 'experience' lines; crude but effective
    best = 0
    for m in YEARS.finditer(text):
        n = int(m.group(1))
        if 3 < n <= 20:
            ctx = text[max(0, m.start()-80): m.end()+80].lower()
            if "experience" in ctx:
                best = max(best, n)
    return best

def score_row(row, desc: str):
    title = row["title"]
    text = desc.lower()
    notes = []

    if TITLE_WRONG.search(title):
        return "F", "wrong domain title"
    if CLEARANCE.search(desc):
        return "F", "requires security clearance"
    if NO_SPONSOR.search(desc):
        return "F", "explicit no-sponsorship/citizenship requirement"
    if TITLE_SENIOR.search(title):
        return "F", "senior/staff/lead level"

    yrs = years_required(desc)
    if yrs >= 7:
        return "D", f"requires {yrs}+ yrs experience"

    hits = [s for s in SKILLS if s in text]
    skill_pct = min(len(hits) / 10, 1.0)  # 10+ skill hits = full marks
    pts = skill_pct * 40
    pts += 20 if TITLE_GOOD.search(title) else 5
    pts += 10 if any(k in text for k in ("machine learning", "data scien", "ml", "ai")) else 0
    smin = float(row["salary_min"] or 0)
    smax = float(row["salary_max"] or 0)
    if smax and smax < 85000:
        return "D", f"salary ceiling ${smax:,.0f} below floor"
    pts += 10 if (smin >= 90000 or smax >= 110000) else (5 if not smax else 3)
    pts += 10 if row["remote"] == "True" else 4
    sponsor_risk = row["sponsor_risk"] == "YES" or bool(re.search(r"\bsponsorship\b", text) and NO_SPONSOR.search(text))
    pts += 0 if sponsor_risk else 10

    if yrs >= 5:
        pts -= 10
        notes.append(f"{yrs}yrs asked")

    grade = "A" if pts >= 75 else "B" if pts >= 60 else "C" if pts >= 45 else "D"
    if (row["sponsor_risk"] == "YES") and grade in "AB":
        grade = "C"
        notes.append("capped C: sponsor_risk=YES")
    notes.append(f"{len(hits)} skill hits: " + ",".join(hits[:8]))
    return grade, "; ".join(notes)

def score_from_req(row, req):
    """Grade a job from a pre-extracted requirements dict (no text re-parse)."""
    title = row["title"]
    notes = []
    if TITLE_WRONG.search(title):
        return "F", "wrong domain title"
    if req.get("clearance"):
        return "F", "requires security clearance"
    if req.get("no_sponsorship"):
        return "F", "explicit no-sponsorship/citizenship requirement"
    if req.get("senior") or TITLE_SENIOR.search(title):
        return "F", "senior/staff/lead level"
    yrs = req.get("years_required", 0)
    if yrs >= 7:
        return "D", f"requires {yrs}+ yrs experience"

    hits = req.get("skills", [])
    pts = min(len(hits) / 10, 1.0) * 40
    pts += 20 if TITLE_GOOD.search(title) else 5
    pts += 10 if any(k in hits for k in ("machine learning", "llm", "genai", "agent")) else 0
    smin = float(row.get("salary_min") or 0)
    smax = float(row.get("salary_max") or 0)
    if smax and smax < 85000:
        return "D", f"salary ceiling ${smax:,.0f} below floor"
    pts += 10 if (smin >= 90000 or smax >= 110000) else (5 if not smax else 3)
    pts += 10 if row.get("remote") == "True" else 4
    pts += 0 if row.get("sponsor_risk") == "YES" else 10
    if yrs >= 5:
        pts -= 10
        notes.append(f"{yrs}yrs asked")

    grade = "A" if pts >= 75 else "B" if pts >= 60 else "C" if pts >= 45 else "D"
    if row.get("sponsor_risk") == "YES" and grade in "AB":
        grade = "C"; notes.append("capped C: sponsor_risk=YES")
    notes.append(f"{len(hits)} skill hits: " + ",".join(hits[:8]))
    return grade, "; ".join(notes)

def main():
    rows = list(csv.DictReader(open(CSV)))
    fields = rows[0].keys()
    counts = {}
    for row in rows:
        if row["status"] != "new":
            continue
        req_path = ROOT / row["description_file"].replace(".md", ".req.json") if row["description_file"] else None
        if req_path and req_path.exists():
            req = json.loads(req_path.read_text())
            grade, why = score_from_req(row, req)
        else:
            p = ROOT / row["description_file"]
            desc = p.read_text(errors="ignore") if p.exists() else ""
            grade, why = score_row(row, desc)
        row["score"] = grade
        row["status"] = "scored"
        row["notes"] = why
        counts[grade] = counts.get(grade, 0) + 1
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("scored:", counts)

if __name__ == "__main__":
    main()
