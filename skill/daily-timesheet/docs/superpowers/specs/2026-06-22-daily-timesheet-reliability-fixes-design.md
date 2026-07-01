# daily-timesheet reliability fixes — design

**Date:** 2026-06-22
**Status:** Approved, ready for implementation plan

## Problem

A real timesheet run (Fri 2026-06-19) surfaced three points where the skill
forced improvisation instead of running a bundled tool:

1. **No activity-timeline script.** `afk_blocks.py` produces only the day
   *skeleton* (work start/end, breaks, active spans). To actually classify the
   day I hand-wrote a throwaway `_tmp_aw619.py` that binned window/web events
   into 15-min buckets. That binning is core to every run and should be a
   permanent, improved script.
2. **Screenshots are unreadable.** `screenshot_capture.py` calls
   `ImageGrab.grab(all_screens=True)`, stitching 3 monitors into one
   ~6400×1440 PNG (~8 MB). When the Read tool ingests it, it downsamples to
   fit, shrinking each monitor to ~520 px wide — window titles and code become
   illegible, defeating the purpose of screenshot disambiguation.
3. **Harvest task-ID lookup is fragile.** Project assignments are paginated
   across 7 files (`harvest_assignments.json` + `_p2…_p7`). A first lookup did
   `sorted(glob)[-1]`, reading only the last page, and missed `NLS-CR202`
   (which lives in page 1). There is no bundled lookup, so the glob+json loop
   gets re-hand-rolled — and mis-rolled — each run.

Root cause across all three: the skill leaves classification-critical
mechanics to ad-hoc scripting.

## Goals

- Every classification run uses bundled, tested scripts — no improvised code.
- Window activity is presented at high time-resolution, tagged with the client
  category ActivityWatch already knows, with uncertainty made visible.
- Screenshots are readable per-monitor.
- Harvest project/task lookup is a single reliable command across all pages.

## Non-goals (YAGNI)

- No changes to `afk_blocks.py`, the Harvest posting/patch scripts, or
  `refresh_catalogs.py`.
- No historical re-capture or re-processing of already-stitched screenshots.
- AW categories stay **client-level** — this design does not attempt
  project/ticket-level auto-classification.

## Design

### 1. New script: `scripts/activity_timeline.py`

Window-only, high-resolution, client-categorized timeline. The permanent
replacement for the throwaway binning script.

**Inputs / flags** (consistent with `afk_blocks.py`):
- positional `date` (YYYY-MM-DD)
- `--utc-offset N` (default 12; use 13 during NZ daylight saving)
- `--window HH:MM-HH:MM` — zoom mode (see below)
- `--json` — machine-readable output

**Default output — merged contiguous spans + rollup:**
- Pull window events for the date's local-midnight UTC range from
  `aw-watcher-window_<host>`. Dedupe AW heartbeats by
  `(timestamp → longest duration)`; drop `<5s` noise.
- Merge consecutive events into spans: same window (app+title) runs combine;
  gaps `<60s` fold into the surrounding span. Output is variable-length spans
  at second precision, not a fixed grid.
- **Category tagging:** read `GET /api/0/settings` → `classes` (list of
  `{name:[...], rule:{type,regex,ignore_case}}`). For each span, apply each
  class's regex to the app+title string (mirroring AW's own categorize
  semantics). Tag the span with the matched category name(s).
  - no match → `uncategorized`
  - multiple matches → list all, flag the span
  - `uncategorized` and multi-match spans are explicitly flagged as
    "needs verification" — these are precisely the spans to check with the
    zoom mode or a screenshot.
- **Day-totals rollup** at the end: minutes per category + `uncategorized`.

**Zoom mode (`--window HH:MM-HH:MM`):**
- Same merged-span detail, restricted to the window, at finer detail.
- Additionally fold in the **web watchers** (`aw-watcher-web-firefox_<host>`,
  `aw-watcher-web-chrome_<host>`) for that window — full URLs/titles — so a
  fuzzy section can be drilled into before resorting to screenshots.

**Stated limitations (documented in the script and SKILL.md):**
- AW classes are client-level regex, not project/ticket-level. Categories get
  you to "NZLS", never to "NLS-CR202 vs NLS2232S".
- Categories are a first-pass signal only — never taken as 100% certain.
  Project/task still derives from ticket/work-item signals + `.context.md`,
  and ambiguous spans are confirmed via zoom mode and/or screenshots.

### 2. Per-monitor screenshot capture — `scripts/screenshot_capture.py`

- Replace the single stitched `ImageGrab.grab(all_screens=True)` save with
  **one PNG per physical monitor**, named `HH-MM-SS_m1.png`, `_m2.png`,
  `_m3.png`, ordered left-to-right by monitor x-position. A laptop-only day
  produces just `_m1.png`. Each file stays full per-monitor resolution and is
  readable when opened.
- Enumerate monitors via the `mss` library (purpose-built, reliable on Windows
  multi-monitor). `setup_screenshot_pipeline.ps1` installs `mss` alongside
  Pillow. (Final dependency decision confirmed during planning; ctypes
  `EnumDisplayMonitors` is the no-dep fallback if `mss` proves unsuitable.)
- Preserve existing behaviour: dated folder creation, pythonw-safe logging to
  `capture.log`, `optimize=True` PNGs.
- Update SKILL.md "Reading the screenshot folder (Windows)" to read the
  relevant monitor file (usually the primary/active monitor) rather than a
  stitched image, and to list the `_mN` variants.

### 3. New script: `scripts/harvest_lookup.py <code-or-fragment>`

- Search **all** `.mcp/harvest_assignments*.json` pages for a project whose
  `code` matches exactly, or whose `code`/`name` contains the fragment.
- Print, per match: `project_id`, project name, and each task assignment's
  `id`, name, and `billable` flag.
- Optional `--task <substr>` to filter task rows.
- Eliminates the hand-rolled glob loop and the "only read the last page" bug.

### 4. SKILL.md wiring

- **Step 2/3:** run `activity_timeline.py` to obtain the categorized timeline
  (replaces the manual binning narrative).
- **Step 4 (classify):** use the AW category as the first-pass client signal,
  with an explicit "verify, don't trust 100%" caveat; project/task still from
  ticket/work-item + `.context.md`.
- **Step 5 (disambiguate):** use `activity_timeline.py --window …` (web
  watchers folded in) as the first disambiguation step; screenshots second.
- Update "Reading the screenshot folder" and the "Files in this skill" list;
  document `harvest_lookup.py` where project/task IDs are looked up.
- Add a maintenance note: the user's AW `classes` are now a live signal source
  — worth filling the `FILL ME` / `New class` placeholder and adding missing
  clients (Cone Marshall, Heart Foundation, etc.). Note that the
  "CON2005 Short Courses under the EarnLearn Edge profile → CON2005" caveat
  still needs manual handling, since a client-level regex cannot catch it.

## Acceptance criteria

- `activity_timeline.py <date>` prints merged window spans tagged with AW
  categories plus a per-category day rollup; `uncategorized`/multi-match spans
  are flagged.
- `activity_timeline.py <date> --window HH:MM-HH:MM` additionally includes
  firefox+chrome web events for the window.
- `screenshot_capture.py` writes one readable PNG per monitor (`_mN` suffix);
  verified on the multi-monitor setup and on laptop-only (single file).
- `harvest_lookup.py NLS-CR202` returns project 48084036 and task
  `Gen - Development/Configuration` (20753151, billable) by searching all
  pages — the case that previously failed.
- SKILL.md reflects the new scripts and per-monitor screenshot reading.

## Risks / open items

- AW categorize matching semantics (concat order, first-vs-all match) — confirm
  against AW source during implementation so tags match what the AW UI shows.
- `mss` dependency acceptability vs ctypes fallback — settle in plan.
