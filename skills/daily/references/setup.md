# Setup — first run per user / per machine

Read this only when a prerequisite check fails (missing `.context.md`, unconfigured credentials or timezone, no screenshot task, unknown AW buckets) or the user asks about standing the pipeline up. Routine runs never need this file.

The skill is **shareable across users**. Each user maintains their own `Timesheets/.context.md` describing *their* clients, colleagues, billing conventions, and preferences. The skill stays generic; `.context.md` carries the personal facts.

## Screenshot grabber (one-time, per machine)

The skill bundles its own capture pipeline. From the skill's `scripts/` folder:

```powershell
pwsh -File setup_screenshot_pipeline.ps1
```

This installs Pillow + mss if needed and registers a single scheduled task (`WorkScreenshots`) that runs *this* `scripts/screenshot_capture.py` in place every ~2.5 min on weekdays, 08:30–20:00, saving to `~/Pictures/WorkScreenshots/<date>/`. Because it points at the script in the skill folder, future skill updates take effect with no re-copying. The capture script creates the dated folders itself. Re-running the setup safely replaces the task (`-Force`); pass `-StartTime`/`-EndTime`/`-IntervalSeconds` to adjust the window. Add `-DryRun` to print the task it would register — command line, schedule and capture directory — without installing packages or registering anything. To capture somewhere other than `~/Pictures/WorkScreenshots`, set `TIMESHEET_SCREENSHOTS_DIR` (`/plugin configure billables`, or `.env` on an exported install) **and** pass the same path as `-ScreenshotsDir`, so the reader and the scheduled task agree. The scheduled task runs outside any Claude Code session, so it never sees the configured value — passing it explicitly is what keeps the two in step, not a convenience. This is the *only* screenshot task the skill relies on. (`daily_exports/` is a separate, optional Cowork-sandbox bridge — not part of screenshot capture.)

> **If a previous `WorkScreenshots` task was registered as Administrator**, re-running setup from a normal shell fails with `Access is denied`. Run the setup command from an **elevated** PowerShell once to replace it; afterward the task points at the in-place skill script and ordinary skill updates need no further elevation.

### Health check — captures stopped

A dead capture task fails *silently*: the task stays `Ready`, no error surfaces, and the
only symptom is a screenshot folder that stops part-way through a day (which looks
identical to the user having stopped work — see `SKILL.md` Step 3).

```powershell
Get-ScheduledTaskInfo -TaskName WorkScreenshots | Select-Object LastRunTime, LastTaskResult, NextRunTime
```

`LastTaskResult` of `0` is healthy. **`0x80070002` (file not found) means the interpreter
path moved** — the task action stores an absolute path, so a Python upgrade, reinstall, or
switch between per-machine and per-user install breaks it, and every trigger from that
moment on fails. Confirm with `(Get-ScheduledTask -TaskName WorkScreenshots).Actions`, then
re-run `setup_screenshot_pipeline.ps1` to re-register against the current interpreter.
Setup prefers the version-independent launcher (`pyw.exe`) precisely so this survives a
reinstall; a task registered by an older setup may still hold a versioned path. Setup also
probes every candidate with a real import before trusting it — a 0-byte Store stub or a
split install that can't reach its own libraries is skipped, and `-PythonExe <path>` pins
an interpreter explicitly when probing picks wrong.

Verify the fix by running the task once (`Start-ScheduledTask -TaskName WorkScreenshots`)
and confirming new PNGs appear for every monitor.

## First-run: `Timesheets/.context.md`

If `Timesheets/.context.md` doesn't exist:

1. Read `references/context.md.example` as the template.
2. Walk the user through filling it in — interactively, one section at a time. Ask about: their internal colleagues, the clients they bill, the signal types each client has (Edge profile, codebase, ChatGPT project, etc.), known external contacts, and any personal-browsing patterns to exclude.
3. Save the result as `Timesheets/.context.md`.
4. Tell the user they can always edit this file directly — the skill re-reads it every run.

## First-run: configuration

Everything the skill needs to know about *this machine and account* is declared in the plugin manifest, so a fresh install asks for it once and never again:

| Key | Required | Unset means |
| --- | --- | --- |
| `HARVEST_ACCOUNT_ID` | yes | every Harvest command stops, naming this key |
| `HARVEST_API_KEY` | yes | as above |
| `TIMESHEET_TIMEZONE` | yes | `afk_blocks` / `activity_timeline` refuse to date a day |
| `TIMESHEET_ACTIVITY_URL` | no | `http://localhost:5600` |
| `TIMESHEET_SCREENSHOTS_DIR` | no | `~/Pictures/WorkScreenshots` |
| `TIMESHEET_WORKSPACE` | no | the directory Claude Code is run from, if it looks like a workspace |

The user sets them with **`/plugin configure billables`**. The two Harvest fields are declared *sensitive*, so Claude Code stores them in its own credential store — not in any file in the plugin, and not in `settings.json`. A plugin update cannot carry them off and there is nothing for this skill to git-ignore.

Be accurate about *where*, when telling a user. That store is the OS keychain on **macOS** only; on Windows and Linux it is `~/.claude/.credentials.json`, a file in the home directory protected by file permissions rather than by a keychain. This plugin is Windows-first, so for most of its users the token is on disk — saying "keychain" invites them to treat their home directory as safe to sync or share.

Every script reads them through the one seam, `scripts/skill_config.py`: a per-command flag, then the skill's `.env`, then the process environment (which is where the harness's values arrive), then the script's own default. That module's docstring carries the precedence and the reasoning for it.

1. Visit https://id.getharvest.com/developers. Note the numeric **Account ID** at the top, then create a **Personal Access Token**.
2. Run `/plugin configure billables` and paste both in, along with an IANA timezone name (`Europe/London`, `Pacific/Auckland`). There is deliberately no default zone — a guessed one dates the whole timesheet wrong without failing.
3. Restart the session, or start a new one: the values reach the scripts through the plugin's SessionStart hook, which runs at the start of a session.
4. Verify: `python scripts/harvest_list.py YYYY-MM-DD YYYY-MM-DD` for today should print existing entries without an auth error. A day with no entries prints `(no time entries from … to …)` on stderr — exit 0 plus that notice is the success case, distinguishable from a run that silently did nothing.

**Exported install** (the shared Agent Skills export that `install/install_skill.ps1` generates, rather than `/plugin install`): there is no manifest for a harness to ask from, so the same keys go in a `.env` at the skill root instead — copy `.env.example` → `.env` (same folder as `SKILL.md`; it is `.gitignore`d) and fill it in. That file grants full access to the user's Harvest account: never commit it, and never include it when sharing the skill folder with a coworker — give them `.env.example` and let them fill in their own.

**Token scope:** a member-scope PAT is sufficient (the skill only reads self entries and posts via `/time_entries`). Admin endpoints like `/projects` and `/clients` would 403 on a member PAT — the skill never calls those; it uses `/users/me/project_assignments` via the cached `.mcp/harvest_assignments*.json`.

**Windows and the timezone database:** `zoneinfo` is stdlib, but on Windows the IANA data it reads is not shipped with Python. If a run reports it could not load the configured zone, `py -m pip install tzdata` for the interpreter the skill uses. The message says so; it does not fall back to a guessed offset.

### When the configuration does not arrive

The user filled in `/plugin configure billables`, started a new session, and a script still says the value is missing. Two causes, in the order worth checking.

**1. A leftover `.env` is outranking it.** The seam's precedence is flag → `.env` → process environment, and the plugin's values arrive in the *environment*. Before this release the two routes carried different keys, so the order never bit; now they carry the same six, and a `.env` left over from an exported install silently wins. The tell is a rotated credential that still 401s, or a timezone change that has no effect. Check for a `.env` beside `SKILL.md`; on a plugin install, delete it — configuration belongs in the dialog, and a file inside the plugin folder is carried off by the next update anyway.

**2. The session hook could not run.** The declared values reach *hook* processes only; the plugin's `hooks/publish_plugin_config.sh` republishes them into the session so the scripts see them. Claude Code runs hook commands through Git Bash on Windows — and through **PowerShell** when Git Bash is not installed, where `sh` is not a command and the hook cannot start. The symptom is precisely "I configured everything and nothing is configured". Fix: `winget install Git.Git`, then start a new session. To confirm before installing anything, check whether `sh --version` runs in the user's shell.

Neither failure is a reason to hand the scripts a guessed value. `--utc-offset <hours>` gets one run done while the cause is being fixed; the credentials have no equivalent, and shouldn't.

## AW host discovery (one-time per machine)

ActivityWatch buckets are hostname-suffixed. On first run for a user, call `GET <activity-url>/api/0/buckets/` and identify the live bucket id for `aw-watcher-window`, `aw-watcher-afk`, etc. (e.g. `aw-watcher-window_HOSTNAME`). Cache them in `.context.md` under an "AW buckets" section so future sessions can skip the discovery.

## ActivityWatch categories (keep them current)

`activity_timeline.py` reads the user's AW category rules live from `/api/0/settings` (client-level regex on window titles — e.g. a rule matching `ACME` in the title tags events as the ACME client). These rules are the source of the CLIENT-level categories shown in the timeline; they are never project- or ticket-level, and they are a first-pass signal only, not 100% certain.

Keep them useful by:
- Filling any placeholder `New class` (`FILL ME`) rule in the AW settings UI with a real client-regex.
- Adding missing clients as new rules when new work starts — the timeline's `uncategorized` spans are the indicator.
- A client-level regex on window titles fundamentally cannot catch *work-content* overrides (e.g. work for client A done under client B's Edge profile). Those overrides must be captured as manual rules in `.context.md` under the relevant client section and resolved during classification.

## After a machine reimage or replacement

A reimage/replacement machine keeps the same user profile path but breaks several things at once, from one underlying cause (new OS install, new hostname):

1. **Scheduled screenshot task points at a dead interpreter.** Its `Execute` path is whatever Python was installed on the old image — check `Get-ScheduledTaskInfo -TaskName WorkScreenshots` for a non-zero `LastTaskResult` (file-not-found is `2147942402`). If the interpreter path changed, `Set-ScheduledTaskAction` with the new `pythonw.exe` path, then re-run `scripts/screenshot_capture.py` once by hand to confirm it isn't *also* missing `mss`/`Pillow` (a fresh Python install has neither) — `pip install mss Pillow` for that interpreter if the capture log shows `No module named ...`.
2. **A configured `TIMESHEET_WORKSPACE` may point at a path that no longer exists.** `find_workspace()` returns it verbatim with no existence check — and neither does the plugin's configuration dialog, whose `directory` type offers a picker but accepts a path that isn't there — so a stale value silently breaks every catalog lookup (`harvest_lookup.py`, `refresh_catalogs.py`) while Harvest-API-only scripts (`harvest_list.py`) keep working and mask the problem. Verify the path with `Test-Path`, not by assuming a script's success means the workspace resolved correctly.
3. **`pac auth` profiles don't carry over.** `pac auth list` after a reimage typically keeps client-environment profiles (if the user re-logged into those separately) but drops the internal-CRM profile the skill's `.env` names — `refresh_catalogs.py`'s Dataverse half fails with `AuthProfileNameDoesNotExist`. Recreating it (`pac auth create --name <PAC_PROFILE> --environment <DATAVERSE_URL>`) is an interactive login — confirm with the user before running it, per the Dataverse-headless convention in their `.context.md`.
4. **AW hostname suffix changes** (e.g. `HOST-OLD` → `HOST-NEW`) — no action needed: `aw_client.py`'s `pick_bucket()` already prefers a suffixed bucket over an unsuffixed leftover and breaks ties among suffixed candidates by `last_updated`, not alphabetically. A stale hostname hardcoded anywhere in `.context.md` prose is still worth correcting so it doesn't mislead a reader.

## Ongoing `.context.md` updates

When a run discovers a *new* fact that should live in `.context.md` (a new client signal, a new colleague, a new exclusion pattern, a clarified billing preference), **propose** the addition at the end of the session. Show the user the exact diff and ask before writing. Don't silently mutate their file.
