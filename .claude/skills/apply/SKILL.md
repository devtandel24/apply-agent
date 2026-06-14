---
name: apply
description: Fill out and submit a job application in the browser on your behalf using agent-browser (scripts/browser.py), with a mandatory confirmation gate before final submission. Use when the user approves applying to a tailored job.
---

# Auto-Apply (agent-browser)

Preconditions — refuse to start and tell the user what's missing if any fail:
- The job row in `data/jobs.csv` has status=`tailored` and a `resume_file` PDF exists.
- `profile/profile.yaml` has no remaining `TODO` in `contact`, `work_authorization`,
  or `eeo.policy`.

Uses `scripts/browser.py` (the agent-browser wrapper) for all browser actions. Work
in a visible (headed) browser so the user can watch.

> **Note:** agent-browser is a free local binary that must be installed (see README);
> if `scripts/browser.py` reports it is missing, tell the user to install it.

## Process
1. `navigate(url)` to the job's `url`. Call `snapshot()` to get element refs
   (e.g. `@e1`, `@e2`). Find the Apply button ref and `click(ref)` it. If it
   redirects to an ATS (Greenhouse / Lever / Ashby / Workday / iCIMS), call
   `snapshot()` again on the ATS page and continue there.
2. **Account walls (Workday etc.):** create an account with `accounts.signup_email`
   and a strong generated password; append `site,email,password,date` to
   `data/portal_accounts.csv` BEFORE submitting the signup form. If the site says an
   account already exists, check that file for the password.
3. Call `snapshot()` to collect all form field refs, then fill all fields from
   `profile/profile.yaml` using `fill_form({ref: value, ...})` to batch-fill the
   entire form in one call:
   - Contact / address / links from `contact`.
   - Upload the tailored PDF from `resume_file` via the file input ref. If the ATS
     parses the resume into editable fields, verify and fix the parsed values.
   - Education and employment history from their sections.
   - Screening questions from `screening_defaults`.
4. **Work authorization — never lie:**
   - "Authorized to work in the US?" → per `work_authorization` in profile.yaml.
   - "Will you now or in the future require sponsorship?" → answer **truthfully**
     from `work_authorization` (if you require sponsorship, answer Yes — never claim otherwise).
   - Visa status dropdowns → the closest match to your status in profile.yaml.
5. EEO section: follow `eeo.policy` ("answer" → use stored values; "decline" →
   "I don't wish to answer" on every question).
6. **Unknown questions:** if a required question isn't covered by profile.yaml
   (essay prompts, "why us", niche tech questions), STOP and ask the user. Record
   their answer in the tracker `notes` (and suggest adding it to profile.yaml if
   reusable). Never fabricate an answer to a factual question.
7. CAPTCHA or email-verification step → pause and ask the user to complete it in
   the browser window, then continue.

## Submission gate (MANDATORY)
Before clicking the final Submit:
1. Call `snapshot()` of the review page.
2. Show the user a summary of every answer given.
3. Ask explicitly: "Submit application to <Company> — <Title>? (yes/no)" (in UI mode,
   route through `ui_bridge.py` with `--type submit_gate`).
4. Only on approval: `find_click("button", "Submit")` (or `click(ref)` for the submit
   button ref), then `screenshot("output/<job-id>/confirmation.png")` for the
   confirmation page.

## After submission
Update the tracker row: status=`applied`, `applied_date=YYYY-MM-DD`. Save any
confirmation number in `notes`. If submission failed, status=`apply-failed` with
the reason in `notes` — never mark `applied` unless the confirmation page was seen.

## Limits
- Max 1 application at a time; finish or abort before starting the next.
- If a site blocks automation or errors twice in a row, mark `apply-blocked` and
  move on — tell the user to apply manually with the tailored PDF.
- LinkedIn "Easy Apply" is against LinkedIn ToS to automate — prefer the company's
  own careers page (the tracker's `url` is the direct link when available).
