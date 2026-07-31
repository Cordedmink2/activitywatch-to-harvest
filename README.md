# activitywatch-to-harvest

A [Claude Code](https://claude.com/claude-code) skill that reconstructs your workday from
[ActivityWatch](https://activitywatch.net/) + periodic screenshots, classifies the activity into
per-client time blocks, shows them to you for review, and (only after you confirm) posts the entries
to [Harvest](https://www.getharvest.com/).

It's built for consultants who bill **multiple clients out of one machine** and are tired of
reconstructing "what did I actually do today?" from memory. ActivityWatch records the raw activity;
this skill turns it into a reviewable, billable timesheet.

> **You stay in control.** Nothing is ever posted to Harvest without an explicit "yes". The skill
> proposes; you approve.

---

## How it works (the short version)

1. **ActivityWatch** runs locally and logs which app/window/browser-tab is in focus, plus when you're
   away from the keyboard (AFK).
2. The **"URL in Title" browser extension** stamps a short **client code** into every tab's title
   (e.g. `… - [NZLS]`), so browser activity carries which client it belongs to.
3. **ActivityWatch categories** use those codes to auto-classify browser time per client.
4. A small **screenshot grabber** takes a periodic screenshot during work hours, used only to
   disambiguate activity that the window title alone can't pin to a client.
5. The **skill** reads all of the above, drafts a timesheet, shows it to you, and posts confirmed
   blocks to Harvest.

---

## The lazy path — let Claude Code set it up for you

Don't want to click through the manual setup below? This repo ships an [`llms.txt`](./llms.txt) — a
machine-readable runbook for the setup. Just open Claude Code anywhere and paste this — it tells
Claude where to find everything, so you don't even need to clone first:

```
Clone https://github.com/Cordedmink2/activitywatch-to-harvest, read its llms.txt, and set up the
daily-timesheet skill for me on this machine. Walk me through anything you can't do yourself
(installing ActivityWatch, the browser extension, the browser-profile title tags, the AW
categories). Ask me for any secrets — don't guess them — and never commit my .env.
```

Claude will clone the repo, run the install/scaffold scripts, help you create your `.env`, verify
ActivityWatch is reachable, and talk you through the manual browser steps that only a human can do.

> **Heads-up on antivirus / EDR.** A scheduled task that silently screenshots every few minutes looks
> like spyware to endpoint security, so it (or `pip install`) may be blocked mid-setup. The runbook
> tells Claude to verify each step actually took effect rather than assume it — if a step is blocked,
> Claude will stop and tell you exactly what to allow-list (the skill's `scripts/` folder) instead of
> silently carrying on.

---

## Updating

There's no separate updater — the install script is idempotent, so you update by getting the latest
repo files and re-running it.

- **If you cloned the repo**, from inside your clone:
  ```powershell
  git pull
  pwsh -File install\install_skill.ps1        # macOS/Linux: ./install/install_skill.sh
  ```
- **If you used the lazy path above** (no local clone), just ask Claude Code to *"update the
  daily-timesheet skill from the latest activitywatch-to-harvest repo"* — it'll fetch the current
  version and re-run the installer.

Re-running never touches your `.env`, your workspace, or your `.context.md`. Note it **copies over**
`~/.claude/skills/daily-timesheet` rather than mirroring it, so a file *removed* upstream won't be
deleted from your copy. For a clean reinstall, delete the skill folder first (back up your `.env`),
then run the install script.

> **Updating from an earlier version?** See [CHANGELOG.md](./CHANGELOG.md) for what changed in
> each release and whether you need to act.
>
> **Re-run the screenshot setup afterwards.** The install script only
> copies files — it installs no Python dependencies. Older versions captured a single stitched image
> with Pillow alone; the current per-monitor capture also needs [mss](https://python-mss.readthedocs.io/).
> Because the `WorkScreenshots` task points at the in-place script, it starts running the new code on
> its next tick and will fail with `No module named 'mss'` (silently, into `capture.log`) until `mss`
> is present. Re-run the screenshot setup once to install it (it also safely re-registers the task):
>
> ```powershell
> pwsh -File "$HOME\.claude\skills\daily-timesheet\scripts\setup_screenshot_pipeline.ps1"
> ```

---

## Prerequisites

- **Windows** (the screenshot pipeline + setup scripts target Windows/PowerShell; the skill logic and
  the `.sh` install scripts work cross-platform, but screenshots are Windows-only as shipped).
- **PowerShell 7** (`pwsh`) for the commands below. Windows ships only Windows PowerShell 5.1, where
  `pwsh` doesn't exist — install it with `winget install Microsoft.PowerShell`, or substitute
  `powershell.exe -File …` in every command (the scripts run under 5.1 too).
- **Python 3.10+** on your `PATH` (`python --version`).
- **[Claude Code](https://claude.com/claude-code)** installed.
- A **Harvest** account you can create a personal access token for.
- A Chromium browser (Chrome/Edge) if you want per-client browser classification.

---

## Setup — step by step

### 1. Install ActivityWatch

Download and install it from **https://activitywatch.net/downloads/**, then launch it. Confirm it's
running by opening **http://localhost:5600** in your browser — you should see the ActivityWatch
dashboard. Leave it running in the background (set it to start on login).

### 2. Install the "URL in Title" browser extension

Install **URL in Title** from the Chrome Web Store:
**https://chromewebstore.google.com/detail/url-in-title/ignpacbgnbnkaiooknalneoeladjnfgb**

This extension rewrites each tab's title to include URL components. ActivityWatch records the window
title, so anything the extension puts in the title becomes a signal the skill can read.

### 3. Tag each browser profile with a client code

The trick that makes per-client classification work: **use one browser profile per client**, and in
each profile configure the extension to append that client's short code to every title.

In the URL in Title options, set the title format to something like:

```
{title}-{hostname}{path}{args}{hash} - [NZLS]
```

Replace **`NZLS`** with a short code for the client this profile is for (pick your own — `ACME`,
`CON`, whatever). Do this **separately in each browser profile**, using that profile's client code.

The result: every tab you open in your "Acme" profile gets ` - [ACME]` on the end of its title, your
"Beta" profile gets ` - [BETA]`, and so on. ActivityWatch now sees which client each tab belongs to.

> Tip: keep the bracketed code distinct and unlikely to appear by accident (the brackets help).

### 4. Configure ActivityWatch categories

Now teach ActivityWatch to group activity by those codes:

1. Open **http://localhost:5600** → **Settings** → **Categories**.
2. For each client, **add a category** (e.g. `Work > Acme`).
3. Give it a **rule** of type **Regex** matching the bracketed code, e.g. `\[ACME\]`.
4. Save. ActivityWatch will now classify any window/tab whose title contains `[ACME]` as Acme time.

Repeat per client. You can verify it's working on the **Activity** / **Category** views after browsing
in each profile for a bit. (The skill reads the raw events too, so this step mainly powers the AW
dashboard and gives the skill a clean signal — both benefit from accurate codes.)

### 5. Install the skill into Claude Code

From a clone of this repo:

```powershell
pwsh -File install\install_skill.ps1
```

(macOS/Linux: `./install/install_skill.sh`.)

This copies the skill to `~/.claude/skills/daily-timesheet`. It never copies a `.env` or build
artifacts, and it's safe to re-run to update the skill.

### 6. Scaffold your workspace

Pick (or `cd` into) the folder you want to be your timesheet workspace, then:

```powershell
pwsh -File install\setup_workspace.ps1            # uses the current directory
# or target an explicit folder:
pwsh -File install\setup_workspace.ps1 -Workspace C:\Users\you\Work
```

(macOS/Linux: `./install/setup_workspace.sh [path]`.)

This creates the folders the skill uses:

- **`Timesheets/`** — your `.context.md` (see next step) plus optional per-day markdown audit files.
- **`daily_exports/`** — optional historical ActivityWatch dumps (a fallback when AW isn't running).
- **`.mcp/`** — cached catalogs (your Harvest project list, etc.), refreshed automatically.

It also seeds **`Timesheets/.context.md`** from the template (without overwriting an existing one).

### 7. Fill in your `.context.md`

`Timesheets/.context.md` is the **per-user source of truth** — the skill reads it on every run, and
it's what makes classification accurate. It stays **local** (it's git-ignored). Open it and fill in:

- **Preferences** — your timezone, AFK/lunch thresholds, default Harvest task.
- **AW buckets** — your machine's hostname suffix (the skill can discover this on first run).
- **Internal colleagues** — names that, in a Teams title, mean internal work rather than a client.
- **Known external contacts** — people who map to a specific client.
- **Active client projects** — one block per client: its code/bracket tag, Edge profile name,
  Dynamics/SharePoint/Azure DevOps URLs, repo paths, VS Code workspace names — every signal that
  identifies "this is client X".
- **How I bill** — your description style and project-selection conventions.
- **Personal browsing to exclude** — anything that should never be billed.

The skill will also *propose* additions to this file as it learns (showing you the diff first) — it
never edits it silently.

### 8. Set your Harvest API credentials

The skill talks to Harvest via small local scripts that read credentials from a `.env` file at the
skill root. Set it up:

1. Copy the template:
   ```powershell
   Copy-Item "$HOME\.claude\skills\daily-timesheet\.env.example" "$HOME\.claude\skills\daily-timesheet\.env"
   ```
2. Go to **https://id.getharvest.com/developers**:
   - Note your numeric **Account ID** (shown at the top).
   - Create a **Personal Access Token**.
3. Edit the new `.env` and fill in:
   ```
   HARVEST_ACCOUNT_ID=1234567
   HARVEST_API_KEY=pat-...
   ```
4. Verify it works (should print existing entries or nothing, with no auth error):
   ```powershell
   python "$HOME\.claude\skills\daily-timesheet\scripts\harvest_list.py" 2026-01-01 2026-01-01
   ```

> **Security:** your `.env` grants full access to your Harvest account. It is git-ignored — never
> commit it, and never share the skill folder with `.env` still in it. A member-scope token is enough.

### 9. (Optional) Dataverse ticket catalog

If you create work tickets in a **Dataverse / Dynamics 365** org that sync to Harvest as projects, you
can enable ticket-number → title lookups. In the same `.env`, set:

```
DATAVERSE_URL=https://yourorg.crm6.dynamics.com/
PAC_AUTH_PROFILE=YourPacAuthProfileName
```

This requires the [Power Platform CLI](https://learn.microsoft.com/power-platform/developer/cli/introduction)
(`pac`) installed and authenticated. **Leave both blank to skip it** — everything else works
Harvest-only.

If you instead connect Dataverse through an MCP server (e.g. via the `dataverse` plugin's `dv-connect` skill), register it **scoped locally to this workspace** — run `claude mcp add -s local …` from this folder, never user scope — so a single-env server can't follow you into your other client repos.

### 10. Set up the screenshot pipeline

This is a **core part of the skill, not optional.** Screenshots are how the skill disambiguates
generic activity (a bare browser, a terminal, `XrmToolBox`, an IDE with no workspace in the title)
into the right client — the window title alone often can't.

```powershell
pwsh -File "$HOME\.claude\skills\daily-timesheet\scripts\setup_screenshot_pipeline.ps1"
```

This installs [Pillow](https://pillow.readthedocs.io/) and [mss](https://python-mss.readthedocs.io/)
if needed and registers a single Windows scheduled task (`WorkScreenshots`) that runs every ~2.5
minutes on weekdays from **08:30 to 20:00**, saving to `~/Pictures/WorkScreenshots/<date>/`. Each
tick writes **one PNG per monitor** (`HH-MM-SS_m1.png`, `HH-MM-SS_m2.png`, … in left-to-right order,
at native resolution) rather than a single stitched image. Adjust with `-StartTime`, `-EndTime`,
`-IntervalSeconds`. Re-running safely replaces the task.

> **If a previous `WorkScreenshots` task was registered as Administrator**, re-running setup from a
> normal shell fails with `Access is denied`. Run the setup command once from an **elevated**
> PowerShell to replace it; afterward it points at the in-place skill script, so ordinary skill
> updates need no further elevation.

### 11. Use it

In Claude Code, just ask — the skill triggers on natural phrasing:

- *"do my timesheet for yesterday"*
- *"what did I work on Friday?"*
- *"log my Harvest time for 2026-06-17"*
- *"catch up / backfill my timesheets"*

It drafts the blocks, shows you the AFK-derived day skeleton as a reality check, flags anything
uncertain, and asks before posting anything to Harvest.

---

## Customize

- **`Timesheets/.context.md`** (in your workspace) — all your per-user facts. Edit any time.
- **`skill/daily-timesheet/references/classification-rules.md`** — the generic rubric the skill uses
  to turn signals into a `(client, project, task, billable)` decision.
- **`skill/daily-timesheet/references/output-format.md`** — the markdown timesheet template.
- **`skill/daily-timesheet/references/setup.md`** — first-run setup the skill walks you through.
- **`skill/daily-timesheet/references/activitywatch.md`** — what the skill reads out of ActivityWatch.
- **`skill/daily-timesheet/references/new-client-work.md`** — raising a new ticket for unmatched work.
- Thresholds (AFK break length, lunch window, default task) are overridable in `.context.md` under
  `## Preferences`.

---

## Security

- **`.env` holds a token with full Harvest access.** It's git-ignored at both the repo and skill
  level. Don't commit it; don't share the skill folder with it inside.
- The skill **never writes to Harvest without explicit confirmation.**
- Screenshots stay **local** on your machine (`~/Pictures/WorkScreenshots/`); nothing is uploaded.
- Your client list, colleagues, and billing conventions live in `Timesheets/.context.md`, which is
  git-ignored — keep it that way.

---

## What's in this repo

```
activitywatch-to-harvest/
├── README.md                 # you are here
├── CHANGELOG.md              # what changed in each release
├── llms.txt                  # machine-readable setup runbook for Claude Code
├── LICENSE                   # MIT
├── skill/daily-timesheet/    # the skill itself (installed into ~/.claude/skills)
│   ├── SKILL.md              # the skill's instructions
│   ├── .env.example          # credential + optional-config template
│   ├── references/           # classification rules, setup, context template, formats
│   └── scripts/              # Harvest + ActivityWatch + screenshot helpers (stdlib Python)
│       ├── activity_timeline.py  # categorized window timeline from AW category rules
│       ├── afk_blocks.py         # AFK-anchored day skeleton (work_start/end, breaks)
│       ├── harvest_lookup.py     # project_id/task_id lookup across .mcp catalogs
│       └── ...                   # harvest_post/patch/list, refresh_catalogs, screenshot_capture
└── install/                  # install_skill + setup_workspace (PowerShell + bash)
```

## License

MIT — see [LICENSE](./LICENSE).
