---
name: daily-timesheet
description: Use when the user wants to fill in, review, regenerate, or backfill a timesheet, log time to Harvest, or asks any date-scoped "what did I do / summarise yesterday / what was I working on Friday" question. Auto-relevant whenever the user mentions Harvest, ActivityWatch, daily_exports, or Timesheets/, even without the word "timesheet". Targets a workspace containing `Timesheets/.context.md`, `daily_exports/`, and `.mcp/` catalogs — the user supplies these on their own machine.
---

# daily-timesheet

For consultants who track time across multiple clients. ActivityWatch plus a scheduled screenshot grabber (`~/Pictures/WorkScreenshots/`) capture the workday; this skill turns that into a reviewable billable timesheet and (with confirmation) posts it to Harvest.

**Read the whole Workflow section before starting a run — the guards in Steps 3 and 6 are where runs go wrong.**

## What lives where (read before adding any new fact)

This skill is **shareable** — sort every fact by who it applies to. Don't use the cross-session memory store; the skill is the single source of truth.

- **Generic mechanism** (any user) → `SKILL.md` / `references/` / `scripts/`: classification, blocking, posting, reusable heuristics, API quirks.
- **One user's facts** → `Timesheets/.context.md` (in the user's workspace, not the skill folder): clients, colleagues, signals, billing-convention *overrides*, machine specifics, CRM URLs / account GUIDs, pac profiles, prefix→client map. Read every run. Size-budgeted — see Step 11.
- **Secrets** → `.env` (skill root, gitignored): Harvest creds. Share `.env.example`, never `.env`.

## When to invoke

**Strong triggers** — invoke without further confirmation: "summarise yesterday" / "what did I do on <date>" / "fill in <day>'s timesheet" / "log time for <date>" / "review today's work" / "backfill the timesheets".

**Soft triggers** — confirm first: the user mentions Harvest, ActivityWatch, `daily_exports/`, `Timesheets/` in passing; a new export landed and the user seems unsure what to do with it.

**Do NOT invoke when:**
- the user is asking about *configuring* the pipeline itself (export script, ActivityWatch setup, screenshot scheduler) — that's maintenance, not daily classification (see `references/setup.md`)
- the user wants *raw* Harvest data beyond a date range ("list my projects", "monthly totals") — point at the Harvest web UI or a one-off script

## Data sources

| Source | Purpose | When to use |
|---|---|---|
| **ActivityWatch** at `http://localhost:5600/api/0/` | Live, authoritative event stream (window titles, AFK, browser tabs) | **Primary** — but access it via the bundled scripts; query raw only per `references/activitywatch.md` |
| `daily_exports/<date>/compact.jsonl` | Pre-processed AW dump (sub-10s events pre-dropped; short keys: `b`=bucket, `t`=timestamp, `d`=duration, `a`=app, `ti`=title, `u`=url, `s`=afk) | Fallback only when AW is unreachable |
| `~/Pictures/WorkScreenshots/<date>/HH-MM-SS_mN.png` | **Source-of-truth** screenshots, ~2.5 min cadence, 08:30–20:00 weekdays | Disambiguation only — load specific timestamps, never proactively |
| `daily_exports/<date>/screenshots/` | Partial copy | Ignore; use the Pictures folder |
| `Timesheets/.context.md` | The user's attribution rules — **source of truth** for all ambiguity calls | Read every run |
| `Timesheets/<date>_timesheet.md` | Optional markdown audit trail | Format reference; create only on request |
| `.mcp/harvest_assignments*.json` | Cached Harvest project assignments (`project.id/name/code`, `client.name`, `task_assignments[]`) | Project + task IDs, via `harvest_lookup.py` |
| `.mcp/<catalog>.txt/.json` | User-specific catalogs (e.g. active-incident list) | Ticket-number → title |

**Screenshot location:** `~/Pictures/WorkScreenshots/` above is the default. If `TIMESHEET_SCREENSHOTS_DIR` is set in the skill's `.env`, captures go there instead — read that path rather than the literal one in the commands below.

**Timezone:** AW stores UTC; all scripts take `--utc-offset` (default 12; **13 during NZ daylight saving**). User timezone from `## Preferences` in `.context.md`, default `Pacific/Auckland`.

**Running the scripts:** every `python scripts/…` command below is relative to *this skill's own folder*, not the workspace. The session's working directory is the workspace, so prefix them with the skill path — `python "$HOME/.claude/skills/daily-timesheet/scripts/afk_blocks.py" <date>` (Windows: `$HOME\.claude\skills\daily-timesheet\scripts\…`). Catalog paths resolve from the workspace, so run them *from* the workspace directory.

### Reading the screenshot folder (Windows)

List with PowerShell `Get-ChildItem` — the Bash `cmd dir` and `Glob` routes return empty for the `Pictures` path even when it's full:

```powershell
Get-ChildItem "$HOME\Pictures\WorkScreenshots\2026-05-29" -Filter *.png | Sort-Object Name
```

Each capture tick writes **one PNG per monitor** (`HH-MM-SS_m1.png`, `_m2.png`, … left-to-right, native resolution). Laptop-only days have just `_m1`. On multi-monitor days read the monitor showing the active app — and when hunting a client signal, check the *other* monitors too. Days captured before mid-2026 may hold single stitched `HH-MM-SS.png` files. Filenames are local time; filter by name prefix to find the capture nearest a timestamp, then `Read` the PNG normally.

## Prerequisites — check at start of every run

Run in parallel before classifying anything. If any first-run piece is missing (no `.context.md`, no `.env`, no screenshot task, unknown AW buckets), follow `references/setup.md`.

1. **`Timesheets/.context.md` exists** — if missing, run first-run setup; don't classify without it.
2. **ActivityWatch reachable** — `curl -s http://localhost:5600/api/0/buckets/` returns JSON. If not, fall back to `daily_exports/<date>/compact.jsonl`; if both missing, the day can only be reconstructed from screenshots + user memory — say so explicitly.
3. **AW bucket ids resolved** — from `.context.md` if cached, else discover and offer to cache.
4. **Catalogs fresh** — `.mcp/harvest_assignments*.json` + client catalogs modified within 7 days; else run `scripts/refresh_catalogs.py` (details: `references/catalog-refresh.md`). Surface a >30-day gap to the user before refreshing, unless `.context.md` preferences say refresh silently.
5. **Harvest credentials work** — `python scripts/harvest_list.py <today> <today>` runs without auth error. "credentials not found" → `references/setup.md`; `401/403` → PAT revoked, user must regenerate.

**Tunable defaults** (override via `## Preferences` in `.context.md`): AFK break threshold `1050s` (17.5 min); lunch window `11:30–14:30`; work-hours rendering window `06:00–20:00`; default Harvest task `Gen - Development/Configuration`.

## Workflow

### Step 1 — Resolve target date and scope

If the user gave a date, use it. Otherwise: list existing entries (`harvest_list.py`) for the past ~10 days, cross-reference against `~/Pictures/WorkScreenshots/<date>/` (most reliable date index) or `daily_exports/`, and pick the days with activity but no/partial Harvest entries. **Today is always "in progress" on a no-date run — it is not a reason to ask.** Default to the oldest fully-unbilled *prior* day and mention today's partial state separately; ask only when several *prior* gap days compete. No gaps → "all caught up" (offer today-so-far).

Convert relative dates ("yesterday", "Friday") using today's date in the user's timezone.

**Honor partial-day scope:** "only do the morning" / "I've filled in after 12:40" restricts classification to that window — don't propose blocks outside it.

### Step 2 — Load inputs

Read in parallel:
- `Timesheets/.context.md` (full file)
- `references/classification-rules.md` (the classification rubric — client, project, **task selection**, interleaved-day protocol)
- Cached catalogs from `.mcp/`
- `python scripts/afk_blocks.py <date>` — the day skeleton (work_start, work_end, breaks, active spans)
- `python scripts/activity_timeline.py <date>` — merged window spans tagged with the AW client category, plus per-category rollup. **Compact output is the default and is enough** — do NOT reach for `--full` routinely; zoom specific blocks later with `--window HH:MM-HH:MM`. Loading the full raw timeline for a mostly-single-client day is the main cause of context bloat.
- Screenshot index: list `~/Pictures/WorkScreenshots/<date>/` filenames (PowerShell, per above). Don't open PNGs yet.

The two scripts complement each other: AFK anchors the time boundaries; the timeline shows what happened inside them. Don't derive either by hand from raw events — hand-derivation is where end-of-day and break errors come from. (Sole exception: AW unreachable and working from `compact.jsonl` — apply the manual blocking spec in `references/activitywatch.md`.)

### Step 3 — Block the day

Group the day into proposed blocks using the script outputs. **The skeleton is arithmetic, not judgment — take it verbatim:**

- **Breaks = `afk_blocks.py`'s `breaks` list** (afk ≥ threshold), plus any break the user explicitly states. Do not invent a break, stretch one, or infer one from a cluster of short AFKs, window gaps, or screenshots. One exception: a window-event gap ≥30 min with *no AFK record covering it* is also a hard boundary — rare, and usually means the watcher restarted.
- **`work_end` = the script's `work_end`** (last `not-afk` moment) — a *ceiling*, not a magnet. The day never ends at the last window event: a terminal/IDE/browser left in focus reads as "still working" for minutes or hours after the user walked away (the script's `window_watcher_tail` flag marks this). Never extend the last block to the screenshot window (08:30–20:00) or the work-hours rendering window (06:00–20:00) — those are capture/display bounds, not activity signals. And when `work_end` itself is a momentary blip (a sub-2-min `not-afk` flicker after ≥10 min idle — the script flags this too), end the final block at its last *substantive* active span, not at the blip.
- **A block runs from an active-span start to the next break start (or `work_end`).** It never crosses a break, and it never stops early because short AFKs cluster near its tail.
- **Short AFK folds in.** AFK events `< 1050s` are not boundaries — bathroom/coffee stays inside the block, duration not subtracted.

**Validate every block with its `active_ratio`** (get it per block via `afk_blocks.py <date> --window HH:MM-HH:MM`; the default output covers only whole spans). A `.context.md` billing convention can override the ratio verdict for a specific item (e.g. a standup the user joins by phone bills despite a low ratio):
- `≥ 0.7` — genuinely active; fold in short AFK as designed.
- `0.4–0.7` — thin. Flag 🔸 and shrink to the contiguous active spans (drop idle heads/tails; split around a ≥10 min cumulative mid-block AFK clump). **Then re-merge for billing:** adjacent shrunk pieces with the same attribution, separated only by dropped idle, become ONE entry whose start/end are set so its duration ≈ the summed active minutes (anchor on the largest piece; note the netted-out idle in the presentation). Never propose an entry under 0.25 hr — fold it into a same-client neighbour or drop it with a note. Typical thin block: supervising a background agent — bill the supervision as one entry, not a string of 8–20 min slivers.
- `< 0.4` — mostly idle; do not propose billing. Ask the user what was happening, citing screenshot timestamps from the active spans. Common cause: a long window event that stayed in focus after the user left. Window duration ≠ work time.

Cumulative short AFKs are real: several 5–15 min chunks in an hour add up. `active_ratio` — not "longest single AFK" — decides.

**Work fragments inside an excluded stretch** (short bursts of real work in the middle of a personal-browsing run): ≥10 min for one client → bill it, by extending the nearest same-client entry or standing alone if it reaches 0.25 hr; under 10 min → surface it in the presentation and leave it unbilled by default.

**Under-billing is as much an error as over-billing.** `work_end` is the ceiling; the `--cover` check in Step 6 is the floor. Classic failure to avoid: a cluster of sub-threshold AFKs around 11:20–11:45 looks like "lunch starting", the morning gets cut at 11:15 — when the script's actual break is 12:30–13:41 and 11:45–12:30 was solid work.

**Soft boundaries** — split only where it improves classification: a sustained context switch (≥3 consecutive events on a different ticket/profile, ≥3 min total); a Teams meeting starting (`Meeting | …` / `Call with …` title) — meetings are usually their own block; an active-ratio drop mid-block. **A named meeting attended while multitasking still gets carved out:** when a meeting window recurs in fragments across a ~15–60 min stretch (the user in the call while coding in parallel), that stretch is a meeting block with its own attribution — don't fold it into the surrounding dev block just because the meeting fragments are individually short.

Aim for 15-min granularity (0.25 hr); fold blocks shorter than 0.25 hr into a neighbour.

These rules apply identically on the **backfill path** (filling the gap between the last timesheet and now) — trailing left-in-focus windows are *more* likely there.

### Step 4 — Classify each block

For each block determine **client + Harvest project + Harvest task + billable + confidence (high/medium/low)** per `references/classification-rules.md`. Mechanics:

- The AW category from the timeline is a client-level first pass only — never project/ticket-level, never 100%. Investigate every `uncategorized` and `!MULTI` span.
- Ticket-shaped strings (`[A-Z]{2,4}\d{3,}S?`) in titles/URLs are the highest-confidence signal: resolve the title in the user's incident catalog and the project/task via `python scripts/harvest_lookup.py <code-or-name>` — it searches ALL catalog pages and falls back to the user's recent entries for archived projects. Never hand-roll a glob loop (it reads one page and misses projects). Trailing `S` = Support: tag the description `[Support]`, same project/task selection.
- **Task selection and billable status: follow the rubric's "Task selection" section exactly** — `.context.md` overrides first, task follows the block's dominant activity, billable comes from `task_assignments[].billable` not the task name.
- **If the day shows more than one client, or a block is titled by an agent-session file (`CLAUDE.md`, `AGENTS.md`, plan `.md`s): apply the rubric's "Interleaved days" protocol before accepting any block over an hour.** This is the single largest source of real misattributions.

### Step 5 — Disambiguate flagged blocks

For any 🔸 block (low confidence, thin ratio, or ambiguous attribution):

- **AFK status is settled by the AFK watcher** — never re-infer active/idle from screenshots. Screenshots and zooms answer only *which client/project*.
1. **Zoom the timeline first:** `python scripts/activity_timeline.py <date> --window HH:MM-HH:MM` folds in Firefox/Chrome web-watcher rows — richer URL/title signals without opening images.
2. **Then screenshots**, for generic apps that don't name their client (XrmToolBox, bare VS Code, terminals): find the nearest `HH-MM-SS_mN.png` to the ambiguous timestamps, read the env URL / workspace / repo / ticket on screen. Different clients in different screenshots within one block → split the block (switch-point protocol).
3. **Still ambiguous → ask the user**, showing which screenshots you checked, what you saw, and the candidate clients.
- **Never silently bill an abandoned-task block.** Setup/sign-in/install work that ended without a client deliverable and a pivot elsewhere → surface it; default to internal-admin non-billable unless the user says otherwise.

### Step 6 — Present the proposed timesheet

Render in the user's format:

```markdown
| Time | Duration | Client | Description |
|------|----------|--------|-------------|
| 08:12–08:46 | 0.5 hrs | <Client> | <Description with ticket # if any> |
```

Flag uncertain blocks 🔸 below the table. End-of-day and breaks are deterministic; *which client / billable / where to split* is judgment — flag it rather than committing silently. The user's review is what makes the sheet accurate, so make uncertain calls easy to see.

**Three hard guards — all mandatory before presenting:**

1. **Outer block edges are the script's spans, transcribed verbatim.** A block starts at an active-span start and ends at a break start / `work_end` — don't hand-tidy or merge those edges. *Interior* splits (classification boundaries at a client switch, meeting, or work-item change) are allowed and expected — they must sit strictly inside a script span and be evidence-based, and adjacent sub-blocks must tile the span exactly. Shrunk-and-re-merged thin blocks (Step 3) are the one sanctioned exception to verbatim edges. Entries post as start/end times and Harvest derives the hours — the Duration column is informational, so don't distort boundaries to make durations land on neat quarters; the only hard rule is no entry under 0.25 hr. If an outer edge doesn't match a script span (and isn't a documented shrink), that's a transcription bug, not a judgment call.
2. **No block ends after `work_end`.** Shrink any that do.
3. **Billed blocks must cover the active spans.** Pass the *proposed billed entries* (post-shrink, exactly what Step 8 will post):
   ```
   python scripts/afk_blocks.py <date> --cover "08:30-09:00,09:30-12:30,13:45-17:06"
   ```
   Every reported `UNCOVERED` stretch (≥15 min active, not in a break) must be billed or explicitly listed as a known exclusion (personal browsing per `.context.md`, or a documented thin-block drop) — never silently absent.

**Show the AFK skeleton with the table** so the user can sanity-check boundaries at a glance, e.g.:
`AFK watcher: work 08:27–17:06, lunch 12:30–13:41, active 354.9 min; billed 7.5h covers all active spans (0 unaccounted).`

Then ask:

> "I've drafted N blocks for <date> (AFK watcher: work ended HH:MM, breaks at …; blocks cover all active spans). M are high confidence, K are 🔸. Walk through the 🔸 ones, or batch-accept and edit after?"

Wait for the answer; edit per the user's input.

### Step 7 — Write the timesheet .md *(optional — ask first)*

Harvest is the system of record; the user often doesn't need the markdown file. **Ask** before generating. If they want it, write `Timesheets/<date>_timesheet.md` per `references/output-format.md`.

### Step 8 — Confirmation gate before Harvest

First self-check every line of the proposal:

- [ ] `--cover` run and clean (no unexplained UNCOVERED)
- [ ] No block past `work_end`; no block crossing a script break
- [ ] Every `project_id`/`task_id` came from `harvest_lookup.py`; billable flag checked
- [ ] Task = dominant activity per the rubric, `.context.md` overrides applied
- [ ] Every Harvest note passes the client-readability test (Non-negotiables below)
- [ ] All 🔸 blocks resolved with the user
- [ ] `.context.md` exclusions applied (personal browsing, recurring internal items)

Then show:

> "Ready to post to Harvest. This will create N time entries:
> - 0.5 hrs · [Adaptable Consulting Limited] · Adaptable Internal — Team Standup
> - 0.75 hrs · [Connexis] · CON2020S Connexis Fabrics Copy job — Gen - Investigation
>
> Proceed? (yes / no / edit block <n>)"

**Do not post without an explicit "yes" or equivalent.** Edits loop back to Step 6.

### Step 9 — Post to Harvest

For each confirmed block, serially (so the user can interrupt):

```
python scripts/harvest_post.py <project_id> <task_id> <YYYY-MM-DD> <HH:MM> <HH:MM> '<notes>'
```

- Times: 24h (`16:05`) or 12h (`4:05pm`) both accepted.
- **Single-quote the notes** — money amounts (`$5k`), backticks, and shell-shaped substrings get mangled otherwise.
- Success prints `OK <entry_id>` — capture it for Step 10. Failure prints `ERR <status> <body>` and exits non-zero — stop and surface, don't retry silently.
- The script always sends `started_time`+`ended_time`, never bare `hours`: in a start/end-time Harvest account, bare `hours` starts a running *timer*. Passing times works in either account mode.
- After each post log: `✓ Posted: <hours> hrs · <project.code> · <task>`.

Fix a wrong entry with `python scripts/harvest_patch.py <entry_id> [--start HH:MM] [--end HH:MM] [--notes "..."] [--hours N] [--project-id N] [--task-id N] [--date YYYY-MM-DD]` (≥1 flag; same OK/ERR convention).

**Block belongs to brand-new client work with no Harvest project yet** → follow `references/new-client-work.md` (create the backend case, post other blocks now, bill the deferred one when the synced project appears).

### Step 10 — Wrap-up

Summarise: total hours posted, blocks deferred/skipped, suggested next action (next date to backfill, or "all caught up"). Save the entry ids to `Timesheets/<date>_harvest_responses.json`: `{"entries": [{"id": 2933345845, "project_code": "ACL-001", "hours": 0.25, "notes": "..."}], ...}`.

### Step 11 — Surface skill or `.context.md` improvements

A run frequently reveals a fact the skill or `.context.md` doesn't know (a new signal you had to guess, a convention that turned out wrong, an offline watcher). Collect them and present at the end:

- *This user's* clients/colleagues/signals/preferences → propose for `.context.md` (most additions).
- The *workflow itself* (a generic heuristic, data-source change, API quirk) → propose for `SKILL.md`/`references/`.

Show the exact diff, one fact per ask. Example: "The XrmToolBox signal isn't in `.context.md`; I guessed EarnLearn. Add `XrmToolBox connecting to env X → EarnLearn` under EarnLearn?"

**`.context.md` size budget — check after every edit to it.** `(Get-Item Timesheets/.context.md).Length` must stay under **14,000 bytes** (override via `## Preferences`). Over budget → compact in the same session, in this order: (1) move any *generic* rule that crept in into this skill's references — that's skill drift, not a user fact; (2) delete facts proven wrong or superseded (finished workstreams, retired clients, one-off ticket examples older than a few months); (3) shorten confirmed-example parentheticals to the date stamp. If getting under budget would drop a live user fact, ask the user which to drop — never silently delete.

## Non-negotiables

- **No Harvest write without explicit confirmation.**
- **Honor `.context.md` exclusions** — personal browsing, AFK breaks, personal home admin are NEVER billable.
- **Don't fabricate confidence.** A block that could be 2–3 clients gets surfaced, not arbitrated.
- **Harvest notes are client-readable.** They go out on invoices: describe *what part of the client's project* was worked on, never the internal mechanism, file names, internal app names, or chat partners. If a term wouldn't appear in the SOW or on the client's own board, it doesn't go in the note. Tickets (`NLS2232S`) and recurring meeting names are fine. The markdown timesheet stays internal and can be granular. Style defaults: the rubric's "Writing the Harvest note" section; the user's own examples in `.context.md` "How I bill".
- **`.context.md` is the source of truth for per-user facts** — propose new user facts there, not in the skill.

## Files in this skill

- `SKILL.md` — this file
- `.env.example` / `.gitignore` — Harvest credential template (copy to `.env`, gitignored)
- `references/setup.md` — first-run setup: screenshot task, `.context.md` creation, Harvest creds, AW discovery, AW category maintenance
- `references/context.md.example` — starter template for `Timesheets/.context.md`
- `references/classification-rules.md` — client/project/**task** rubric + interleaved-day switch-point protocol
- `references/activitywatch.md` — raw AW API reference (endpoints, buckets, heartbeat dedupe, lock-screen quirk)
- `references/output-format.md` — timesheet .md template
- `references/catalog-refresh.md` — refreshing `.mcp/` catalogs
- `references/new-client-work.md` — billing work that has no Harvest project yet (Dataverse case creation)
- `scripts/afk_blocks.py` — deterministic day skeleton: work_start/work_end/breaks/active spans/active_ratio; `--window`, `--json`, `--utc-offset`, `--afk-threshold`, `--cover "HH:MM-HH:MM,..."` coverage check
- `scripts/activity_timeline.py` — categorized window timeline + rollup; `--window HH:MM-HH:MM` zoom folds in web watchers; flags `uncategorized`/`!MULTI`; `--utc-offset`, `--json`
- `scripts/harvest_lookup.py` — project/task id lookup across ALL catalog pages, live-entry fallback for archived projects (a miss after the fallback = genuinely unknown project; a cache refresh won't help); `--task`, `--mcp-dir`, `--json`, `--no-live`, `--days`
- `scripts/harvest_post.py` / `harvest_patch.py` / `harvest_list.py` — create / update / list time entries (`OK <id>` / `ERR …`)
- `scripts/harvest_client.py` — shared `.env` + API helper
- `scripts/refresh_catalogs.py` — refresh `.mcp/harvest_assignments*.json` + incident catalog; `wait_for_project(<code>)` for new synced projects
- `scripts/screenshot_capture.py` + `scripts/setup_screenshot_pipeline.ps1` — per-monitor capture + one-time scheduled-task setup
