---
name: status
description: Show the job pipeline dashboard — counts by status, recent applications, pending approvals, and follow-ups due. Use when the user asks "status", "where are we", or "what's pending".
---

# Pipeline Status

Read `data/jobs.csv` and report:

1. **Funnel counts:** new → scored → approved → tailored → applied (+ apply-failed,
   apply-blocked, rejected, interview, offer).
2. **Needs action:** scored A/B jobs awaiting approval; approved jobs awaiting
   tailoring; tailored jobs awaiting apply; unknown-question blockers.
3. **Recent activity:** last 10 applied jobs with dates and confirmation notes.
4. **Follow-ups:** applications older than 10 days with no status change — suggest
   a follow-up email for each.
5. **Hygiene warnings:** remaining TODOs in profile.yaml, duplicate rows, stale
   `new` rows older than 7 days (job postings go stale — offer to purge).

Use a compact markdown table for the funnel and bullet lists for actions.
Statuses are canonical lowercase: new, scored, approved, tailored, applied,
apply-failed, apply-blocked, rejected, interview, offer, withdrawn, stale.
