# Token-Efficiency Benchmark — career-agent

**Status:** Partially measured. Browser-payload figures are real measured data.
End-to-end figures are projections, clearly labeled. The full end-to-end number
requires a live agent-browser run (see §4).

---

## 1. Method

### What was measured
162 accessibility-tree snapshots stored in `.playwright-mcp/page-*.yml` were
produced during real Playwright-MCP apply runs (3 browser sessions captured
2026-06-10 and 2026-06-12). Each `.yml` file is the exact payload that was fed
to the model as a browser observation step in the old flow — no synthetic data,
no truncation.

### Token approximation
Tokens are estimated using **4 characters per token** — a common rough approximation
for English/HTML mixed content. This approximation is explicitly stated wherever
used; actual Claude tokenization may differ by ±10–20 %.

### Projection methodology
agent-browser is not installed in this environment, so no "after" snapshots could
be measured directly. All "after" figures are clearly labeled
**PROJECTION — not measured** and are derived from:
- the agent-browser documentation's stated behavior (`snapshot -i -c`: interactive
  elements only, compact format with short `@ref` handles instead of full ARIA trees);
- the `batch` command semantics (entire form filled in one invocation);
- arithmetic over the actual per-JD data in `data/demo_jobs.csv`.

---

## 2. Measured: Before (Playwright MCP browser payloads)

All numbers come from the 162 real `.playwright-mcp/page-*.yml` snapshots.

### Snapshot size statistics

| Metric | Value |
|---|---|
| Snapshot count | 162 |
| Total bytes across all snapshots | 5,597,796 B (~5.3 MB) |
| Average bytes per snapshot | **34,554 B (~33.7 KB)** |
| Maximum bytes (single snapshot) | 295,632 B (~289 KB) |
| Minimum bytes (single snapshot) | 0 B (empty/error snapshot) |

### Token estimates (@ 4 chars/token)

| Metric | Value |
|---|---|
| Average tokens per snapshot | **~8,639 tokens** |
| Maximum tokens (single snapshot) | ~73,908 tokens |
| Total tokens across all 162 snapshots | **~1,399,449 tokens** |

### Session breakdown

Snapshots were grouped into browser sessions using a gap threshold of > 10 minutes
between consecutive file timestamps.

| Session | Date | Snapshots | Duration |
|---|---|---|---|
| 1 | 2026-06-10 18:37–18:48 UTC | 29 | ~11 min |
| 2 | 2026-06-10 19:18–19:27 UTC | 30 | ~9 min |
| 3 | 2026-06-12 21:07–21:30 UTC | 103 | ~23 min |
| **Total** | | **162** | |
| **Average snapshots/session** | | **~54** | |

The average of 54 snapshots/session is skewed by session 3 (103 snapshots, which
appears to include both exploration and retry steps). Sessions 1 and 2 are closer to
what a typical focused apply run looks like (29–30 snapshots). A realistic
single-application snapshot budget under the old Playwright-MCP flow is
approximately **25–55 snapshots**, corresponding to roughly **216,000–476,000 tokens**
of browser-observation payload per application (at the measured average of 34,554 B
and 4 chars/token).

---

## 3. Projected: After (agent-browser + model tiering + Python pre-filter)

> **All numbers in this section are PROJECTIONS — not measured.**
> They will be replaced with real figures after a live agent-browser run.

### 3a. Browser payload reduction (agent-browser `snapshot -i -c`)

**Why it is smaller:** Playwright MCP's accessibility-tree snapshots include the
full ARIA tree of the page — every element, role, label, and property, whether or
not it is interactive. agent-browser's `snapshot -i -c` flag returns only
interactive elements (inputs, buttons, links) in a compact representation using
short `@ref` handles (e.g., `@e1`, `@e2`) instead of verbose ARIA attributes. On a
typical job-application form page, 80–95 % of the ARIA tree is non-interactive
(navigation, banners, descriptions, legal boilerplate) and is stripped entirely.

**Projected range:** Compact interactive-only snapshots on form-heavy pages typically
run 2–5 KB versus the measured 33.7 KB average.

| | Before (measured) | After (PROJECTED) |
|---|---|---|
| Avg bytes/snapshot | ~34,554 B (33.7 KB) | ~2,000–5,000 B (2–5 KB) |
| Avg tokens/snapshot | ~8,639 | ~500–1,250 |
| Reduction vs before | — | **~7×–17× smaller per snapshot** |

### 3b. Snapshot count reduction (`batch` form-fill)

Under Playwright MCP, every fill action was preceded by a fresh snapshot (the model
had to re-observe the page before each element interaction). A 15-field form therefore
generated ~15–20 snapshots just for filling, plus snapshots for navigation, scrolling,
and error recovery.

agent-browser's `batch` command fills an entire form in a single invocation:
`batch @e1="Alice" @e2="alice@example.com" ...`. The model needs one snapshot to see
the form, one `batch` call to fill it, and one snapshot to verify. That collapses
~15–20 fill-step snapshots into ~3 total.

| | Before (measured avg session) | After (PROJECTED) |
|---|---|---|
| Snapshots per form-fill session | ~25–55 | ~5–15 |
| Reduction | — | **~4×–5× fewer round-trips** |

**Combined projected browser savings:** combining smaller snapshot payloads (~10×) with
fewer snapshots (~4–5×), the total browser-payload token load per application is
projected to drop by roughly **40×–85× vs the measured baseline** — but this figure
is explicitly a projection derived from the two independent estimates above and must be
validated with a real run.

### 3c. Model tiering savings

Before this session's changes, every worker task (search, score, tailor, apply)
effectively used a single model size. The new `model_for()` function in
`app/server.py` routes:

| Task | Model |
|---|---|
| Job search + bulk scoring | **Haiku** |
| Tailoring + apply | **Sonnet** |
| High-quality resume (opt-in) | Opus (via `TAILOR_MODEL=opus`) |

**Illustrative calculation (PROJECTION):**
Assume 500 jobs discovered in one search run; average JD is ~2,000 tokens. Under the
old single-model approach, scoring all 500 read every JD → ~1,000,000 input tokens.
With Haiku, the same 500-job score costs roughly the same token count but at ~20× lower
cost per token vs Opus (verify current per-model pricing at the official Anthropic
pricing page before citing exact figures). If only 10 % of jobs
(50) are borderline and get a Haiku re-score, the total model input is roughly the same
number of tokens but at Haiku rates.

*Note: this is a cost projection, not a token-count reduction — tiering reduces dollars
spent rather than tokens consumed, because total JD tokens read stays similar.*

### 3d. Pure-Python pre-filter savings

`scripts/requirements_extract.py` writes a `<id>.req.json` at ingest time (once per
JD). `score_jobs.score_from_req()` is a pure-Python function: it reads the JSON, does
keyword/threshold math, and returns a score with zero model tokens.

**Effect:** In a 500-job firehose, the vast majority (jobs clearly out of scope: wrong
role, explicit US-citizen-only, salary far below target) are eliminated in pure Python
before any model sees the JD. Only borderline jobs (estimated 5–15 % of the total,
based on the demo dataset distribution) are forwarded for a Haiku re-score.

**Illustrative calculation (PROJECTION):**
- 500 jobs × 2,000 tokens/JD = 1,000,000 input tokens if every JD is model-scored.
- With pre-filter eliminating ~85 % → only ~75 jobs sent to Haiku → ~150,000 tokens.
- **Projected 85 % reduction in scoring token spend** (clearly an illustrative estimate;
  actual culling rate depends on the job-board query quality).

---

## 4. How to get the real after-number

To replace the projections in §3 with measured figures:

1. **Install agent-browser** per the instructions in `README.md` (§ Setup → Install
   agent-browser). Verify with `agent-browser --version`.

2. **Run one apply end-to-end** against a test posting (or the demo profile against a
   real low-stakes job):
   ```bash
   ./run   # starts the web UI at localhost:8377
   # approve one job, trigger tailor + apply
   ```

3. **Collect snapshot sizes.** agent-browser writes snapshots to a configurable
   directory (or stdout). Capture the per-step payloads and compute the same stats
   as §2: count, total bytes, avg bytes, avg tokens.

4. **Compare:**
   - Before (measured): avg 34,554 B / ~8,639 tokens per snapshot, ~25–55 snapshots
     per session.
   - After (measured from new run): record actual avg bytes and snapshot count and
     compute the ratio directly.

5. **Update this document.** Replace the "PROJECTED" labels in §3a and §3b with
   measured values, update §5 with the real ratio, and tag the commit.

---

## 5. Bottom Line

**Measured (old Playwright-MCP flow):**
Per-step browser payloads averaged **~34,554 B (~8,639 tokens at 4 chars/token)** across
162 real accessibility-tree snapshots. Three captured sessions averaged ~54 snapshots
each (sessions 1–2 ran 29–30 snapshots in ~10 min; the longer session 3 ran 103
snapshots in ~23 min). A representative single-application run generated roughly
**25–55 snapshots → ~216,000–476,000 tokens of browser-observation payload** under
the old flow.

**Projected (new agent-browser + tiering + pre-filter flow):**
agent-browser's compact interactive-only snapshots are projected to be roughly
an order of magnitude smaller per step; the `batch` form-fill collapses ~15–20
per-field round-trips into ~2–3 calls; and moving 500-job scoring to pure Python
removes the single largest token sink from the model entirely. The full end-to-end
token reduction is **projected to be substantial but is not measured** — the real
number requires a live agent-browser run following the procedure in §4.

> **Honest qualification:** the browser-payload averages in §2 are real measurements.
> Everything in §3 is a reasoned projection. Do not cite the combined ratio as a
> measured figure until §4 has been completed and this document updated.
