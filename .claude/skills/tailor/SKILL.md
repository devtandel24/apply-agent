---
name: tailor
description: Generate a job-specific ATS-optimized resume PDF (and cover letter on request) for an approved job. Use after job approval or when the user says "tailor resume for X".
---

# Resume Tailoring

Inputs: one `approved` row in `data/jobs.csv`, its `description_file`,
`profile/master_resume.md`, `profile/resume_template.html`.

## Hard rules — integrity
- Every fact (employer, title, dates, metrics, skills) must already exist in
  `master_resume.md`. You may reword, reorder, emphasize, and cut — you may NOT
  invent experience, inflate metrics, or add skills she doesn't have.
- Keep it to ONE page (two only if unavoidable).
- TODO placeholders (LinkedIn/portfolio/location) must be resolved from
  `profile/profile.yaml`; if still TODO, ask the user before generating.

## Process
1. Read the must-have skills list from `data/descriptions/<id>.req.json` (key:
   `skills`) — this is cheaper than re-reading the full job description. Fall back to
   reading the description file only if the `.req.json` is absent. Also extract: exact
   job title, top 8-10 keywords/skills, must-have requirements, domain language.
2. Create `output/<job-id>/resume.html` from the template:
   - Summary: mirror the job title (e.g. "Machine Learning Engineer with 3+ years…")
     and weave in 3-4 JD keywords she genuinely has.
   - Skills: reorder so JD must-haves appear first in each category; drop irrelevant ones.
   - Experience bullets: pick the 4-6 most relevant per role; lead with the ones
     matching JD requirements; align vocabulary (e.g. JD says "data pipelines" — use
     that phrase where master resume says "ETL pipelines", since both are true).
   - Projects: keep only the 2-3 most relevant.
3. **Keyword coverage check** — after writing `resume.html`, run:
   ```bash
   .venv/bin/python -c "
   import json, os, sys
   sys.path.insert(0, 'scripts')
   from resume_check import keyword_coverage
   rp = 'data/descriptions/<id>.req.json'
   if not os.path.exists(rp):
       print('SKIP: no .req.json — coverage check skipped'); sys.exit(0)
   req = json.load(open(rp))
   html = open('output/<id>/resume.html').read()
   cov, missing = keyword_coverage(html, req['skills'])
   print(cov, missing)
   "
   ```
   If coverage < 0.6, revise the resume to honestly surface more genuinely-matching
   skills (check `master_resume.md` for overlooked synonyms or related skills she
   actually has — NEVER fabricate) and re-run the check before proceeding.
4. **Honest-framing self-review** — before rendering the PDF, re-read the
   `master_resume.md` "Honest-framing rules" section and verify every bullet and
   metric in `resume.html` still obeys them (designed ≠ built; no Phase-2 feature
   inflation; no invented metrics).
5. Render PDF:
   ```bash
   .venv/bin/python scripts/make_pdf.py output/<job-id>/resume.html
   ```
   **`make_pdf.py` exits non-zero (code 2) if ATS lint fails** (leftover
   `{{placeholders}}`, layout `<table>`, or `<img>`). Treat a non-zero exit as a
   hard stop: fix the template issue and re-render — do NOT ignore it.
6. Visually check the PDF (Read the file) — one page, no overflow, no {{placeholders}} left.
7. Update tracker row: `resume_file=output/<job-id>/resume.pdf`, status=`tailored`.
8. Show the user a 3-line diff summary of what was emphasized vs the master resume,
   plus a clickable path to the PDF.

## Cover letter (only if the job requires one or user asks)
Write `output/<job-id>/cover_letter.md` — 3 short paragraphs, max 250 words, factual,
referencing one concrete company detail from the JD. Render to PDF the same way
using a minimal HTML wrapper.
