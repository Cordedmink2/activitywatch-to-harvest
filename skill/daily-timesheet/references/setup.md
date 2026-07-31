# Setup — first run per user / per machine

Read this only when a prerequisite check fails (missing `.context.md`, missing `.env`, no screenshot task, unknown AW buckets) or the user asks about standing the pipeline up. Routine runs never need this file.

The skill is **shareable across users**. Each user maintains their own `Timesheets/.context.md` describing *their* clients, colleagues, billing conventions, and preferences. The skill stays generic; `.context.md` carries the personal facts.

## Screenshot grabber (one-time, per machine)

The skill bundles its own capture pipeline. From the skill's `scripts/` folder:

```powershell
pwsh -File setup_screenshot_pipeline.ps1
```

This installs Pillow + mss if needed and registers a single scheduled task (`WorkScreenshots`) that runs *this* `scripts/screenshot_capture.py` in place every ~2.5 min on weekdays, 08:30–20:00, saving to `~/Pictures/WorkScreenshots/<date>/`. Because it points at the script in the skill folder, future skill updates take effect with no re-copying. The capture script creates the dated folders itself. Re-running the setup safely replaces the task (`-Force`); pass `-StartTime`/`-EndTime`/`-IntervalSeconds` to adjust the window. Add `-DryRun` to print the task it would register — command line, schedule and capture directory — without installing packages or registering anything. To capture somewhere other than `~/Pictures/WorkScreenshots`, set `TIMESHEET_SCREENSHOTS_DIR` in `.env` **and** pass the same path as `-ScreenshotsDir`, so the reader and the scheduled task agree. This is the *only* screenshot task the skill relies on. (`daily_exports/` is a separate, optional Cowork-sandbox bridge — not part of screenshot capture.)

> **If a previous `WorkScreenshots` task was registered as Administrator**, re-running setup from a normal shell fails with `Access is denied`. Run the setup command from an **elevated** PowerShell once to replace it; afterward the task points at the in-place skill script and ordinary skill updates need no further elevation.

## First-run: `Timesheets/.context.md`

If `Timesheets/.context.md` doesn't exist:

1. Read `references/context.md.example` as the template.
2. Walk the user through filling it in — interactively, one section at a time. Ask about: their internal colleagues, the clients they bill, the signal types each client has (Edge profile, codebase, ChatGPT project, etc.), known external contacts, and any personal-browsing patterns to exclude.
3. Save the result as `Timesheets/.context.md`.
4. Tell the user they can always edit this file directly — the skill re-reads it every run.

## First-run: Harvest credentials

The skill talks to Harvest via three local scripts (`scripts/harvest_post.py`, `scripts/harvest_patch.py`, `scripts/harvest_list.py`) — no MCP needed. They read credentials from a `.env` file at the skill root, falling back to OS env vars.

1. Copy `.env.example` → `.env` (same folder as `SKILL.md`). `.env` is `.gitignore`d.
2. Visit https://id.getharvest.com/developers. Note the numeric **Account ID** at the top, then create a **Personal Access Token**.
3. Paste both into `.env`:
   ```
   HARVEST_ACCOUNT_ID=1234567
   HARVEST_API_KEY=pat-...
   ```
4. Verify: `python scripts/harvest_list.py YYYY-MM-DD YYYY-MM-DD` for today should print existing entries (or nothing) without an auth error.

**Security:** `.env` grants full access to the user's Harvest account. Never commit it; never include it when sharing the skill folder with a coworker — give them `.env.example` and let them fill in their own values. Token scope: a member-scope PAT is sufficient (the skill only reads self entries and posts via `/time_entries`). Admin endpoints like `/projects` and `/clients` would 403 on a member PAT — the skill never calls those; it uses `/users/me/project_assignments` via the cached `.mcp/harvest_assignments*.json`.

## AW host discovery (one-time per machine)

ActivityWatch buckets are hostname-suffixed. On first run for a user, call `GET http://localhost:5600/api/0/buckets/` and identify the live bucket id for `aw-watcher-window`, `aw-watcher-afk`, etc. (e.g. `aw-watcher-window_HOSTNAME`). Cache them in `.context.md` under an "AW buckets" section so future sessions can skip the discovery.

## ActivityWatch categories (keep them current)

`activity_timeline.py` reads the user's AW category rules live from `/api/0/settings` (client-level regex on window titles — e.g. a rule matching `Connexis` in the title tags events as the Connexis client). These rules are the source of the CLIENT-level categories shown in the timeline; they are never project- or ticket-level, and they are a first-pass signal only, not 100% certain.

Keep them useful by:
- Filling any placeholder `New class` (`FILL ME`) rule in the AW settings UI with a real client-regex.
- Adding missing clients as new rules when new work starts — the timeline's `uncategorized` spans are the indicator.
- A client-level regex on window titles fundamentally cannot catch *work-content* overrides (e.g. work for client A done under client B's Edge profile). Those overrides must be captured as manual rules in `.context.md` under the relevant client section and resolved during classification.

## Ongoing `.context.md` updates

When a run discovers a *new* fact that should live in `.context.md` (a new client signal, a new colleague, a new exclusion pattern, a clarified billing preference), **propose** the addition at the end of the session. Show the user the exact diff and ask before writing. Don't silently mutate their file.
