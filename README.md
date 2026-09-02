# activity-to-timesheet

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

## Install

This repo is a plugin marketplace holding one plugin, `billables`. From inside Claude Code:

```
/plugin marketplace add Cordedmink2/activity-to-timesheet
/plugin install billables@activity-to-timesheet
```

Take the **user**-scope install if you are offered the choice, so the plugin is enabled in every
directory you work in. A **local**-scope install is bound to the one folder you installed it from:
start a session anywhere else and the plugin is disabled there, its session hook never runs, and
every command reports your credentials and timezone missing however carefully you filled them in.
That one is worth avoiding rather than diagnosing — it looks identical to having configured
nothing, and it is missing in *both* shells, so none of the usual fixes apply.
`claude plugin list` shows which scope you got and whether the plugin is enabled where you are.

That gives you `/billables:daily`, `/billables:reconcile` and `/billables:setup`, and asks you
for your own details, once:

| | |
|---|---|
| **Harvest account ID** and **personal access token** | From https://id.getharvest.com/developers. Both are marked sensitive, so Claude Code keeps them in its own credential store — the OS keychain on macOS, `~/.claude/.credentials.json` elsewhere — rather than in a file inside the plugin or in `settings.json`. |
| **Your timezone** | An IANA name (`Europe/London`, `Pacific/Auckland`). Required, with no default: it decides where your day starts and ends, and a guess would date someone else's timesheet wrong without anything visibly failing. |
| **ActivityWatch address** | Optional. Leave blank unless AW runs somewhere other than `http://localhost:5600`. |
| **Screenshot directory** | Optional. Blank means `~/Pictures/WorkScreenshots`. |
| **Workspace directory** | Optional. Blank means the folder you run Claude Code from, if it already looks like a workspace (`.mcp/` or `Timesheets/`) — which is the normal case. Set it if you start sessions elsewhere: a plugin is never installed *inside* a workspace, so there is no second place to fall back to. Answer it after step 6, with `/plugin configure billables`. |

To change any of them later: `/plugin configure billables`.

### Then run `/billables:setup`

It walks you through the parts only a person can do — installing ActivityWatch, the browser
extension, the browser-profile title tags, the category rules and the screenshot task — and
*verifies each one before moving on*, which is the difference that matters: every one of those
steps can look like it worked and have done nothing, and the symptom arrives days later as an
empty timesheet. It tells you when setup is finished.

That is the whole path — you don't need to clone this repo, read the rest of this file, or run a
script by hand. What is left afterwards is scaffolding your workspace
([step 6](#6-scaffold-your-workspace)) and filling in your `.context.md`
([step 7](#7-fill-in-your-contextmd)), which the `daily` skill's first run does with you.

> **Heads-up on antivirus / EDR.** A scheduled task that silently screenshots every few minutes
> looks like spyware to endpoint security, so it (or `pip install`) may be blocked mid-setup. The
> `setup` skill catches that where it happens, and hands you a request your security team can
> action: the `WorkScreenshots` task plus the interpreter and script paths read back off the
> registered task, never a folder-wide exclusion. It establishes that the step really was blocked
> before sending you anywhere.

Paths below of the form `$HOME\.agents\skills\billables-daily\…` are where the **exported** copy
lives — the shared Agent Skills directory, for harnesses that aren't Claude Code (see
[step 5](#5-install-the-skill-on-a-harness-that-isnt-claude-code)). On a plugin install, substitute
the plugin's own skill directory; the skill itself resolves this at run time and never needs to be
told.

---

## How it works (the short version)

1. **ActivityWatch** runs locally and logs which app/window/browser-tab is in focus, plus when you're
   away from the keyboard (AFK).
2. The **"URL in Title" browser extension** stamps a short **client code** into every tab's title
   (e.g. `… - [ACME]`), so browser activity carries which client it belongs to.
3. **ActivityWatch categories** use those codes to auto-classify browser time per client.
4. A small **screenshot grabber** takes a periodic screenshot during work hours, used only to
   disambiguate activity that the window title alone can't pin to a client.
5. The **skill** reads all of the above, drafts a timesheet, shows it to you, and posts confirmed
   blocks to Harvest.

---

## Updating

On a **plugin install**, `/plugin update billables` is the whole story.

On the **exported copy**, you update by getting the latest repo files and regenerating it:

- **If you cloned the repo**, from inside your clone:
  ```powershell
  git pull
  pwsh -File install\install_skill.ps1        # macOS/Linux: ./install/install_skill.sh
  ```
- **If you have no local clone**, just ask your agent to *"update the billables skills from the
  latest activity-to-timesheet repo"* — it'll fetch the current version and regenerate the export.

Regenerating never touches your workspace or your `.context.md`, and your `.env` is kept where it
is. Everything else in each `~/.agents/skills/billables-*` directory is **rewritten from the
plugin**, so a file removed upstream leaves your copy too — there is no stale reference left
behind, and nothing to clean out before a reinstall.

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
> pwsh -File "$HOME\.agents\skills\billables-daily\scripts\setup_screenshot_pipeline.ps1"
> ```

### Coming from a hand-installed copy

There used to be one way in: clone the repo and run `install/install_skill.ps1`, which copied the
skill to `~\.claude\skills\daily-timesheet`. If that folder is on your machine, that is what you
have — and the instruction it came with, *update by re-running the installer*, no longer reaches
it. Re-running the installer today generates the shared Agent Skills export described above and
leaves your copy exactly where it is: still loading, still answering, permanently at the version
you installed. Moving to the plugin is how you get current.

**Almost nothing you care about is in that folder.** Your workspace is elsewhere — `Timesheets/`
with your `.context.md` and your per-day audit files, `daily_exports/`, and the `.mcp/` catalogs —
and none of it is touched by any of this. Your screenshots stay in `~\Pictures\WorkScreenshots`.
What *is* in the folder is the `.env` you filled in, and one setting you have been passing on the
command line:

| In the hand-installed copy | Where it lives now |
|---|---|
| `HARVEST_ACCOUNT_ID`, `HARVEST_API_KEY` in `.env` | `/plugin configure billables`. Both are declared sensitive, so they go to Claude Code's credential store instead of a file in the skill folder. |
| `--utc-offset 12` (13 in daylight saving) on every command | **Your timezone**, asked for as an IANA name — `Pacific/Auckland`, not `12`. This is a change of kind, not a rename: the offset is derived per date, so the twice-yearly edit stops being yours to remember. There is no default, and no conversion from your old number — say where you are. |
| `TIMESHEET_WORKSPACE` in `.env` | **Workspace directory** in `/plugin configure billables`. If you left it blank, look at where your workspace actually is before doing the same here: the old copy also searched the folders it was installed under, which from `~\.claude\skills\` reaches your home directory — so a `~\Timesheets` was found from any session. A plugin is never installed inside a workspace, so blank now means *the folder you start Claude Code in*, and nothing else. Blank is right if that is where you work; otherwise set it. |
| `TIMESHEET_SCREENSHOTS_DIR` — in `.env` on later copies, and as `-ScreenshotsDir` on the scheduled task | **Screenshot directory** in `/plugin configure billables`. Blank still means `~\Pictures\WorkScreenshots`. Read the value off the task rather than trusting the `.env`, which the earliest hand installs had no key for: `(Get-ScheduledTask -TaskName WorkScreenshots).Actions.Arguments`. |
| `DATAVERSE_URL`, `PAC_AUTH_PROFILE` in `.env` | Ordinary environment variables — [step 9](#9-optional-dataverse-ticket-catalog). They belong to one org rather than to every install, so the configuration dialog never asks for them. Do **not** put them in a `.env` inside the plugin folder. |

Then, in order:

1. **Install the plugin** ([more at the top of this README](#install)):
   ```
   /plugin marketplace add Cordedmink2/activity-to-timesheet
   /plugin install billables@activity-to-timesheet
   ```
2. **`/plugin configure billables`**, with the old `.env` open beside you, and fill in the
   right-hand column. Start a new session afterwards: the values reach the scripts at session
   start, in commands run through the **Bash** tool — that is the only shell they are published
   to, so a script run through PowerShell will report them missing.
3. **Read your current screenshot task back before touching it**, because the next step replaces it
   with one built from defaults:
   ```powershell
   (Get-ScheduledTask -TaskName WorkScreenshots).Actions.Arguments
   ```
   Anything non-default in there — a capture directory, `-StartTime`, `-EndTime`,
   `-IntervalSeconds` — is yours to carry over, and nothing carries it for you. A task silently
   back on 08:30–20:00 every 2.5 minutes is the kind of thing you notice a fortnight later, in the
   shape of a day with no evidence on it.
4. **Run `/billables:setup`.** The step you specifically need is that screenshot task: it is
   registered against the capture script *inside the old skill folder*, so it keeps running the old
   copy of the script until it is re-registered — and once you delete that folder it stops
   producing anything at all, showing up as a non-zero `LastTaskResult` rather than as an error
   anyone sees. `setup` reads the registered action back and re-registers it against the plugin's
   copy. Pass the values from step 3 through when it does.
5. **Bill a day you have already billed** — `/billables:daily` on a recent date — and compare what
   it proposes against what is in Harvest. That is the confirmation that your credentials, your
   timezone and your workspace all arrived.
6. **Delete `~\.claude\skills\daily-timesheet`.** Not optional and not cosmetic: until it is gone
   you have two skills that both answer *"do my timesheet"*, and no way to tell from the answer
   which one did. If you ever edited anything in there — a classification rule, a reference doc —
   diff it against the plugin's copy first and move the change over or raise it as an issue; the
   old installer copied files in place and never stopped you. Then delete the whole folder, `.env`
   included: everything in it now lives somewhere your next update can't overwrite.

Your `.context.md` needs no edit for any of this. The one line worth revisiting is any note in it
recording your UTC offset: the timezone is plugin configuration now, and a stale offset written
down beside your preferences is something a future run may read as current.

---

## Prerequisites

- **Windows** (the screenshot pipeline + setup scripts target Windows/PowerShell; the skill logic and
  the `.sh` install scripts work cross-platform, but screenshots are Windows-only as shipped).
- **PowerShell 7** (`pwsh`) for the commands below. Windows ships only Windows PowerShell 5.1, where
  `pwsh` doesn't exist — install it with `winget install Microsoft.PowerShell`, or substitute
  `powershell.exe -File …` in every command (the scripts run under 5.1 too).
- **Python 3.10+** that actually runs — verify with `py -m pip --version` rather than
  `python --version`. On Windows a bare `python` is often the Microsoft Store alias, a 0-byte stub
  that prints an install nag instead of running; and an install whose executables have been separated
  from their `Lib\` runs, prints a version, and still can't reach pip or site-packages. Reaching pip
  is the check that rules out both.
- **[Claude Code](https://claude.com/claude-code)** installed.
- A **Harvest** account you can create a personal access token for.
- A Chromium browser (Chrome/Edge) if you want per-client browser classification.

---

## Setup — step by step

> `/billables:setup` does steps 1–4 and 10 for you, checking each one rather than assuming it.
> This is the same ground written out, for reading first or for working without an agent.

### 1. Install ActivityWatch

On Windows, `winget install ActivityWatch.ActivityWatch` is the quickest route — the manifest pulls
the same official installer as the download page. Otherwise (and on macOS/Linux) get it from
**https://activitywatch.net/downloads/**. Then launch it and confirm it's running by opening
**http://localhost:5600** in your browser — you should see the ActivityWatch dashboard. Leave it
running in the background (set it to start on login).

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
{title}-{hostname}{path}{args}{hash} - [ACME]
```

Replace **`ACME`** with a short code for the client this profile is for (pick your own — `BETA`,
`NIMBUS`, whatever). Do this **separately in each browser profile**, using that profile's client code.

The result: every tab you open in your "Acme" profile gets ` - [ACME]` on the end of its title, your
"Beta" profile gets ` - [BETA]`, and so on. ActivityWatch now sees which client each tab belongs to.

> Tip: keep the bracketed code distinct and unlikely to appear by accident (the brackets help).
> Whatever format you pick, the tag and the category regex in the next step **must agree** — if you
> drop the brackets here, drop them from the regex too, or nothing will ever match.

### 4. Configure ActivityWatch categories

Now teach ActivityWatch to group activity by those codes:

1. Open **http://localhost:5600** → **Settings** → **Categories**.
2. For each client, **add a category** (e.g. `Work > Acme`).
3. Give it a **rule** of type **Regex** matching the bracketed code, e.g. `\[ACME\]`.
4. Save. ActivityWatch will now classify any window/tab whose title contains `[ACME]` as Acme time.

Repeat per client. Then **verify it matches**: browse in a tagged profile for a minute and check the
**Activity** / **Category** views actually attribute that time to the client. If everything lands in
`uncategorized`, the tag format and the regex disagree (bracketed rule vs bare-code tag is the
classic), or the regex has stray spaces inside an alternation (`Foo | Bar` requires the spaces).
(The skill reads the raw events too, so this step mainly powers the AW dashboard and gives the skill
a clean signal — both benefit from accurate codes.)

> **See these failure modes for yourself:** open
> [`demo/tag-rule-demo.html`](./demo/tag-rule-demo.html) in a browser — one self-contained file,
> nothing to install. Four guided walkthroughs show a mismatched tag silently categorising nothing,
> bare codes claiming incidental prose, and a regex with spaces inside its alternation that only
> *looks* like it works.

### 5. Install the skill on a harness that isn't Claude Code

On Claude Code, the two `/plugin` commands at the top of this README are this step — skip it.

Codex, OpenCode, Hermes and the other Agent Skills clients read `~/.agents/skills/` instead, which
no plugin can install into. From a clone of this repo, generate the export:

```powershell
pwsh -File install\install_skill.ps1
```

(macOS/Linux: `./install/install_skill.sh`. Both hand over to
`install/export_agent_skills.py`, which is where the export is documented; pass a directory to
write somewhere other than `~/.agents/skills`.)

That writes one directory per skill — `billables-daily`, `billables-reconcile` and
`billables-setup` — prefixed, because that directory is flat and a bare `daily` among your own
skills says nothing about where it came from. You get the same three skills a plugin install does,
`setup` included, so the manual walkthrough is available to you too: invoke `billables-setup`
however your harness names skills. It's generated from the plugin every time rather than merged
into, so re-running it is how you update; your `.env` is the one thing kept. A maintainer's `.env`
and build artifacts never leave the repo.

### 6. Scaffold your workspace

Pick (or `cd` into) the folder you want to be your timesheet workspace, then:

```powershell
pwsh -File install\setup_workspace.ps1            # uses the current directory
# or target an explicit folder:
pwsh -File install\setup_workspace.ps1 -Workspace C:\Users\you\Work
```

(macOS/Linux: `./install/setup_workspace.sh [path]`.)

**No clone?** The script is a convenience, not a requirement — ask your agent to create the three
folders below in your chosen workspace and copy `references/context.md.example` out of the
installed skill to `Timesheets/.context.md`. That is everything the script does.

This creates the folders the skill uses:

- **`Timesheets/`** — your `.context.md` (see next step) plus optional per-day markdown audit files.
- **`daily_exports/`** — optional historical ActivityWatch dumps (a fallback when AW isn't running).
- **`.mcp/`** — cached catalogs (your Harvest project list, etc.), refreshed automatically.

It also seeds **`Timesheets/.context.md`** from the template (without overwriting an existing one).

### 7. Fill in your `.context.md`

`Timesheets/.context.md` is the **per-user source of truth** — the skill reads it on every run, and
it's what makes classification accurate. It stays **local** (it's git-ignored). Open it and fill in:

- **Preferences** — the judgement calls: AFK/lunch thresholds, what counts as substantive activity,
  the active/thin bands, the timeline's noise floor, your default task. Each line names the
  flag the skill passes for it, so retuning one never means editing a script an update would
  overwrite. (Your *timezone* is not here — it's plugin configuration, set once at install.)
- **AW buckets** — your machine's hostname suffix (the skill can discover this on first run).
- **Internal colleagues** — names that, in a Teams title, mean internal work rather than a client.
- **Known external contacts** — people who map to a specific client.
- **Active client projects** — one block per client: its code/bracket tag, Edge profile name,
  Dynamics/SharePoint/Azure DevOps URLs, repo paths, VS Code workspace names — every signal that
  identifies "this is client X".
- **Work kinds** — the skill classifies each block as one of seven neutral kinds (`Meeting`,
  `Development`, `Documentation`, `Project management`, `Testing`, `Investigation`,
  `Internal admin`) and this table says what *your* Harvest account calls each one. No task name
  ships with the skill, because no two accounts spell theirs the same way. Easiest filled in after
  step 8, once your catalogs exist — the skill can read the task names off your own projects and
  offer them. Leave it out and it works that out per block and proposes the row back to you.
- **How I bill** — your description style and project-selection conventions.
- **Personal browsing to exclude** — anything that should never be billed.

The skill will also *propose* additions to this file as it learns (showing you the diff first) — it
never edits it silently.

### 8. Set your Harvest API credentials

1. Go to **https://id.getharvest.com/developers**:
   - Note your numeric **Account ID** (shown at the top).
   - Create a **Personal Access Token**. A member-scope token is enough.
2. Run **`/plugin configure billables`** and paste both in. They go to Claude Code's credential store,
   not into the plugin folder, so there is nothing to git-ignore and a plugin update can't carry them
   off. On macOS that store is the OS keychain; on Windows and Linux it is `~/.claude/.credentials.json`
   — a file in your home directory, so treat that directory as holding a secret.
   Set your **timezone** here too if you skipped it at install — the scripts refuse to date a day
   without one.
3. Start a new session — the values are published at session start, into commands Claude Code runs
   through its **Bash** tool. Then verify there (on Windows use `py` — a bare `python` is often the
   Store stub). It has to be the Bash tool: the values are published as a POSIX shell fragment, so
   the same command in PowerShell reports the credentials missing on an account that is set up
   perfectly well.
   ```bash
   py "<skill folder>/scripts/harvest_list.py" 2026-01-01 2026-01-01
   ```
   Entries print one per line; a day with no entries prints `(no time entries from … to …)`.
   Either of those with no auth error is success — a 401/403 means the token is wrong.

> **Exported install** (step 5's clone route, rather than `/plugin install`): there's no
> configuration dialog, so the same keys go in a `.env` at the skill root instead — copy
> `.env.example` beside it and fill in `HARVEST_ACCOUNT_ID`, `HARVEST_API_KEY` and
> `TIMESHEET_TIMEZONE`. That file grants full access to your Harvest account: it is git-ignored,
> never commit it, and never share the skill folder with it still in place.

### 9. (Optional) Dataverse ticket catalog

If you create work tickets in a **Dataverse / Dynamics 365** org that sync to Harvest as projects, you
can enable ticket-number → title lookups by setting two values:

```
DATAVERSE_URL=https://yourorg.crm6.dynamics.com/
PAC_AUTH_PROFILE=YourPacAuthProfileName
```

These two are deliberately **not** declared plugin configuration: they belong to one org's setup
rather than to every install, so `/plugin configure billables` never asks for them. Where they go
depends on which install you have:

- **Plugin install:** set them as ordinary environment variables. Not in a `.env` inside the plugin
  folder — a `/plugin update` overwrites that folder, and the skill's own diagnostic tells you to
  delete any `.env` it finds there, because on a plugin install one silently outranks the
  configuration dialog.
- **Exported install** (step 5): the skill root's `.env`, alongside the Harvest keys.

The profile must be a **named** one — the refresh selects it with `pac auth select --name`, and
`pac auth create` without `--name` creates an unnamed profile it can never select. Authenticate with
`pac auth create --name YourPacAuthProfileName --environment https://yourorg.crm6.dynamics.com/`, or
name an existing profile without re-authenticating: `pac auth name --index <N> --name <name>`.

This requires the [Power Platform CLI](https://learn.microsoft.com/power-platform/developer/cli/introduction)
(`pac`) installed and authenticated. **Leave both blank to skip it** — everything else works
Harvest-only.

If you instead connect Dataverse through an MCP server (e.g. via the `dataverse` plugin's `dv-connect` skill), register it **scoped locally to this workspace** — run `claude mcp add -s local …` from this folder, never user scope — so a single-env server can't follow you into your other client repos.

### 10. Set up the screenshot pipeline

This is a **core part of the skill, not optional.** Screenshots are how the skill disambiguates
generic activity (a bare browser, a terminal, `XrmToolBox`, an IDE with no workspace in the title)
into the right client — the window title alone often can't.

```powershell
pwsh -File "$HOME\.agents\skills\billables-daily\scripts\setup_screenshot_pipeline.ps1"
```

This installs [Pillow](https://pillow.readthedocs.io/) and [mss](https://python-mss.readthedocs.io/)
if needed and registers a single Windows scheduled task (`WorkScreenshots`) that runs every ~2.5
minutes on weekdays from **08:30 to 20:00**, saving to `~/Pictures/WorkScreenshots/<date>/`. Each
tick writes **one PNG per monitor** (`HH-MM-SS_m1.png`, `HH-MM-SS_m2.png`, … in left-to-right order,
at native resolution) rather than a single stitched image. Adjust with `-StartTime`, `-EndTime`,
`-IntervalSeconds`. Re-running safely replaces the task.

The setup probes each Python it can find with a real import and skips broken ones — the 0-byte Store
stub and the "install exists but can't reach its own libraries" case both showed up in the wild. If
it still picks the wrong interpreter, pin one with `-PythonExe C:\path\to\python.exe` (a broken
`-PythonExe` is an error, never a silent fallback).

> **If a previous `WorkScreenshots` task was registered as Administrator**, re-running setup from a
> normal shell fails with `Access is denied`. Running setup *elevated* clears the error and brings
> the trap straight back: the replacement is owned by `BUILTIN\Administrators` too, so the next
> ordinary re-register fails the same way. Break it in two steps instead — remove the task from an
> **elevated** PowerShell, then register the new one from a normal shell, so it ends up owned by
> you and no later update needs elevation:
>
> ```powershell
> Unregister-ScheduledTask -TaskName WorkScreenshots -Confirm:$false   # elevated
> ```

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
- **`skills/daily/references/classification-rules.md`** — the generic rubric the skill uses
  to turn signals into a `(client, project, task, billable)` decision.
- **`skills/daily/references/output-format.md`** — the markdown timesheet template.
- **`skills/daily/references/setup.md`** — first-run setup the skill walks you through.
- **`skills/daily/references/activitywatch.md`** — what the skill reads out of ActivityWatch.
- **`skills/daily/references/new-client-work.md`** — raising a new ticket for unmatched work.
- Thresholds (AFK break length, what counts as substantive activity, the active/thin bands, the
  timeline's noise floor and gap fold, lunch window, default task) are overridable in `.context.md`
  under `## Preferences` — each line names the flag it maps to. Machine and account facts
  (credentials, timezone, ActivityWatch address, screenshot and workspace directories) are plugin
  configuration instead: `/plugin configure billables`.

---

## Security

- **Your Harvest token has full access to your account.** On a plugin install it is declared
  sensitive, so Claude Code holds it in your OS keychain — it is never written into the plugin
  folder or into `settings.json`. On an exported install it lives in a `.env`, which is git-ignored
  at both the repo and skill level: don't commit it, and don't share the skill folder with it inside.
- The skill **never writes to Harvest without explicit confirmation**, and that is enforced rather
  than only promised: the two scripts that create or amend a time entry write nothing unless passed
  `--confirm`, and print what they would have sent instead. So an agent that reached them without
  being asked to bill still bills nothing.
- Screenshots stay **local** on your machine (`~/Pictures/WorkScreenshots/`); nothing is uploaded.
- Your client list, colleagues, and billing conventions live in `Timesheets/.context.md`, which is
  git-ignored — keep it that way.

---

## What's in this repo

```
activity-to-timesheet/
├── README.md                 # you are here
├── .github/ISSUE_TEMPLATE/   # the form behind "New issue"
├── CHANGELOG.md              # what changed in each release
├── LICENSE                   # MIT
├── demo/
│   └── tag-rule-demo.html    # interactive demo of the tag/category-rule failure modes
├── .claude-plugin/           # marketplace + plugin manifests, incl. the configuration it asks for
├── hooks/                    # SessionStart: hands that configuration to the bundled scripts
├── skills/setup/             # /billables:setup — the manual steps, each one verified
├── skills/reconcile/         # /billables:reconcile — days worked but never billed
├── skills/daily/             # /billables:daily — the timesheet run
│   ├── SKILL.md              # the skill's instructions
│   ├── .env.example          # credential + optional-config template
│   ├── references/           # classification rules, setup, context template, formats
│   └── scripts/              # Harvest + ActivityWatch + screenshot helpers (stdlib Python)
│       ├── activity_timeline.py  # categorized window timeline from AW category rules
│       ├── afk_blocks.py         # AFK-anchored day skeleton (work_start/end, breaks)
│       ├── aw_client.py          # shared ActivityWatch REST helpers for the two above
│       ├── harvest_lookup.py     # project_id/task_id lookup by code, name or client
│       ├── skill_config.py       # the one seam every script reads a setting through
│       └── ...                   # harvest_post/patch/list, refresh_catalogs, screenshot_capture
├── tests/                    # guards on the install/setup scripts a new user runs first
└── install/                  # export_agent_skills.py (the shared-directory export the
                              #   install_skill wrappers run) + setup_workspace
```

## Reporting a problem

Open an issue — the ["New issue"](../../issues/new/choose) form asks for the version, what you
asked for, and what the skill did instead.

Two things worth knowing before you do:

- **Not everything is a defect.** If the skill didn't know one of *your* clients, signals or
  machine facts, that belongs in your own `Timesheets/.context.md`. If a window title comes back
  `uncategorized`, that's an ActivityWatch category rule on your machine — `references/setup.md`
  covers it. Neither is fixed by a change here.
- **Redact before you paste.** This tool reads window titles, screenshots and Harvest entries, so
  its output carries client names, project codes and file paths. Issues are public.

The skill can do this for you: at the end of a run it sorts what it learned, and for anything that
looks like a genuine defect it will draft the report and offer to file it. It won't file anything
without you saying yes.

## License

MIT — see [LICENSE](./LICENSE).
