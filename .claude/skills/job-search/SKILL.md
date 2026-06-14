---
name: job-search
description: Discover fresh AI/ML/DevOps job postings, score each against your master resume, and present a ranked shortlist for approval. Use when the user says "find jobs", "job hunt", "search", or runs /job-search.
---

# Job Search & Scoring

## Step 1 — Discover
Run from the project root:
```bash
.venv/bin/python scripts/search_jobs.py
```
Options: `--query "Agentic AI Engineer"` (repeatable), `--hours 24`, `--limit 30`.
The script merges results into `data/jobs.csv` (status=`new`) and saves each job
description under `data/descriptions/`.

If the user names specific companies, also check their Greenhouse/Lever boards directly:
- `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true`
- `https://api.lever.co/v0/postings/<slug>?mode=json`

## Step 2 — Score every `new` job
Read `profile/master_resume.md` once. For each row in `data/jobs.csv` with
status=`new`, read its `description_file` and assign a letter score:

| Score | Meaning |
|---|---|
| A | ≥80% of must-haves matched, title aligned, salary ≥ floor, no sponsor risk |
| B | Good match, 1-2 gaps in nice-to-haves |
| C | Stretch: title or seniority off, or several skill gaps |
| D | Poor match — wrong domain or hard requirement missed (e.g. 8+ yrs) |
| F | Disqualified: clearance required, explicit "no sponsorship", senior/staff level |

Scoring dimensions (weighted): must-have skills overlap (40%), title/seniority fit
(20%), domain fit (10%), salary vs the floor in profile.yaml (10%), remote/location (10%),
sponsorship risk (10%). If the candidate requires visa sponsorship (see profile.yaml),
cap `sponsor_risk=YES` jobs at C and say why — they burn limited work-authorization runway.

Write the score into the `score` column and set status=`scored`. Do this with a
small Python snippet over the CSV, not manual edits, to keep the file consistent.

## Step 3 — Present shortlist
Show A and B jobs as a markdown table: score, title, company, location/remote,
salary, sponsor risk, posted date, URL. One line per job on why it scored that way.
Mention how many C/D/F were filtered out.

## Step 4 — Approval gate (REQUIRED)
Ask which jobs to proceed with (AskUserQuestion or plain question). For each
approved job set status=`approved`. NEVER tailor or apply without explicit approval
of that specific job. After approval, hand off to the `tailor` skill.
