#!/usr/bin/env python3
"""Discover fresh job postings across boards and merge them into the tracker.

Usage:
  .venv/bin/python scripts/search_jobs.py                      # all default queries
  .venv/bin/python scripts/search_jobs.py --query "MLOps Engineer" --hours 24
  .venv/bin/python scripts/search_jobs.py --limit 30

Writes/updates data/jobs.csv. New rows get status=new. Existing rows are never
overwritten, so scoring/approval status survives re-runs.
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from requirements_extract import extract_requirements


def write_req_json(path, desc_text):
    path = Path(path)
    path.write_text(json.dumps(extract_requirements(desc_text), indent=2), encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "data" / "jobs.csv"
PROFILE = ROOT / "profile" / "profile.yaml"

FIELDS = [
    "id", "status", "score", "title", "company", "location", "remote",
    "salary_min", "salary_max", "sponsor_risk", "date_posted", "site",
    "url", "description_file", "resume_file", "applied_date", "notes",
]

NO_SPONSOR_PAT = re.compile(
    r"(no\s+(visa\s+)?sponsorship|sponsorship\s+(is\s+)?not\s+(available|offered|provided)"
    r"|without\s+(the\s+need\s+for\s+)?sponsorship|unable\s+to\s+sponsor"
    r"|will\s+not\s+sponsor|cannot\s+sponsor|not\s+able\s+to\s+sponsor"
    r"|must\s+(be\s+authorized|not\s+require\s+sponsorship)|citizens?\s+only"
    r"|green\s*card\s+(holders?\s+)?(or\s+citizens?\s+)?only|security\s+clearance|TS/SCI)",
    re.IGNORECASE,
)

EXCLUDE_TITLE_PAT = re.compile(
    r"\b(staff|principal|director|vp|head\s+of|intern(ship)?|manager,)\b", re.IGNORECASE
)


def job_id(title: str, company: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", f"{company}-{title}".lower()).strip("-")
    return slug[:80]


def load_tracker() -> dict:
    rows = {}
    if TRACKER.exists():
        with open(TRACKER, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows[row["id"]] = row
    return rows


def save_tracker(rows: dict) -> None:
    TRACKER.parent.mkdir(exist_ok=True)
    with open(TRACKER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in rows.values():
            w.writerow(row)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", help="search term (repeatable); default: titles from profile.yaml")
    ap.add_argument("--hours", type=int, default=None, help="posted within N hours")
    ap.add_argument("--limit", type=int, default=25, help="results per query per site")
    ap.add_argument("--location", default=None)
    ap.add_argument("--sites", default="linkedin,indeed,zip_recruiter,google",
                    help="comma list: linkedin,indeed,zip_recruiter,glassdoor,google")
    args = ap.parse_args()

    prof = yaml.safe_load(PROFILE.read_text())
    search = prof["search"]
    queries = args.query or search["target_titles"]
    hours = args.hours or search.get("posted_within_hours", 72)
    location = args.location or "United States"
    min_salary = search.get("min_base_salary_usd", 0)

    from jobspy import scrape_jobs  # slow import, keep local

    tracker = load_tracker()
    found = added = 0

    for q in queries:
        print(f"--- searching: {q!r} (last {hours}h, {location})", flush=True)
        try:
            df = scrape_jobs(
                site_name=[s.strip() for s in args.sites.split(",")],
                search_term=q,
                google_search_term=f"{q} jobs in {location} since yesterday",
                location=location,
                results_wanted=args.limit,
                hours_old=hours,
                country_indeed="USA",
                is_remote=search.get("work_mode_preference") == "remote_first",
                linkedin_fetch_description=True,
                verbose=0,
            )
        except Exception as e:  # one board failing shouldn't kill the run
            print(f"    ! query failed: {e}", file=sys.stderr)
            continue

        if df is None or df.empty:
            print("    0 results")
            continue
        found += len(df)

        for _, r in df.iterrows():
            title = str(r.get("title") or "")
            company = str(r.get("company") or "")
            if not title or not company or EXCLUDE_TITLE_PAT.search(title):
                continue

            jid = job_id(title, company)
            if jid in tracker:
                continue

            desc = str(r.get("description") or "")
            smin = r.get("min_amount")
            smax = r.get("max_amount")
            # drop only when we KNOW the ceiling is below the floor
            try:
                if smax and float(smax) < min_salary:
                    continue
            except (TypeError, ValueError):
                pass

            desc_file = ""
            if desc and desc.lower() != "nan":
                desc_dir = ROOT / "data" / "descriptions"
                desc_dir.mkdir(parents=True, exist_ok=True)
                desc_file = f"data/descriptions/{jid}.md"
                (ROOT / desc_file).write_text(
                    f"# {title} — {company}\n\nURL: {r.get('job_url','')}\n\n{desc}",
                    encoding="utf-8",
                )
                write_req_json(ROOT / f"data/descriptions/{jid}.req.json", desc)

            tracker[jid] = {
                "id": jid,
                "status": "new",
                "score": "",
                "title": title,
                "company": company,
                "location": str(r.get("location") or ""),
                "remote": str(r.get("is_remote") or ""),
                "salary_min": "" if smin is None or str(smin) == "nan" else smin,
                "salary_max": "" if smax is None or str(smax) == "nan" else smax,
                "sponsor_risk": "YES" if NO_SPONSOR_PAT.search(desc) else "",
                "date_posted": str(r.get("date_posted") or ""),
                "site": str(r.get("site") or ""),
                "url": str(r.get("job_url_direct") or r.get("job_url") or ""),
                "description_file": desc_file,
                "resume_file": "",
                "applied_date": "",
                "notes": "",
            }
            added += 1

    save_tracker(tracker)
    print(f"\nDone {datetime.now(timezone.utc).isoformat(timespec='seconds')}: "
          f"{found} results scanned, {added} new jobs added, tracker now {len(tracker)} rows.")
    print(f"Tracker: {TRACKER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
