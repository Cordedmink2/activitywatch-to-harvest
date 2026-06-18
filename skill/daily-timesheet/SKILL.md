---
name: daily-timesheet
description: Reconstructs the user's workday from ActivityWatch + screenshots, classifies activity into client time blocks, presents them for human review, then posts confirmed entries to Harvest via bundled scripts (`scripts/harvest_post.py`, `scripts/harvest_patch.py`, `scripts/harvest_list.py`). Use whenever the user wants to remember what they did on a given day, fill in a timesheet, log time to Harvest, summarise yesterday, review today's work, regenerate a missing timesheet, or backfill the gap between the most recent `Timesheets/<date>_timesheet.md` and the latest `daily_exports/<date>/`. Auto-relevant when the user mentions Harvest, ActivityWatch, daily_exports, Timesheets/, or any date-scoped "what did I do" question, even if they don't explicitly say "timesheet". Targets a workspace containing `Timesheets/.context.md`, `daily_exports/`, and `.mcp/` catalogs — the user supplies these on their own machine.
---

# daily-timesheet

For consultants who track time across multiple clients in a single tenant. A live ActivityWatch event stream plus a scheduled screenshot grabber (`~/Pictures/WorkScreenshots/`) capture the workday; this skill turns that raw activity into a reviewable, billable timesheet and (with confirmation) posts it to Harvest.

## What lives where (read before adding any new fact)

This skill is **shareable** — sort every fact by who it applies to. Don't use the cross-session memory store; the skill is the single source of truth.

- **Generic mechanism** (any user) → `SKILL.md` / `references/` / `scripts/`: classification, blocking, posting, reusable heuristics, API quirks (Harvest replica-lag, start/end-time rule).
- **One user's facts** → `Timesheets/.context.md` (in the user's workspace, not the skill folder): clients, colleagues, signals, billing conventions, machine specifics, CRM URLs / account GUIDs, pac profiles, prefix→client map. Read every run.
- **Secrets** → `.env` (skill root, gitignored): Harvest creds. Share `.env.example`, never `.env`.

## When to invoke

**Strong triggers** — invoke without further confirmation:
- "summarise yesterday" / "what did I do on <date>" / "what was I working on Friday"
- "fill in <day>'s timesheet" / "do my timesheet for <date>"
- "log time for <date>" / "post my Harvest time for <date>"
- "review today's work" / "remember what I did <date>"
- "backfill the timesheets" / "catch up on time tracking"

**Soft triggers** — confirm before invoking:
- the user mentions Harvest, ActivityWatch, `daily_exports/`, `Timesheets/` in passing
- A new export landed and the user seems uncertain what to do with it

**Do NOT invoke when:**
- the user is asking about *configuring* the pipeline itself (export script, ActivityWatch setup, screenshot scheduler) — that's pipeline maintenance, not daily classification
- the user is asking to fetch *raw* Harvest data beyond a date range ("list my projects", "what hours do I have for the month") — that's outside this skill's scope; point the user at the Harvest web UI or write a one-off script

## Data sources

| Source | Purpose | When to use |
|---|---|---|
| **ActivityWatch HTTP API** at `http://localhost:5600/api/0/` | Live, authoritative event stream. Window titles, AFK status, browser tab URLs, VS Code editor activity | **Primary**. Use whenever the local AW service is running |
| `daily_exports/<YYYY-MM-DD>/compact.jsonl` | Pre-processed AW dump (sub-10s events dropped, short keys: `b`=bucket, `t`=ISO timestamp, `d`=duration secs, `a`=app, `ti`=title, `u`=url, `s`=afk status) | Fallback for historical days only; query ActivityWatch live for current days |
| `~/Pictures/WorkScreenshots/<YYYY-MM-DD>/HH-MM-SS.png` | **Source-of-truth** screenshots (~2.5 min cadence, **08:30–20:00 weekdays**), captured by the bundled `scripts/screenshot_capture.py`. Covers the whole workday including evenings | **Use this folder for all screenshot lookups.** Disambiguation only — load specific timestamps when AW is ambiguous; don't load proactively. List it with PowerShell `Get-ChildItem` (see note below) |
| `daily_exports/<YYYY-MM-DD>/screenshots/HH-MM-SS.png` | Partial copy, historical days only | Ignore; use the Pictures folder above |
| `Timesheets/.context.md` | User-maintained client attribution rules — internal-colleague names, Edge-profile → client mapping, exclusions, preferences. **Source of truth** for all ambiguity calls | Read every run |
| `Timesheets/<YYYY-MM-DD>_timesheet.md` | Optional markdown output (users don't always want this — ask if unclear). Existing files are a reference for format + tone | Format reference; create only if the user asks for the markdown audit trail |
| `.mcp/harvest_assignments*.json` | Cached Harvest project assignments (the user's `/users/me/project_assignments` paginated). Has `project.id`, `project.name`, `project.code`, `client.name`, `task_assignments[]` | Look up project + task IDs |
| `.mcp/<catalog>.txt` or `.json` | Optional user-specific catalogs (e.g. a Dataverse incident list, a Jira/Linear ticket dump). Surfaced when ticket-number resolution is needed | Resolve ticket-number → title |

### ActivityWatch quick reference

- Discover buckets: `GET http://localhost:5600/api/0/buckets/` returns `{bucket_id: {...}}`. The hostname-suffixed buckets (e.g. `aw-watcher-window_ACL-113359`) are the live ones.
- Pull events: `GET http://localhost:5600/api/0/buckets/<bucket_id>/events?start=<ISO-UTC>&end=<ISO-UTC>&limit=10000`. Events have `timestamp` (UTC), `duration` (seconds), `data` (varies by watcher).
- Time zones: AW stores everything in UTC. Compute the UTC range from the user's *local-midnight* boundaries. Example for `2026-05-13` in NZST (UTC+12): `[2026-05-12T12:00:00Z, 2026-05-13T12:00:00Z]`. Read the user's timezone from `## Preferences` in `.context.md`; default to `Pacific/Auckland` if absent. Watch for DST transitions in their offset.
- Useful buckets to query in parallel (`<host>` is the user's machine hostname — discover via the buckets endpoint):
  - `aw-watcher-window_<host>` — `data.app`, `data.title`. Primary classifier signal.
  - `aw-watcher-afk_<host>` — `data.status` is `"afk"` or `"not-afk"`. Primary break-detection signal (see Step 3 thresholds).
  - `aw-watcher-web-firefox_<host>` — `data.url`, `data.title` for Firefox tabs. Full URLs expose ChatGPT project slugs, Azure DevOps paths, SharePoint URLs.
  - `aw-watcher-web-chrome_<host>` — same shape for Edge/Chrome tabs.
  - `aw-watcher-vscode_<host>` — exact files/projects open in VS Code (when watcher is enabled — may be stale).
- Filter: drop events with `duration < 5` to remove tab-switch noise.
- **AW emits "heartbeat" updates.** A single ongoing activity often shows up as multiple events with the *same* `timestamp` but progressively longer `duration` — AW extends the existing event as time passes. When binning or counting, dedupe by `(timestamp → longest duration)` rather than summing across the duplicates, or you'll double-count.
- **`data.app == "unknown"` (or empty `data.title`) usually means the screen is locked** — Windows replaces the foreground app with `LockApp.exe`, which AW logs as `unknown`. AFK watcher will also be `afk` for the same window. Don't bill these spans; they're either short interruptions (fold-in per Step 3) or real breaks.

### Reading the screenshot folder (Windows)

List and locate screenshots with PowerShell `Get-ChildItem` — the Bash `cmd dir` and `Glob` routes return empty for the `Pictures` path even when it's full, so trust `Get-ChildItem`:

```powershell
Get-ChildItem "$HOME\Pictures\WorkScreenshots\2026-05-29" -Filter *.png | Sort-Object Name
```

Files are `HH-MM-SS.png` in local time; filter by name prefix to find the one nearest a timestamp. Once you have a path, `Read` opens the PNG normally.

## Setup (first-run + ongoing)

This skill is **shareable across users**. Each user maintains their own `Timesheets/.context.md` describing *their* clients, colleagues, billing conventions, and personal preferences. The skill itself stays generic; `.context.md` carries the personal facts.

**Screenshot grabber (one-time, per machine).** The skill bundles its own capture pipeline so a new user can stand it up in one command. From the skill's `scripts/` folder:

```powershell
pwsh -File setup_screenshot_pipeline.ps1
```

This installs Pillow if needed and registers a single scheduled task (`WorkScreenshots`) that runs `screenshot_capture.py` every ~2.5 min on weekdays, 08:30–20:00, saving to `~/Pictures/WorkScreenshots/<date>/`. The capture script creates the dated folders itself. Re-running the setup safely replaces the task (`-Force`); pass `-StartTime`/`-EndTime`/`-IntervalSeconds` to adjust the window. This is the *only* screenshot task the skill relies on. (`daily_exports/` is a separate, optional Cowork-sandbox bridge — not part of screenshot capture.)

**First-run check.** On every invocation, verify `Timesheets/.context.md` exists. If it doesn't:
1. Read `references/context.md.example` as the template.
2. Walk the user through filling it in — interactively, one section at a time. Ask about: their internal colleagues, the clients they bill, the signal types each client has (Edge profile, codebase, ChatGPT project, etc.), known external contacts, and any personal-browsing patterns to exclude.
3. Save the result as `Timesheets/.context.md`.
4. Tell the user they can always edit this file directly — the skill re-reads it every run.

**Ongoing updates.** When you discover a *new* fact during a timesheet run that should live in `.context.md` (a new client signal, a new colleague, a new exclusion pattern, a billing preference the user clarified), **propose** the addition at the end of the session. Show the user the exact diff you'd add and ask before writing. Don't silently mutate their file.

**AW host discovery.** ActivityWatch buckets are hostname-suffixed. On first run for a user, call `GET http://localhost:5600/api/0/buckets/` and identify the live bucket id for `aw-watcher-window`, `aw-watcher-afk`, etc. (e.g. `aw-watcher-window_HOSTNAME`). Use those bucket ids for the rest of the session. Cache them in `.context.md` under a "AW buckets" section so future sessions can skip the discovery.

**First-run: Harvest credentials.** The skill talks to Harvest via three local scripts (`scripts/harvest_post.py`, `scripts/harvest_patch.py`, `scripts/harvest_list.py`) — no MCP needed. They read credentials from a `.env` file at the skill root, falling back to OS env vars.

1. Copy `.env.example` → `.env` (same folder as `SKILL.md`). `.env` is `.gitignore`d.
2. Visit https://id.getharvest.com/developers. Note the numeric **Account ID** at the top, then create a **Personal Access Token**.
3. Paste both into `.env`:
   ```
   HARVEST_ACCOUNT_ID=1234567
   HARVEST_API_KEY=pat-...
   ```
4. Verify: `python scripts/harvest_list.py YYYY-MM-DD YYYY-MM-DD` for today should print existing entries (or nothing) without an auth error.

**Security:** `.env` grants full access to the user's Harvest account. Never commit it; never include it when sharing the skill folder with a coworker — give them `.env.example` and let them fill in their own values. Token scope: a member-scope PAT is sufficient for this skill (we only read self entries and post via `/time_entries`).

**Tunable defaults.** A few thresholds in this skill default to the user's preferences but can be overridden per-user via a `## Preferences` section in `.context.md`:
- AFK threshold for "real break" (default `1050s` = 17.5 min — shorter AFK folds into surrounding work)
- Lunch detection window (default `11:30`–`14:30` NZ)
- Work-hours window for AW rendering (default `06:00`–`20:00` NZ)
- Default Harvest task for client work (default `Gen - Development/Configuration`)

If `.context.md` overrides any of these, honour the user's value.

## Prerequisites — check at start of every run

Run these in parallel before classifying anything:

1. **`Timesheets/.context.md` exists** — if missing, kick off the first-run setup above. Do not proceed with classification until it's in place.
2. **ActivityWatch reachable** — `curl -s http://localhost:5600/api/0/buckets/` returns JSON. If not, fall back to `daily_exports/<date>/compact.jsonl`. If both are missing, the day can only be reconstructed from screenshots + user memory — say so explicitly.
3. **AW bucket ids resolved** — read from `.context.md` if cached, otherwise discover from the buckets endpoint and offer to cache them.
4. **Catalogs present and fresh** — `.mcp/harvest_assignments*.json` and any client-specific catalog files (e.g. `dv_active_incidents.txt` for users who work in Dataverse) exist and were modified within the last 7 days. If stale or missing, call `scripts/refresh_catalogs.py` (see `references/catalog-refresh.md` for the API + auth details). Don't refresh silently if the catalogs are >30 days old — surface to the user first, since a long absence may mean something else changed.
5. **Harvest credentials present** — `python scripts/harvest_list.py <today> <today>` should run without an auth error. If it exits with "Harvest credentials not found", point the user at `.env.example` (see Setup → "First-run: Harvest credentials"). If it returns `401`/`403`, the PAT in `.env` is wrong or revoked — ask the user to regenerate one at https://id.getharvest.com/developers. **Note on PAT scope:** the user's PAT is typically *member-scope*, so admin endpoints like `/projects` and `/clients` would 403. The skill never calls those — it uses `/users/me/project_assignments` (works for member PATs) via the cached `.mcp/harvest_assignments*.json`.

## Workflow

### Step 1 — Resolve target date and scope

If the user specified a date, use it. Otherwise:
- Check existing Harvest entries via `python scripts/harvest_list.py <from> <to>` for the past ~10 days
- Cross-reference against either `~/Pictures/WorkScreenshots/<date>/` (most reliable date index — screenshots exist for every workday) or `daily_exports/<date>/`
- Identify days that have activity data but no/partial Harvest entries — those are candidates
- If exactly one, use it; if multiple, list and ask; if none, tell the user everything is caught up

Convert relative dates ("yesterday", "Friday") to absolute YYYY-MM-DD using today's date in Auckland timezone — the user works in NZ.

**Honor partial-day scope:** if the user says "only do the morning" or "I've already filled in after 12:40", restrict classification to that window. Don't propose blocks outside it.

### Step 2 — Load inputs

Read in parallel:
- `Timesheets/.context.md` (full file) — the user's source-of-truth attribution rules
- `references/classification-rules.md` (this skill's classification rubric)
- Cached catalogs from `.mcp/`
- **Event data**: query ActivityWatch directly (preferred) — see Data sources above. Pull `aw-watcher-window_*`, `aw-watcher-afk_*`, `aw-watcher-web-firefox_*`, `aw-watcher-web-chrome_*` for the target date's UTC range. If AW unreachable, fall back to `daily_exports/<date>/compact.jsonl`.
- **Screenshot index**: list `~/Pictures/WorkScreenshots/<date>/` filenames with PowerShell `Get-ChildItem` (see "Reading the screenshot folder (Windows)"). Don't open the PNGs yet — Step 5 only.

Don't eagerly load screenshot PNGs or `activity.json` — defer to step 5 disambiguation.

### Step 3 — Block the day

Group events into proposed time blocks. Events are reverse-chronological (latest first); reverse to chronological first.

**Run `scripts/afk_blocks.py <date>` first — don't derive the day's skeleton by hand.** Deriving end-of-day, breaks, and active-ratio by eyeballing hundreds of raw AFK/window events is exactly where this step goes wrong (a terminal left in focus reads as "still working"; cumulative small AFKs get missed). The script does that arithmetic deterministically against the live AFK watcher and prints the facts you then classify around:

```
python scripts/afk_blocks.py 2026-05-28              # day skeleton
python scripts/afk_blocks.py 2026-05-28 --window 18:45-20:00   # active_ratio for one candidate block
python scripts/afk_blocks.py 2026-05-28 --json       # same, machine-readable
```

It returns `work_start`, **`work_end`** (the last `not-afk` moment — the true end of day), `breaks` (afk ≥ threshold, within the workday), `active_spans`, `total_active_min`, and a `window_watcher_tail` flag when a foreground window runs past `work_end` (the left-in-focus trap). Pass `--utc-offset 13` during NZ daylight saving; `--afk-threshold` to override the 1050s break cutoff. Take `work_end` as the day boundary and the `active_ratio` verdicts as authoritative; the rules below are the spec the script implements — read them so you understand *why* the numbers fall where they do, and apply them by hand only if AW is unreachable and you're working from the legacy `compact.jsonl`.

**Use the AFK watcher (`aw-watcher-afk_<host>`) as the primary break-detection signal.** Each event has `data.status` (`"afk"` or `"not-afk"`) and a duration. The AFK stream is more reliable than guessing breaks from window-event gaps, because the window watcher can fall silent for non-break reasons (the user on a long Teams call, machine locked while reading on phone, etc.).

**Hard block boundary** — split here unconditionally:
- **Lunch break** — the longest contiguous `afk` event of the day that falls between roughly 11:30 and 14:30, *if* its duration is ≥17.5 min (1050s). Mark explicitly as a `*Break*` row (not billable).
- Any other `afk` event with `duration ≥ 1050s` (≥17.5 min) — represents a genuine break.
- Window-event gap ≥30 min with no AFK record covering it (rare — usually means the watcher restarted)

**Fold-in rule for short AFK** — `afk` events shorter than 17.5 min are *not* break boundaries on their own. Treat them as part of the surrounding work block (bathroom, coffee, brief interruption — the user was still on the same task either side). Do **not** propose a `*Break*` row for these, and do **not** subtract their duration from the block hours.

**Active-ratio validation (mandatory per block).** The fold-in rule above only works if there's *enough* surrounding active time. Compute, for every proposed block:

```
active_ratio = (block_duration - sum_of_AFK_overlapping_block) / block_duration
```

- **`active_ratio ≥ 0.7`** — block is genuinely active; fold in short AFK as designed.
- **`0.4 ≤ active_ratio < 0.7`** — block is "thin". Auto-flag 🔸 and shrink the block to the *contiguous active spans* before billing (drop low-activity tails/heads, or split around mid-block AFK clumps if there's a clear high-AFK region ≥10 min cumulative).
- **`active_ratio < 0.4`** — block is mostly idle. Do not propose billing it. Surface to the user as "AW shows mostly AFK in this window — what was happening?" with screenshot timestamps from the active spans for context. Common cause: a long-running window event (Bitwarden sign-in, a model export, a Teams call that ended) that stayed in focus while the user walked away. **Window-watcher duration ≠ active work time.**

**Cumulative AFK is real even when no single event exceeds the lunch threshold.** Several 5–15 min AFK chunks within an hour add up to a real break in aggregate. Use `active_ratio` (not "longest single AFK") as the deciding signal.

**End-of-day boundary — anchor on the AFK watcher, never on the last window event.** The workday ends at the **last `not-afk → afk` transition** in `aw-watcher-afk_<host>` (the final moment of genuine activity). It does **not** end at the last window event. A foreground window — especially `WindowsTerminal`, an IDE, a browser, or `unknown`/`LockApp` — routinely stays in focus for many minutes (sometimes hours) after the user has walked away; that trailing window event carries a long `duration` but is **not** work time. Concretely: if the AFK stream goes `afk` at 19:47 and stays afk to midnight, the day ends ~19:47 even though the window watcher shows a terminal "in focus" until 20:02 and a `LockApp` event after that. Clamp the final block's end to the last `not-afk` timestamp. **Never** extend the last block to the screenshot-scheduler window (08:30–20:00) or the work-hours rendering window (06:00–20:00) — those are capture/display bounds, not activity signals.

**This rule applies on the backfill path too.** When backfilling the gap between the last timesheet and the latest export (the "evening backfill" case), you are *more* likely to be looking at trailing left-in-focus windows — run the same AFK-anchored end-of-day check and active-ratio validation on the final block. Don't assume the user worked up to whatever the last window/screenshot timestamp happens to be.

**Soft block boundary** — split here if doing so improves classification clarity:
- Sustained context switch: ≥3 consecutive events with a different ticket-prefix or Edge profile than the prior block, totalling ≥3 min
- A Teams meeting starts (window title `Meeting | …` or `Call with …`) — meetings are usually their own block
- Active-ratio falls below 0.7 mid-block — shrink the block to the contiguous active span before proceeding

Aim for **15-min granularity** in the final timesheet (rounded to 0.25 hrs), matching the user's existing format. Don't propose blocks shorter than 0.25 hr — fold them into the adjacent block.

### Step 4 — Classify each block

For each block, determine **client** + **Harvest project** + **Harvest task** + **billable/NB** + **confidence (high/medium/low)**. The full rubric is in `references/classification-rules.md`. Quick summary:

1. **Ticket-number signal (highest confidence):** if any event in the block has a window title or URL containing a ticket-number-shaped string `[A-Z]{2,4}\d{3,}S?`, look it up in `.mcp/dv_active_incidents.txt` for the title, and in `.mcp/harvest_assignments*.json` matching `project.code`. Direct hit → high confidence.
2. **Edge profile signal:** window title ending `… - <ProfileName> - <UserDisplayName> - Microsoft Edge` (or `… - <ProfileName> - Microsoft Edge` for older format) → profile name maps to client per `.context.md`. (`<UserDisplayName>` is the user's profile name shown by Edge — discovered automatically from window titles in the first session.)
3. **Teams chat signal:** title pattern `Chat | <Name>… | <TenantName> | <user-email> | Microsoft Teams`. If the chat title includes an *internal-colleague* name from `.context.md`, → the user's internal / admin project (defined in `.context.md`). External contacts also live in `.context.md` under "Known external contacts".
4. **App-stack signal:** `XrmToolBox`, `devenv.exe`, `SIMS - Visual Studio Code`, etc. — see rubric for the full mapping.
5. **`claude.exe` adjacent logic:** Pure `claude.exe` time inherits the surrounding block's client unless adjacent to timesheet-automation paths (`Claude/Scheduled/`, `Pictures/WorkScreenshots/`, `Claude/Work/Timesheets/`), in which case → your internal / admin project.

For the task (Harvest sub-category), match to the project's `task_assignments[]`:
- Mostly meetings/chat → `Gen - Meeting` or `Gen - Meeting (NB)`
- Code/configuration → `Gen - Development/Configuration`
- Docs/Obsidian/wiki → `Gen - Documentation`
- Bug investigation, ADO log reading → `Gen - Investigation` if available else `Gen - Issue Resolution`
- Generic → `Gen - General Consulting`

**Billable status comes from the task assignment, not the task name.** Check `task_assignments[N].billable` in `harvest_assignments*.json` — that's authoritative. The `(NB)` suffix is a naming convention some clients use to distinguish billable / non-billable variants of the same task (e.g. `Gen - Meeting` vs `Gen - Meeting (NB)`), but many tasks are non-billable without the suffix — everything under an internal admin project like `INT-001` is non-billable, and those task names don't carry `(NB)`. Practical rule: when the block is internal/admin/training, pick a task whose `billable: false` in the catalog; treat the `(NB)` suffix as a *hint*, not the source of truth.

**Trailing `S` on ticket numbers** (e.g. `ABC2138S`, `ABC2020S`) → flag the block as Support work in the timesheet description ("[Support] …"), but project_id/task_id selection is the same.

### Step 5 — Disambiguate low-confidence blocks

For any block flagged 🔸 (low confidence OR thin active-ratio OR ambiguous attribution):

**Separate concerns:**
- **AFK status** is determined by `aw-watcher-afk_<host>` only. Active vs idle is a fact from the AFK watcher — don't try to re-infer it from screenshots.
- **Client / project attribution** is what screenshots are *for*. When the window title or URL doesn't tell you which client an app is being used for, the screenshot does.

1. **Use screenshots to resolve which client a generic app was working on.** Many apps don't expose the client in their window title — `XrmToolBox`, `Visual Studio Code` (when no workspace name is in the title), bare browsers showing nothing useful, terminal windows, etc. The screenshot at that timestamp will show the actual environment, repo, ticket, or Dataverse org on screen, which identifies the client.

   Workflow:
   1. Identify the timestamps within the block where window-watcher shows a generic / ambiguous app.
   2. Find the screenshot file closest to those timestamps in `~/Pictures/WorkScreenshots/<date>/HH-MM-SS.png` (cadence ~2.5 min), listing the folder with PowerShell `Get-ChildItem` (see "Reading the screenshot folder (Windows)"). This folder covers the full 08:30–20:00 day, so use it for afternoon and evening blocks.
   3. Read the PNG. Look at the visible env URL, workspace name, repo path, ticket title, project name — whatever lets you pin down the client.
   4. Apply the resolved client to the block. If multiple screenshots within the block show *different* clients, split the block.

2. **Active-ratio is already settled by AFK.** Step 3 has computed `active_ratio` from the AFK watcher. Don't use screenshots to "verify AFK". If `active_ratio < 0.4`, the block shouldn't be billed regardless of what the screenshots show.

3. **If still ambiguous after screenshot check, ask the user.** Show the screenshot timestamps you peeked at, what you saw, and the candidate clients. Let the user pick.

4. **Never silently bill an abandoned-task block.** If the active spans in the block are a setup / sign-in / install that ended without producing client deliverable work (and the user pivoted elsewhere afterward), surface it explicitly. Default to the user's internal-admin project as non-billable unless the user says otherwise.

### Step 6 — Present the proposed timesheet

Render as a markdown table identical to the user's existing format:

```markdown
| Time | Duration | Client | Description |
|------|----------|--------|-------------|
| 08:12–08:46 | 0.5 hrs | <Client> | <Description with ticket # if any> |
```

Below the table, **flag uncertain blocks** with a 🔸 marker.

**Show the AFK skeleton next to the blocks as a reality check.** Print the one-line facts from `scripts/afk_blocks.py` — `work start`, **`work end`**, the day's breaks, and total active minutes — directly above or below the proposed table. The user knows their own day ("I stopped at 7:12"), so surfacing the watcher-derived boundary is the cheapest, strongest accuracy check there is: a wrong end-of-day or a missed break is obvious the moment the real numbers are on screen. This is non-negotiable for the final block of the day, which is where end-of-day errors hide.

**Hard guard — no block may end after `work_end`.** `work_end` (last `not-afk`) is the deterministic ceiling for the day. If any proposed block ends later, you've billed idle time — shrink it to `work_end` (or earlier, if a thin tail per Step 3 should be dropped) before presenting. State the day's `work_end` explicitly in the summary so the user can confirm it matches reality.

**Be honest about the precision the data supports.** End-of-day and breaks are deterministic (AFK watcher → script). *Which client / billable-vs-not / how to split a block* is judgment from window+URL signals, and genuinely varies — so when a block's attribution or billability isn't clear-cut, flag it 🔸 rather than committing silently. The review gate exists precisely because classification can't be made deterministic; the user's confirmation is what makes the timesheet accurate, so make the uncertain calls easy to see.

Then ask:

> "I've drafted N blocks for <date> (AFK watcher: work ended HH:MM, breaks at …). M are high confidence (no marker), 2 are low confidence (🔸). Want to walk through the 🔸 ones, or batch-accept and edit individuals after?"

Wait for the answer. Edit per the user's input.

### Step 7 — Write the timesheet .md *(optional — ask first)*

the user often doesn't need the markdown file — Harvest is the system of record. **Ask** whether he wants the `.md` audit trail before generating it. If he does, write `Timesheets/<date>_timesheet.md` matching the template in `references/output-format.md` (table, totals, notes, footer). If he doesn't, skip to Step 8.

### Step 8 — Confirmation gate before Harvest

Before any write to Harvest, show:

> "Ready to post to Harvest. This will create N time entries:
> - 0.5 hrs · [Your Consultancy Ltd] · Internal — Team Standup
> - 0.75 hrs · [Acme Corp] · ABC2020S Acme Fabrics Copy job — Gen - Investigation
> - …
>
> Proceed? (yes / no / edit block <n>)"

**Do not post without an explicit "yes" or equivalent affirmative.** Edits loop back to step 6.

### Step 9 — Post to Harvest

For each confirmed block, run:

```
python scripts/harvest_post.py <project_id> <task_id> <YYYY-MM-DD> <HH:MM> <HH:MM> '<notes>'
```

- `<project_id>` — the integer from the matched project assignment
- `<task_id>` — the integer from the matched task assignment
- `<YYYY-MM-DD>` — the target date
- `<HH:MM> <HH:MM>` — block start, block end (24h or 12h like `8:15am` both accepted by Harvest)
- `'<notes>'` — description from the table. **Use single quotes** to prevent shell `$variable` interpolation from mangling notes that mention money (`$5k`), shell-shaped substrings, or backticks.

Success prints `OK <entry_id>`. Failure prints `ERR <status> <body>` to stderr and exits non-zero — stop and surface the error, don't silently retry.

**The script always sends `started_time` + `ended_time`, never bare `hours`.** Harvest accounts can be in *duration* mode or *start/end-time* mode. In start/end-time mode, posting just `hours` makes Harvest start a running timer instead of logging a fixed block. Passing start/end always works in either mode — Harvest computes `hours` from the times. (You can check the mode by inspecting any existing entry from `harvest_list.py`: if it has non-null `started_time` and `ended_time`, the account is in start/end mode.)

To fix an entry that ended up as a timer or has wrong values, use:

```
python scripts/harvest_patch.py <entry_id> [--start HH:MM] [--end HH:MM] [--notes "..."] [--hours N] [--project-id N] [--task-id N] [--date YYYY-MM-DD]
```

At least one flag is required. Same `OK <id>` / `ERR …` output convention.

Post serially (not in parallel) so the user can interrupt cleanly if something looks wrong. After each, log: `✓ Posted: <hours> hrs · <project.code> · <task>` to the user. Capture each `OK <entry_id>` for the wrap-up paper trail in Step 10.

#### Block bills to brand-new client work with no Harvest project yet

A block may belong to new work with no Harvest project yet — in some setups you create a backend ticket/case in a CRM (e.g. a Dataverse Case) that syncs to Harvest as a new project (`project.code` == ticket id). Creating that ticket is **org-specific and not bundled** with this skill — use whatever tooling your CRM provides, and confirm the resolved client + title with the user before creating anything client-facing. Full mechanism + the optional read-only Dataverse catalog are in `references/catalog-refresh.md`. After the ticket exists: **post the other blocks now**, then use `refresh_catalogs.wait_for_project(<code>)` to poll for the new project (its catalog entry lags a few minutes and a single refresh isn't reliable), and bill the deferred block once it surfaces.

### Step 10 — Wrap-up

When done, summarise:
- Total hours posted
- Any blocks deferred or skipped
- Suggested next action (next date to backfill, or "all caught up")

Save the harvest entry IDs (the `OK <entry_id>` values from Step 9) to `Timesheets/<date>_harvest_responses.json` as a simple list — paper trail if reconciliation is ever needed. Format: `{"entries": [{"id": 2933345845, "project_code": "INT-001", "hours": 0.25, "notes": "..."}], ...}`.

### Step 11 — Surface skill or `.context.md` improvements

A timesheet run frequently reveals things the skill or the user's `.context.md` doesn't know yet — a new client signal you had to guess, a billing convention that turned out to be wrong, a watcher bucket that's offline, an ambiguity you couldn't resolve. Capture these as you go and present them at the end of the session.

For each finding, decide whether it belongs in:
- **`.context.md`** — anything about *this user's* clients, colleagues, signals, exclusions, billing preferences, default tasks. Most additions land here.
- **`SKILL.md`** (or its `references/`) — anything about the *workflow itself* — a new heuristic that applies to any user, a data-source change, a confidence-rating refinement, a Harvest-API quirk.

Show the proposed diff and ask before writing. Examples:

> "While classifying 5/13 I noticed you billed the Team Standup to ABC2005, but `.context.md` says it goes to INT-001. Want me to (a) update `.context.md` to reflect the override, (b) leave both as-is, or (c) move the entry to INT-001?"

> "The XrmToolBox signal didn't appear in any client section of `.context.md`. I guessed Acme Corp this time. Want me to add `XrmToolBox connecting to env X → Acme Corp` as a signal under the Acme Corp section?"

> "AW window-watcher went silent 12:30-14:30 today but the AFK watcher showed activity throughout. Want me to add a note to SKILL.md that AFK is the more reliable break signal in this kind of gap?"

Keep proposals concrete and small — one fact per ask. Don't batch huge rewrites.

## Non-negotiables

- **No Harvest write without explicit confirmation.** Treat as a hard rule.
- **Honor `Timesheets/.context.md` exclusions** — personal browsing (flights, social, news, weather, Pomodoro pages), AFK breaks, personal home admin (router pages, smart-home admin, etc.) are NEVER billable.
- **Don't fabricate confidence.** If a block genuinely could be 2-3 clients, surface that — don't pick one arbitrarily.
- **Describe the project area, not the internal mechanism.** Harvest `notes` get sent to clients with invoices, so describe *what part of their project* was worked on (e.g. "Confidential Matters configuration", "MyPortal architecture review", "ROA import investigation") — not the internal tool/process flavour of the activity ("flow naming conventions", "renaming variables", "refactoring the helper module"). When the underlying work is a coding-standards pass, a refactor, or other internal-mechanism work, frame it by the client deliverable it serves. Tickets (e.g. `ABC2232S`) and recurring meeting names (e.g. `Team Standup`) are fine to name verbatim — they're already client-facing. Internal app names (e.g. a scratch app), code file names, and internal chat partners are not. Markdown timesheet descriptions stay internal so can be more granular, but the Harvest `notes` field should follow this rule. See `.context.md` "How I bill" and existing entries in Harvest history for examples.
- **`.context.md` is the source of truth for per-user facts.** When you learn something about a client / signal / convention, propose adding it there — not into the skill.

## Files in this skill

- `SKILL.md` — this file
- `.env.example` — template for the user's Harvest credentials. Copy to `.env` (gitignored).
- `.gitignore` — keeps `.env` out of git.
- `references/context.md.example` — starter template for `Timesheets/.context.md`
- `references/classification-rules.md` — full rubric for client/project/task selection
- `references/output-format.md` — exact template for the timesheet .md
- `references/catalog-refresh.md` — how to refresh `.mcp/harvest_assignments*.json` and any other catalog files
- `scripts/afk_blocks.py` — deterministic AFK-watcher analyzer: prints `work_start`/`work_end`/breaks/active-spans + per-window `active_ratio` from the live AW stream. Run it at the start of Step 3 so end-of-day, breaks, and thin-block detection aren't eyeballed
- `scripts/harvest_client.py` — shared Harvest API helper: loads `.env` creds, wraps `urllib` requests
- `scripts/harvest_post.py` — create a time entry. `OK <id>` on success
- `scripts/harvest_patch.py` — update an existing time entry
- `scripts/harvest_list.py` — list self entries for a date range, compact one-per-line output
- `scripts/refresh_catalogs.py` — refreshes `.mcp/harvest_assignments*.json` and `.mcp/dv_active_incidents.txt`
- `scripts/screenshot_capture.py` — captures one all-monitors screenshot into `~/Pictures/WorkScreenshots/<date>/`; fired by the scheduled task
- `scripts/setup_screenshot_pipeline.ps1` — one-time setup: installs Pillow and registers the single `WorkScreenshots` scheduled task (weekdays 08:30–20:00, ~2.5 min)
