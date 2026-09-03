---
name: daily
description: Fill in, review, regenerate, or backfill a daily timesheet from ActivityWatch data and log the time to Harvest. User-invoked.
compatibility: Runs bundled Python scripts, so it needs Python 3.10+ on the PATH and a harness that can execute local commands. Reads a running ActivityWatch server (default http://localhost:5600) or a daily_exports/ dump of one. Logging time needs Harvest credentials. Screenshot capture is Windows-only.
disable-model-invocation: true
---

# daily

For consultants who track time across multiple clients. ActivityWatch plus a scheduled screenshot grabber (`~/Pictures/WorkScreenshots/`) capture the workday; this skill turns that into a reviewable billable timesheet and (with confirmation) posts it to Harvest.

**Read the whole Workflow section before starting a run — the guards in Steps 3 and 6 are where runs go wrong.**

## What lives where (read before adding any new fact)

This skill is **shareable** — sort every fact by who it applies to. Don't use the cross-session memory store; the skill is the single source of truth.

- **Generic mechanism** (any user) → `SKILL.md` / `references/` / `scripts/`: classification, blocking, posting, reusable heuristics, API quirks.
- **One user's facts** → `Timesheets/.context.md` (in the user's workspace, not the skill folder): clients, colleagues, signals, billing-convention *overrides*, machine specifics, CRM URLs / account GUIDs, pac profiles, prefix→client map. Read every run. Size-budgeted — see Step 11.
- **This machine and account** → declared plugin configuration, set once at install and changed with `/plugin configure billables`: Harvest credentials, `TIMESHEET_TIMEZONE`, and the optional `TIMESHEET_ACTIVITY_URL` / `TIMESHEET_SCREENSHOTS_DIR` / `TIMESHEET_WORKSPACE`. The credentials are declared sensitive, so the harness holds them in its own credential store (the OS keychain on macOS, `~/.claude/.credentials.json` elsewhere) — there is no secrets file for this skill to create, read or share. An exported install (no manifest, so no harness to ask) puts the same keys in `.env` at the skill root, gitignored; share `.env.example`, never `.env`.

When the same setting is available from more than one of those, a per-command flag wins, then `.env`, then the process environment (where the harness's values arrive), then the script's own default; blank counts as unset. `scripts/skill_config.py` carries the reasoning and is where every script resolves a setting — read it there rather than inferring the order from a script.

## When to invoke

**Strong triggers** — invoke without further confirmation: "summarise yesterday" / "what did I do on <date>" / "fill in <day>'s timesheet" / "log time for <date>" / "review today's work" / "backfill the timesheets".

**Soft triggers** — confirm first: the user mentions Harvest, ActivityWatch, `daily_exports/`, `Timesheets/` in passing; a new export landed and the user seems unsure what to do with it.

**Do NOT invoke when:**
- the user is asking about *configuring* the pipeline itself (export script, ActivityWatch setup, screenshot scheduler) — that's maintenance, not daily classification. Standing it up for the first time is the `setup` skill; `references/setup.md` is for a prerequisite that failed mid-run
- the user wants *raw* Harvest data beyond a date range ("list my projects", "monthly totals") — point at the Harvest web UI or a one-off script

## Data sources

| Source | Purpose | When to use |
|---|---|---|
| **ActivityWatch** at the configured `TIMESHEET_ACTIVITY_URL` (default `http://localhost:5600`) + `/api/0/` | Live, authoritative event stream (window titles, AFK, browser tabs) | **Primary** — but access it via the bundled scripts; query raw only per `references/activitywatch.md` |
| `daily_exports/<date>/compact.jsonl` | Pre-processed AW dump (sub-10s events pre-dropped; short keys: `b`=bucket, `t`=timestamp, `d`=duration, `a`=app, `ti`=title, `u`=url, `s`=afk) | Fallback only when AW is unreachable |
| `~/Pictures/WorkScreenshots/<date>/HH-MM-SS_mN.png` | **Source-of-truth** screenshots, ~2.5 min cadence, 08:30–20:00 weekdays | Disambiguation only — load specific timestamps, never proactively |
| `daily_exports/<date>/screenshots/` | Partial copy | Ignore; use the Pictures folder |
| `Timesheets/.context.md` | The user's attribution rules — **source of truth** for all ambiguity calls | Read every run |
| `Timesheets/<date>_timesheet.md` | Optional markdown audit trail | Format reference; create only on request |
| `.mcp/harvest_assignments*.json` | Cached Harvest project assignments (`project.id/name/code`, `client.name`, `task_assignments[]`) | Project + task IDs, via `harvest_lookup.py` |
| `.mcp/<catalog>.txt/.json` | User-specific catalogs (e.g. active-incident list) | Work-item number → title |

**Screenshot location:** `~/Pictures/WorkScreenshots/` above is the default. If `TIMESHEET_SCREENSHOTS_DIR` is configured, captures go there instead — read that path rather than the literal one in the commands below. Resolve it once, **in the Bash tool**, and reuse the answer for the whole run:

```bash
python "<this skill's folder>/scripts/screenshot_capture.py" --where
```

It prints the resolved directory and captures nothing. Quote it when you paste it into the PowerShell commands below — a configured path may contain spaces.

Do not reach for an `echo` of the setting instead. That reads the process environment, which is one of the four layers `skill_config` resolves and not the one an exported install keeps this value in: it comes back empty for a user whose capture task is writing somewhere else entirely, and you would then list the default folder and find it empty. The script applies the whole precedence, and expands a `~`.

**Timezone:** AW stores UTC; the scripts convert using the configured `TIMESHEET_TIMEZONE`, applying it at each instant rather than once for the day, so a daylight-saving change needs nothing from you — including on the day itself, which is 23 or 25 hours long and is read at that length. On the day the clocks go back, the second pass over the repeated hour is suffixed `*` (`02:30:00*`); hand it back to `--window` / `--cover` as part of the time, and see `references/output-format.md` before it reaches Harvest. **There is no assumed zone and no default offset** — a run with neither a configured zone nor `--utc-offset` stops and says so, because a guessed offset dates the day wrong without failing. `--utc-offset <hours>` still overrides it for a single run (a day spent in another zone). If a run reports it cannot *load* the zone, the machine is missing the zone database: `py -m pip install tzdata`.

**Running the scripts:** every `python scripts/…` command below is relative to *this skill's own folder* — the directory this `SKILL.md` was read from — not the workspace. The session's working directory is the workspace, so prefix them with that folder's absolute path: `python "<this skill's folder>/scripts/afk_blocks.py" <date>`. **Resolve the folder once, with the Prerequisites below, from where you read this file, and reuse it for the whole run** — never assume a literal location. It differs by install (inside a plugin's own directory, a shared Agent Skills directory, or a harness's skills directory) and a guessed path fails as "script not found", which reads like a broken skill rather than a wrong prefix. Catalog paths resolve from the workspace, so run them *from* the workspace directory.

**Run them through the Bash tool, and read every configured value there too.** Claude Code publishes the declared configuration as a POSIX shell fragment and applies it to **Bash** tool calls alone — the PowerShell tool is given no equivalent and loads no profile, so `$env:TIMESHEET_TIMEZONE` is empty there however well the machine is configured. A script run through PowerShell now says which shell to re-run in rather than sending you to reinstall anything, but that is a wasted round trip. Where a command genuinely has to be PowerShell — the screenshot listing below, `setup_screenshot_pipeline.ps1` — **resolve the value in Bash first and put the literal into the PowerShell command**; reading it in PowerShell finds nothing and silently uses the default instead, which is a folder the user does not capture into.

`python` in those commands means *the interpreter this machine actually uses*, not the literal string. Check `.context.md` first — if it records one, use it and don't re-probe. Otherwise resolve it once with the Prerequisites below and reuse it for the whole run. On Windows a bare `python` is often the Store app-execution stub, whose tell is a **help message about installing from the Microsoft Store and exit code 49** — that is a missing interpreter, not a broken script, so don't debug the script. `py` (the launcher) is the usual working answer there. Record the resolved answer in `.context.md` → Machine so the next run skips the probe.

### Reading the screenshot folder (Windows)

List with PowerShell `Get-ChildItem` — the Bash `cmd dir` and `Glob` routes return empty for the `Pictures` path even when it's full:

```powershell
Get-ChildItem "$HOME\Pictures\WorkScreenshots\2026-05-29" -Filter *.png | Sort-Object Name
```

Each capture tick writes **one PNG per monitor** (`HH-MM-SS_m1.png`, `_m2.png`, … left-to-right, native resolution). Laptop-only days have just `_m1`. On multi-monitor days read the monitor showing the active app — and check the *other* monitors too whenever the answer matters, which is both "which client is this" and "is anything happening at all". **A capture showing wallpaper, a lock screen or a black screen is evidence about that monitor and nothing else** — never about whether the user was working. `references/classification-rules.md` § "Focused window ≠ active attention" owns why, and the AFK watcher owns active/idle regardless. Days captured before mid-2026 may hold single stitched `HH-MM-SS.png` files. Filenames are local time; filter by name prefix to find the capture nearest a timestamp, then `Read` the PNG normally.

**Byte size triages which captures to open, and settles nothing.** A capture of a black or locked screen lands around 6-7 KB, so `Get-ChildItem`'s `Length` column cheaply ranks a long index before you spend image tokens on it. Two limits, both observed: a large file can be a detailed *wallpaper photo* rather than app content (3.7 MB of seals, 2026-08-21), so size never confirms work either; and a run of near-identical sizes means those pixels didn't change, which is a fact about one monitor's screensaver, not about the user. Open the image before you conclude anything from it.

## Prerequisites — check at start of every run

Run in parallel before classifying anything. If any first-run piece is missing (no workspace, no `.context.md`, unconfigured credentials or timezone, no screenshot task, unknown AW buckets), follow `references/setup.md` — which is also where the `setup` skill hands over when it says this skill scaffolds the workspace.

1. **`Timesheets/.context.md` — read it, whole, every run.** If missing, run first-run setup; don't classify without it. **Read the entire file into context; never grep it, never read a slice of it, never skim to the section you think you need.** Its facts are cross-cutting — an exclusion in one section decides a block whose client is named in another — so a partial read produces confident wrong answers rather than an obvious gap. The Step 11 size budget exists precisely so this file always fits in one read; if it has grown past budget, fix the budget (Step 11), don't switch to reading part of it.
2. **ActivityWatch reachable** — `curl -s <activity-url>/api/0/buckets/` returns JSON, where `<activity-url>` is the configured `TIMESHEET_ACTIVITY_URL` or `http://localhost:5600` if unset. Use the configured one: probing localhost on a machine that reads a remote AW reports the instrument dead when the scripts would have worked. If not, fall back to `daily_exports/<date>/compact.jsonl`; if both missing, the day can only be reconstructed from screenshots + user memory — say so explicitly.
3. **AW bucket ids resolved** — from `.context.md` if cached, else discover and offer to cache.
4. **Catalogs fresh** — the assignment catalog (`.mcp/harvest_assignments*.json`) + any work-item catalogs modified within 7 days; else run `scripts/refresh_catalogs.py` (details: `references/catalog-refresh.md`). Surface a >30-day gap to the user before refreshing, unless `.context.md` preferences say refresh silently.
5. **Harvest credentials work** — `python scripts/harvest_list.py <today> <today>` runs without auth error. "credentials not found" → `references/setup.md`; `401/403` → PAT revoked, user must regenerate.

**Tunable defaults** (override via `## Preferences` in `.context.md`): AFK break threshold `1050s` (17.5 min); substantive-activity floor `120s`; end-of-day blip gap `600s`; smallest uncovered stretch worth flagging `900s`; active/thin bands `0.7`/`0.4`; timeline noise floor `5s`, gap fold `60s` and minimum displayed span `3.0 min`; minimum billable block `0.25 hr`; lunch window `11:30–14:30`; work-hours rendering window `06:00–20:00`. **The task names have no default and cannot have one** — the rubric decides a *work kind*, and `.context.md` § "Work kinds" maps each one to the task the user's own provider offers. With no mapping there yet — every install predating that table — the rubric matches the work kind against the project's own `task_assignments[]` rather than guessing a name, and proposes the row at Step 11. A guessed task name is not a task the provider has.

Where `## Preferences` names a value that differs from the default, **pass it on the command line** — each entry in the template carries the flag it maps to. Never edit a constant in `scripts/`: an update overwrites it, silently reverting a preference the user set once and expects to hold.

## Workflow

### Step 1 — Resolve target date and scope

If the user gave a date, use it — then immediately **check whether that date is already billed** (below) before loading anything else. Otherwise: list existing entries (`harvest_list.py`) for the past ~10 days, cross-reference against `~/Pictures/WorkScreenshots/<date>/` (most reliable date index) or `daily_exports/`, and pick the days with activity but no/partial Harvest entries. **Today is always "in progress" on a no-date run — it is not a reason to ask.** Default to the oldest fully-unbilled *prior* day and mention today's partial state separately. No gaps → "all caught up" (offer today-so-far).

**One date per session.** "Backfill the timesheets" scopes the *goal*, not this run. On a no-date run, report the whole gap list, then work only its oldest entry; Step 12 hands the rest to a fresh session.

**Check the target date against Harvest before rebuilding it — on *every* run, dated or not.** `harvest_list.py <date> <date>` costs one call; `Timesheets/<date>_harvest_responses.json` sits beside it as a free done-marker — and, on the already-covered branch below, as the record of what was already decided. Do this *before* Step 2 loads the skeleton, the timeline and the screenshot index. Nothing downstream will save you: Steps 3, 6 and 8 all check the proposal against ActivityWatch, never against Harvest, so a duplicate day passes every guard in this file and double-bills the client.

- **Already covered** → say so, and *verify* rather than redraft: run Step 6's `--cover` against the existing entries and check the unbilled stretches are genuinely under the `<0.4` band. **Both of those are time questions and neither can see an entry booked to the wrong client** — right clock, wrong project passes `--cover` perfectly. So also read one screenshot inside every **non-billable or internal** entry and confirm the screen matches what the entry claims; those are the ones that silently move time off a client. Report what you found; propose changes only where the evidence contradicts an entry.
  - **Read `Timesheets/<date>_harvest_responses.json` whole before proposing any change to that day** — the same rule as `.context.md` in Prerequisite 1, and for the same reason: its schema is ad hoc (`exclusions`, `notes`, `judgment_calls`, `declared_judgments`, free-text keys invented per run), so there is no key to look under and a partial read returns a confident wrong answer rather than an obvious gap. It holds the *reasons* the day looks the way it does.
  - **A ruling the user already gave on a window binds, and re-deriving the evidence does not reopen it.** An entry the user asked for, extended, or confirmed is settled; a fresh `active_ratio`, a fresh screenshot read, or a fresh look at the timeline is the *same* argument run again on the same data, not new evidence. Recompute all you like — then, if the file records a decision on that window, say the recomputation disagrees and leave the entry alone. Only genuinely new information (the user says they misremembered, an entry contradicts a *different* entry) reopens it. This branch's job is finding what nobody has looked at yet.
  - **Proposing a *reduction* — a delete, a trim, a repoint — pulls in `references/classification-rules.md` first.** This branch deliberately skips the rubric to avoid redrafting, which is right while you are verifying and wrong the moment you start subtracting: the guards against over-reading a thin block (supervised agents, meetings invisible to the window watcher, browser rows that span hours) all live there, and without them a low `active_ratio` reads as an idle window that isn't one. Cheaper than an unwarranted deletion.
- **Partly billed** → treat the billed windows as fixed and scope this run to the gaps, unless the user says otherwise.
- **Nothing there** → carry on into Step 2 as normal.

Convert relative dates ("yesterday", "Friday") using today's date in the user's timezone.

**Honor partial-day scope:** "only do the morning" / "I've filled in after 12:40" restricts classification to that window — don't propose blocks outside it.

### Step 2 — Load inputs

Read in parallel:
- `Timesheets/.context.md` — the **whole** file (Prerequisite 1), if you have not already read it this run
- `references/classification-rules.md` (the classification rubric — client, project, **work kind and task selection**, interleaved-day protocol)
- Cached catalogs from `.mcp/`
- `python scripts/afk_blocks.py <date>` — the day skeleton (work_start, work_end, breaks, active spans)
- `python scripts/activity_timeline.py <date>` — merged window spans tagged with the AW client category, plus per-category rollup. **Compact output is the default and is enough** — do NOT reach for `--full` routinely; zoom specific blocks later with `--window HH:MM-HH:MM`. Loading the full raw timeline for a mostly-single-client day is the main cause of context bloat.
- Screenshot index: list `~/Pictures/WorkScreenshots/<date>/` filenames (PowerShell, per above). Don't open PNGs yet.
  - **Compare the last capture's timestamp against `work_end` before moving on.** A short index is ambiguous on its own — it looks the same whether the user stopped working or the capture died mid-day — and `work_end` is what separates the two. If captures stop well before `work_end`, say so *now*, in the Step 6 skeleton line, and treat every block after that point as having no screenshot fallback: those are the blocks that will need the user, so flag them 🔸 on weaker evidence than you otherwise would. Finding this out at Step 5, when a block is already ambiguous, is too late to plan around.
  - A dead capture task is *maintenance*, not classification — don't fix it mid-timesheet. Note it, finish the day, raise it at Step 11. `references/setup.md` has the health check.

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

These rules apply identically when **backfilling an older date** — trailing left-in-focus windows are *more* likely there.

### Step 4 — Classify each block

For each block determine its attribution — **client + project + task + billable + confidence (high/medium/low)** — per `references/classification-rules.md`. Mechanics:

- The AW category from the timeline is a client-level first pass only — never project/work-item-level, never 100%. Investigate every `uncategorized` and `!MULTI` span.
- Work-item-shaped strings (`[A-Z]{2,4}\d{3,}S?`) in titles/URLs are the highest-confidence signal: resolve the title in the user's work-item catalog and the project/task via `python scripts/harvest_lookup.py <code-name-or-client>` — it searches ALL catalog pages and falls back to the user's recent entries for archived projects. Never hand-roll a glob loop (it reads one page and misses projects). **A client's name is a first-class search term, and the top hit is not automatically the right project:** the live delivery project is often named for the *work* and matches only on `client.name` (reported as `matched_on: client`, ranked last), while a dead presales or shell project named after the client ranks above it. Read all candidates before picking — an all-non-billable task set is the tell for a shell. Trailing `S` = Support: tag the description `[Support]`, same project/task selection.
- **Task selection and billable status: follow the rubric's "Work kind and task selection" section exactly** — `.context.md` overrides first, then the block's dominant activity gives a work kind, then `.context.md` § "Work kinds" turns that into the user's own task name. Billable comes from `task_assignments[].billable`, never from the task name.
- **If the day shows more than one client, or a block is titled by an agent-session file (`CLAUDE.md`, `AGENTS.md`, plan `.md`s): apply the rubric's "Interleaved days" protocol before accepting any block over an hour.** This is the single largest source of real misattributions.

### Step 5 — Disambiguate flagged blocks

For any 🔸 block (low confidence, thin ratio, or ambiguous attribution):

- **AFK status is settled by the AFK watcher** — never re-infer active/idle from screenshots. Screenshots and zooms answer only *which client/project*.
1. **Zoom the timeline first:** `python scripts/activity_timeline.py <date> --window HH:MM-HH:MM` folds in Firefox/Chrome web-watcher rows — richer URL/title signals without opening images.
2. **Then screenshots**, for generic apps that don't name their client (XrmToolBox, bare VS Code, terminals): find the nearest `HH-MM-SS_mN.png` to the ambiguous timestamps, read the env URL / workspace / repo / work item on screen. Different clients in different screenshots within one block → split the block (switch-point protocol).
   - **When several blocks need screenshot-checking, delegate the reading to a cheap subagent** (e.g. `Agent` with `model: "haiku"`) rather than reading every capture in the main session — image tokens add up fast once a date needs more than a couple of captures, and this is a plain read-what's-on-screen task a smaller model handles fine. Give the subagent no conversation context of its own, so its prompt must carry: the screenshot directory and exact timestamps to check (all monitors — `_m1`/`_m2`/…), the signal list from `.context.md`, the AFK-settled rule above, and classification-rules.md's "Interleaved days" probe-economically procedure (3 spread, densify around flips) if any block needs a switch point. It reports **raw signals per capture** (app, environment URL, ticket numbers, Edge profile, workspace) — never a billing verdict; attribution against `.context.md` stays with the main session.
3. **Still ambiguous → ask the user**, showing which screenshots you checked, what you saw, and the candidate clients.
- **Never silently bill an abandoned-task block.** Setup/sign-in/install work that ended without a client deliverable and a pivot elsewhere → surface it; default to internal-admin non-billable unless the user says otherwise.

### Step 6 — Present the proposed timesheet

Render in the user's format:

```markdown
| Time | Duration | Client | Description |
|------|----------|--------|-------------|
| 08:12–08:46 | 0.5 hrs | <Client> | <Description with work item # if any> |
```

Flag uncertain blocks 🔸 below the table. End-of-day and breaks are deterministic; *which client / billable / where to split* is judgment — flag it rather than committing silently. The user's review is what makes the sheet accurate, so make uncertain calls easy to see.

**Three hard guards — all mandatory before presenting:**

1. **Outer block edges are the script's spans, transcribed verbatim.** A block starts at an active-span start and ends at a break start / `work_end` — don't hand-tidy or merge those edges. *Interior* splits (classification boundaries at a client switch, meeting, or work-item change) are allowed and expected — they must sit strictly inside a script span and be evidence-based, and adjacent sub-blocks must tile the span exactly. **"Tile the span exactly" governs adjacent *billed* sub-blocks.** A stretch excluded under Step 3's `<0.4` band is declared as a known exclusion under the table (guard 3), not tiled over — removing it is not inventing a break, and the blocks either side keep their evidence-based edges. This matters most on a day with no breaks at all, where the span is the whole day and its ratio can pass `≥0.7` while hiding stretches that are nearly dead. Shrunk-and-re-merged thin blocks (Step 3) are the one sanctioned exception to verbatim edges. Entries post as start/end times and Harvest derives the hours — the Duration column is informational, so don't distort boundaries to make durations land on neat quarters; the only hard rule is no entry under 0.25 hr. If an outer edge doesn't match a script span (and isn't a documented shrink), that's a transcription bug, not a judgment call.
2. **No block ends after `work_end`.** Shrink any that do.
3. **Logged blocks must cover the active spans.** Pass *every entry Step 9 will post* — post-shrink, non-billable ones (standups, internal admin, machine setup) included, since they account for active time just as billable ones do. A stretch you are *excluding* is declared under the table as a known exclusion and never passed here: feeding it to `--cover` makes the guard report clean while the under-billing it exists to catch goes unnoticed.
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

- [ ] `--cover` run and clean (no unexplained UNCOVERED) — pass **every entry Step 9 will post, non-billable ones included**; a stretch you're excluding is declared under the table, never fed to `--cover` to make it look covered
- [ ] Skeleton still current — if the day was still in progress when you read it, or the session has since crossed midnight, re-run `afk_blocks.py <date>` before posting. An open day's `work_end` advances and late spans appear, which moves both the final block's end and the coverage denominator
- [ ] No block past `work_end`; no block crossing a script break
- [ ] Every `project_id`/`task_id` came from `harvest_lookup.py`; billable flag checked
- [ ] Work kind = the block's dominant activity per the rubric, and the task name came from `.context.md` § "Work kinds" or from this project's own `task_assignments[]` — never from memory; `.context.md` overrides applied
- [ ] Every Harvest note passes the client-readability test (Non-negotiables below)
- [ ] All 🔸 blocks resolved with the user
- [ ] `.context.md` exclusions applied (personal browsing, recurring internal items)
- [ ] **The date isn't already billed** — re-confirm Step 1's Harvest check still holds. Every other line above compares the proposal against ActivityWatch; this line is the checklist's comparison against Harvest, and the cost of skipping it is double-billing a client

Then show:

> "Ready to post to Harvest. This will create N time entries:
> - 0.5 hrs · [Northwind Consulting Ltd] · Northwind Internal — Team Standup
> - 0.75 hrs · [Beta Industries] · BET2020S Beta Fabrics Copy job — Investigation [Support]
>
> Proceed? (yes / no / edit block <n>)"

**An explicit "yes" or equivalent is what earns `--confirm` in Step 9** — without that flag the posting scripts write nothing and print what they would have posted instead, so anything short of a yes simply leaves it off. Edits loop back to Step 6.

### Step 9 — Post to Harvest

For each confirmed block, serially (so the user can interrupt):

```
python scripts/harvest_post.py <project_id> <task_id> <YYYY-MM-DD> <HH:MM> <HH:MM> '<notes>'
```

- **Append ` --confirm` to that command once Step 8 has the user's yes.** The template leaves it off on purpose: without the flag the script prints `WOULD POST <body>` and exits 0 having created nothing, so a command copied straight from here bills nothing until someone adds it deliberately. A run that comes back `WOULD POST` has *not* billed the block — re-run it with the flag, and never record it as posted.
- Times: 24h (`16:05`) or 12h (`4:05pm`) both accepted.
- **Single-quote the notes** — money amounts (`$5k`), backticks, and shell-shaped substrings get mangled otherwise.
- Success prints `OK <entry_id>` — capture it for Step 10. Failure prints `ERR <status> <body>` and exits non-zero — stop and surface, don't retry silently.
- The script always sends `started_time`+`ended_time`, never bare `hours`: in a start/end-time Harvest account, bare `hours` starts a running *timer*. Passing times works in either account mode.
- **On the day the clocks go back, a block worked straight through the change is refused** — Harvest bills the difference between the two clock times, which is short by however long the clocks repeated (an hour in most zones; the `ERR` states it). It names the two entries to post in its place and why they are not the overlap they look like; post both, and do not close the overlap. `harvest_patch.py` refuses the same entry, judged on what the patch would leave behind — so correcting a block onto that morning meets the same message, and the fix is the same two entries: patch the one you have to the first, post the second. Do that rather than reaching for `--hours`: the guard lets `--hours` through (a duration-mode account has no other way to correct such an entry) but on a start/end-time account, which is the usual one, it does not do what it looks like — see the script's module docstring. `references/output-format.md` §Conventions has the cases the refusal cannot see, where a block touches the repeated span rather than straddling it.
- After each post log: `✓ Posted: <hours> hrs · <project.code> · <task>`.

Fix a wrong entry with `python scripts/harvest_patch.py <entry_id> [--start HH:MM] [--end HH:MM] [--notes "..."] [--hours N] [--project-id N] [--task-id N] [--date YYYY-MM-DD] [--confirm]` (≥1 field flag; same OK/ERR convention, same gate — it previews as `WOULD PATCH <entry_id> <body>` until `--confirm` is added). A patch overwrites a line the user already approved, so it needs its own yes; Step 8's covers the entries it listed, not a later correction to one.

**Block belongs to brand-new client work with no project yet** → follow `references/new-client-work.md` (create the backend work item, post other blocks now, bill the deferred one when the synced project appears).

### Step 10 — Wrap-up

Summarise: total hours posted, blocks deferred/skipped, and whether more days are outstanding — but **don't name the next date here**; Step 12 does that after the reset ask. Save the entry ids to `Timesheets/<date>_harvest_responses.json`: `{"entries": [{"id": 2933345845, "project_code": "NWC-001", "hours": 0.25, "notes": "..."}], ...}`.

### Step 11 — Surface skill or `.context.md` improvements

A run frequently reveals a fact the skill or `.context.md` doesn't know (a new signal you had to guess, a convention that turned out wrong, an offline watcher). Collect them and present at the end:

- *This user's* clients/colleagues/signals/preferences → propose for `.context.md` (most additions).
- The *workflow itself* (a generic heuristic, data-source change, API quirk) → propose for `SKILL.md`/`references/`.
- The *skill is wrong* — a script returns a wrong answer, a guard didn't fire, an instruction is wrong for every user → `references/reporting-issues.md` if the user installed this skill, `references/self-development.md` if they maintain it.

Show the exact diff, one fact per ask. Example: "The XrmToolBox signal isn't in `.context.md`; I guessed Ledger Learning. Add `XrmToolBox connecting to env X → Ledger Learning` under Ledger Learning?"

**`.context.md` size budget — check after every edit to it.** `(Get-Item Timesheets/.context.md).Length` must stay under **14,000 bytes** (override via `## Preferences`). The budget exists to keep Prerequisite 1's whole-file read affordable on every run — that is what it is *for*, so a file over budget gets trimmed, never partially read. Over budget → compact in the same session, in this order: (1) move any *generic* rule that crept in into this skill's references — that's skill drift, not a user fact; (2) delete facts proven wrong or superseded (finished workstreams, retired clients, one-off work-item examples older than a few months); (3) shorten confirmed-example parentheticals to the date stamp. If getting under budget would drop a live user fact, ask the user which to drop — never silently delete.

### Step 12 — One date per session, then reset

**Finish one date per session and stop.** The date is done when nothing is left to post (Step 9 posted it, the user declined at Step 8, or the run had no Harvest write in scope), Step 10 has wrapped up, and every Step 11 proposal is written or declined — a reset mid-follow-up loses those proposals. A date the user deliberately scoped to part of the day is **not** done: the rest of it is unfinished business on this date, not a next day.

**Then, only if days remain**, ask for the reset *before* naming the next date. Say where this date landed, that days are outstanding, and ask the user to run `/clear` before the next one — this date's blocks, client mix and resolved ambiguities read like evidence for the next date.

- **Today-so-far counts as a next date.** Starting a fresh date is what triggers the ask, whether that date is an old gap or the rest of today. Step 1's "today is in progress, not a reason to ask" governs *date selection* on a no-date run; it does not exempt today from the reset.
- **Say to re-invoke the skill, in the same breath as `/clear`.** It is not model-invocable, so a bare "do Thursday" in the cleared session runs with none of these guards. Dropping this makes the reset actively worse than not resetting.
- **All caught up → say nothing about resetting.**
- **You may not know whether days remain.** Only a no-date run builds the gap list (Step 1); on "do Friday" you never swept for one. Ask the user — don't run an unrequested sweep to find out. A month-wide answer is the `reconcile` skill's, and it is the user's to invoke.
- **Won't clear → ask for `/compact`.** Weaker: it carries this date's conclusions forward, but it drops the raw timelines, screenshot reads and catalog dumps.
- **Declines both → do as they ask**, and say once that the next date will be read against this one's conclusions.
- You cannot run either; the user does. **Don't open the next date in the same turn as the ask** — "yes, do Thursday next" is not permission to skip it. Proceed once they have reset, or declined both.

## Non-negotiables

- **No Harvest write without explicit confirmation.** `harvest_post.py` and `harvest_patch.py` write only when passed `--confirm`. Never type that flag on a yes you don't have — a posted entry is not recoverable from your side.
- **Honor `.context.md` exclusions** — personal browsing, AFK breaks, personal home admin are NEVER billable.
- **Don't fabricate confidence.** A block that could be 2–3 clients gets surfaced, not arbitrated.
- **Entry notes are client-readable.** They go out on invoices: describe *what part of the client's project* was worked on, never the internal mechanism, file names, internal app names, or chat partners. If a term wouldn't appear in the SOW or on the client's own board, it doesn't go in the note. Work-item numbers (`ACM2232S`) and recurring meeting names are fine. The markdown timesheet stays internal and can be granular. Style defaults: the rubric's "Writing the entry note" section; the user's own examples in `.context.md` "How I bill".
- **`.context.md` is the source of truth for per-user facts** — propose new user facts there, not in the skill.

## Files in this skill

- `SKILL.md` — this file
- `.env.example` / `.gitignore` — Harvest credential template (copy to `.env`, gitignored)
- `references/setup.md` — first-run setup: screenshot task, `.context.md` creation, Harvest creds, AW discovery, AW category maintenance
- `references/context.md.example` — starter template for `Timesheets/.context.md`
- `references/classification-rules.md` — client/project/**work kind** rubric + interleaved-day switch-point protocol
- `references/activitywatch.md` — raw AW API reference (endpoints, buckets, heartbeat dedupe, lock-screen quirk)
- `references/output-format.md` — timesheet .md template
- `references/catalog-refresh.md` — refreshing `.mcp/` catalogs
- `references/new-client-work.md` — billing work that has no project yet (Dataverse case creation)
- `references/reporting-issues.md` — reporting a defect upstream when the user installed this skill rather than maintaining it: the repo, what to redact first, and the confirmation gate before filing
- `references/self-development.md` — **for changing this skill, not for running it.** Start here before editing `SKILL.md`, a reference, or a script: where maintenance content goes, which instruments to test against, the rules that have more than one copy, and where the release ritual lives. Ignore it on a normal run.
- `TESTING.md` — the record behind those decisions: test results, evidence rungs, and options already tried and rejected. Read it so you don't re-add something that was measured unnecessary; new findings go here, not in `SKILL.md`.
- `scripts/afk_blocks.py` — deterministic day skeleton: work_start/work_end/breaks/active spans/active_ratio; `--window`, `--json`, `--utc-offset`, `--cover "HH:MM-HH:MM,..."` coverage check, plus the `## Preferences` tunables `--afk-threshold`, `--solid`, `--blip-gap`, `--min-uncovered`, `--active-band`, `--thin-band`
- `scripts/activity_timeline.py` — categorized window timeline + rollup; `--window HH:MM-HH:MM` zoom folds in web watchers; flags `uncategorized`/`!MULTI`; `--utc-offset`, `--json`, `--noise-floor`, `--gap-fold`, plus the two that control how much of the day you get back: `--full` shows every merged span, and `--min-span` sets the shortest span the compact default prints in minutes (`--min-span` is the `## Preferences` tunable `references/context.md.example` maps onto). Hidden spans are still counted in the per-category rollup, so the totals do not move
- `scripts/aw_client.py` — shared ActivityWatch REST helpers behind `afk_blocks.py` and `activity_timeline.py`, plus the server address (`TIMESHEET_ACTIVITY_URL`) both of them need. *When* a day is read is the next entry's, not this one's
- `scripts/timezone.py` — the zone a day is read in (`TIMESHEET_TIMEZONE`) and the clock arithmetic that follows from it: the day's UTC bounds, the local-clock rendering and the range parsing behind the window and coverage flags above, and where on a date the clocks change. Not a script, and not either half's: the two reading scripts above and the two writers below all import it, and its conversions apply the offset in force at each instant rather than one read once for the day, which is what makes the day the clocks change 23 or 25 hours long instead of silently short
- `scripts/harvest_lookup.py` — project/task id lookup across ALL catalog pages by code, project name **or client name**, live-entry fallback for archived projects (a miss after the fallback = genuinely unknown project; a cache refresh won't help); `--task`, `--mcp-dir`, `--json`, `--no-live`, `--days`
- `scripts/harvest_post.py` / `harvest_patch.py` / `harvest_list.py` / `harvest_write.py` — create / update / list time entries (`OK <id>` / `ERR …`). The two that write take `--confirm` and do nothing without it, printing `WOULD POST` / `WOULD PATCH` and the body instead; `harvest_write.py` is not a script but where that gate, the preview and the `OK` / `ERR` contract are implemented, which both writers declare their body to. Both writers read `TIMESHEET_TIMEZONE` to refuse an entry that runs straight through a daylight-saving change, which Harvest would bill short by the repeated span — Step 9 has what to do with that refusal. `harvest_patch.py` refuses the entry its patch would *result* in, so `--start` alone, `--end` alone and `--date` alone each reach it; that costs one read of the entry, which it skips where nothing in the patch could move a clock and on any date the clocks do not repeat. The patch fields are `--start HH:MM`, `--end HH:MM`, `--notes`, `--project-id`, `--task-id`, `--date YYYY-MM-DD` and `--hours` — at least one is required, and PATCH semantics mean only what you pass changes. Prefer `--start` **and** `--end` together to change a duration: pass one alone and Harvest recomputes hours against the unchanged side, and `--hours` on a start/end-time account (which is the usual setup) leaves the entry inconsistent or converts it to a running timer. The script's module docstring carries both traps in full. `harvest_list.py <from> <to> --by-day` collapses the listing to one row per date — total, entry count and project codes, with a row for every date in the range including the empty ones; that is the month sweep the `reconcile` skill runs, and it is also the cheapest way to see a fortnight's gaps at Step 1
- `scripts/skill_config.py` — the seam every script reads a setting through; its docstring carries the flag / `.env` / environment / default precedence and the reasoning behind it
- `scripts/harvest_client.py` — shared Harvest API helper + the credentials contract
- `scripts/refresh_catalogs.py` — refresh `.mcp/harvest_assignments*.json` + incident catalog; `--harvest-only` / `--dataverse-only` do one of the two (they are mutually exclusive, and the default is both); `wait_for_project(<code>)` for new synced projects
- `scripts/screenshot_capture.py` (`--where`) + `scripts/setup_screenshot_pipeline.ps1` — per-monitor capture + one-time scheduled-task setup. `--where` prints the resolved capture directory and captures nothing; it is how you get that path for a PowerShell command, per "Screenshot location" above
- `tests/` + `pytest.ini` — the script suite. Maintainers only; `references/self-development.md` explains what it does and does not measure.
