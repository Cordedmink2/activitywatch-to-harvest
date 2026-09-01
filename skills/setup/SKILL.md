---
name: setup
description: Walk a first-time user through the parts of installing this plugin that only a person can do — installing the activity source, adding the browser extension, tagging each browser profile with a client code, building the category rules, and getting the screenshot task past endpoint security — verifying each one before moving on. User-invoked.
compatibility: Windows-first. Reads a running ActivityWatch server over HTTP (default http://localhost:5600). Step 5 registers a Windows scheduled task and needs PowerShell plus Python 3.10+; on macOS and Linux there is no screenshot capture to set up and that step is skipped. Needs a harness that can execute local commands and make HTTP requests. Posts nothing to any timesheet provider.
disable-model-invocation: true
---

# setup

The other skills in this plugin fail loudly — a script exits non-zero and says why. The install does not. Every step below can look like it worked and have done nothing: an extension added to the wrong browser profile, a category rule that matches no title, a scheduled task registered against an interpreter that no longer exists. The symptom arrives days later as a timesheet with nothing in it, and by then nobody remembers which step it was.

So this skill is not a list of instructions. It is a list of instructions **with a check after each one**, and it does not move on until the check comes back. Run it top to bottom.

## What this covers, and what it does not

It covers only the residue a person has to do. Everything a machine can do belongs elsewhere and is not repeated here:

- **The values** — credentials, timezone, paths — are declared plugin configuration, collected once at install. This skill checks whether they are *present* and routes a gap to `/plugin configure billables`. It never asks for one, and never asks the user to type a token into the conversation, which is written to disk in the session transcript.
- **The workspace** — `Timesheets/`, the catalogs, and the `.context.md` describing the user's own clients and conventions — belongs to the `daily` skill's own first run. Point at it at the end; do not build it here.

Five steps, and then a stated finish.

## Finding the files this skill needs

Step 5 runs a script that ships with the `daily` skill, in a directory beside this one. Resolve **this** skill's folder from where this `SKILL.md` was read, then look for a sibling named `daily` — or, in the shared export, `billables-daily`, because that directory is flat and every skill in it is prefixed. Check which of the two exists rather than guessing; a wrong prefix fails as "file not found", which reads like a broken install rather than a wrong path.

## Before you start

Three things, in parallel, before step 1:

1. **Is the configuration set?** Check for `HARVEST_ACCOUNT_ID`, `HARVEST_API_KEY` and `TIMESHEET_TIMEZONE` in the environment. Do not collect them here and do not block on them — steps 1 to 5 need none of them, so carry on and re-check at the finish.

   **An absent value here has two causes and they need different things.** Either it was never filled in, or it was filled in and the session hook that republishes it did not run — on Windows that hook needs Git Bash, and without it the values reach nothing. So do not report "not configured" from an empty environment alone. Ask whether the user has filled in `/plugin configure billables`; if they have, the answer is a new session, and if a new session does not fix it, `references/setup.md` in the `daily` skill owns that diagnosis. If they have not, that is the thing to ask for — the dialog, never the conversation.

   **On an exported install there is no dialog to send them to.** A harness that is not Claude Code has no plugin manifest to hold configuration, so the same keys live in a `.env` beside the sibling skill's `SKILL.md`, and `/plugin configure billables` is a command that does not exist there. Work out which install this is at the same time as resolving the sibling directory below, and route a gap to copying that skill's `.env.example` to `.env` instead. Either way the value is written to a file by the user, not typed into the conversation.
2. **Which address is the activity source on?** `TIMESHEET_ACTIVITY_URL` if it is set, otherwise `http://localhost:5600`. Use that address everywhere below.
3. **Is there a working interpreter?** On Windows, prefer `py` over a bare `python`: the bare name is often the Store app-execution alias, a 0-byte stub whose tell is a help message about installing from the Store and exit code 49. Probe it — `py -c "import sys; print(sys.prefix)"` then `py -m pip --version` — rather than trusting that the name resolves. This matters most at step 5, where a broken interpreter and a blocked one look identical.

## Steps

### 1. The activity source is installed and running

**Do** — ask the user to install ActivityWatch and launch it. On Windows `winget install ActivityWatch.ActivityWatch` is the shortest route; https://activitywatch.net/downloads/ is the fallback and the only route on macOS and Linux.

**Verify** — `GET <activity-url>/api/0/buckets/` returns JSON holding a key that starts `aw-watcher-window_` and one that starts `aw-watcher-afk_`. Note the hostname suffix on those keys; the buckets are hostname-scoped and the rest of this run needs the window bucket's full id.

**If it fails** — a refused connection means it is not running (the tray icon, not the installer, is the thing to check). HTML or a 404 instead of JSON means something else holds the port. If the user runs the server on another machine or port, that address is `TIMESHEET_ACTIVITY_URL`: have them set it through `/plugin configure billables` rather than passing it per-command forever, and use the new address for the rest of this run.

### 2. The browser extension is rewriting window titles

Window titles are the only client signal that survives into the activity stream. Without the extension a browser title is a page name, which says nothing about which client the page belongs to.

**Do** — ask the user to install **URL in Title** (https://chromewebstore.google.com/detail/url-in-title/ignpacbgnbnkaiooknalneoeladjnfgb) in **each browser profile they work in**. Extensions are per-profile; installing it once does not cover the others.

**Verify** — have the user browse for a minute in a work profile, then read recent events: `GET <activity-url>/api/0/buckets/<window-bucket>/events?limit=1000`. Keep the events whose `data.app` is a browser, and check that at least one `data.title` carries a hostname — a `host.tld` pattern such as `example.com`. Do not expect all of them to: a profile without the extension, and any window opened before it was installed, legitimately have none. **Zero across every browser event is the failure**, and it localises to this step rather than to the tagging in step 3.

**If it fails** — the usual cause is the extension living in one profile while the user browsed in another. Ask which profile they just used and check it directly. A managed browser can also refuse the install outright: on Edge or Chrome under policy, the extension has to be allow-listed by ID, which is a precise request — see `references/endpoint-security.md`.

### 3. Each work profile tags its titles with a client code

**Do** — explain the arrangement: one browser profile per client, and in each profile the URL-in-Title format appends that client's short code in brackets, e.g. `{title}-{hostname}{path}{args}{hash} - [ACME]`. Help the user pick codes that are short and collision-resistant; write down which profile carries which code, because step 4 has to agree with it exactly and the end of this run hands the list to the `daily` skill.

**Verify** — from the same recent-events read as step 2, check the browser titles for a bracketed code, `\[[A-Za-z0-9-]{2,12}\]`. Go through the codes the user named one at a time: **each has to appear in at least one real title.** A code with zero matches is a profile whose format string was never saved — which is invisible in the options page, because it shows what was typed rather than what was stored.

**If it fails** — the format was saved in a different profile from the one browsed in; or it was typed and the page left without saving. Re-check per profile, not in aggregate: an aggregate pass hides the one profile that is wrong, and that client's whole day comes back uncategorized.

### 4. The category rules match the tags

**Do** — walk the user through the activity source's own UI (`<activity-url>` → Settings → Categories): one category per client, with a **Regex** rule matching the bracketed code, e.g. `\[ACME\]`.

**Verify** — do not trust the UI having saved. `GET <activity-url>/api/0/settings` and read `classes[]`. Each entry carries a `name` (a list — the category and its parents) and a `rule`. **Only test the entries whose `rule.type` is `"regex"`**: a grouping category has `{"type": "none"}` and no `regex` at all, and reaching for a field that isn't there turns a healthy configuration into an error. Compile each regex, honouring its `ignore_case`, and run it against the browser titles collected in step 2.

Judge the result against **the codes the user demonstrated in this session**, not against every rule on the machine: each of those must match at least one real title. A rule that matches nothing is only a defect if its code is one the user just showed you working — on a machine that has been running a while, a zero usually means that client simply wasn't worked on inside the sampled window, and calling it broken sends the user to fix something that is fine. A leftover placeholder (`New class`, `FILL ME`) is a defect either way.

**If it fails** — first separate "the rules are wrong" from "there are no rules to read". The settings endpoint can be absent or return an empty `classes[]` on some versions of the activity source, and the bundled reader is written to survive exactly that; an empty list is not a saved-rules failure and sending the user back to the UI to re-enter rules they already entered wastes their time. Confirm the endpoint answered and returned entries before diagnosing any of the below.

Then, in order of how often it is the answer: a bracketed rule against a bare tag, or a bare rule against a bracketed tag, which matches nothing and silently leaves every block uncategorized; spaces inside an alternation (`Contract | ACME` requires the literal spaces); a rule saved for a code no profile actually emits, which is really a step 3 failure surfacing here. The fix is to make the tag and the rule agree — either end may move, as long as both do. If this install carries `demo/tag-rule-demo.html`, opening it shows each of these failure modes live and is faster than explaining them.

### 5. The screenshot task is registered and actually capturing

Screenshots are what disambiguate generic activity into the right client, so this is a required step on Windows, not an optional one. On macOS and Linux there is no capture pipeline shipped: say so, and skip to the finish.

**Do** — run the `daily` skill's `scripts/setup_screenshot_pipeline.ps1`, resolved as described above. It installs Pillow and mss if they are missing and registers one scheduled task. If `TIMESHEET_SCREENSHOTS_DIR` is configured, pass the same path as `-ScreenshotsDir`: the task runs outside any session and never sees the configured value, so passing it explicitly is what keeps the reader and the writer pointed at the same folder.

**Verify** — three checks, and the second is the one that catches a stale install:

1. `Get-ScheduledTaskInfo -TaskName WorkScreenshots` returns without error.
2. `(Get-ScheduledTask -TaskName WorkScreenshots).Actions` — read the `Execute` and `Arguments` back and confirm they name **this** install's `screenshot_capture.py` and a current interpreter. A machine that once had a hand-installed copy keeps a task pointing at the old path; it registers, reports `Ready`, and captures into a folder nobody reads.
3. Fire one capture by hand and confirm the files land: run `screenshot_capture.py` from the sibling skill's `scripts/`, **passing the same directory as its first argument**, then list that directory's folder for today and confirm `HH-MM-SS_m1.png` files appeared, one per monitor. The script would fall back to the configured value on its own, but only if the session published it — pass it explicitly so a check that comes back empty means no capture rather than two folders. Multi-monitor machines write `_m1`, `_m2`, `_m3`; a laptop on its own writes only `_m1`.

**If it fails** — decide which of three it is before telling the user anything, because they lead to completely different asks:

- **`Access is denied` on registration** — a previous task was registered from an elevated shell. Have the user run the setup script once from an elevated PowerShell; afterwards ordinary updates need no elevation.
- **`No module named mss` / `No module named PIL`, or the task's `LastTaskResult` is `0x80070002`** — an interpreter problem, not a security one. The stored path is absolute, so a Python upgrade or reinstall breaks every trigger from that moment on. Re-run the setup script, or pin the interpreter with `-PythonExe <path>`.
- **The task registers, reports `Ready`, and no image ever appears** — this is the one that is usually endpoint security. Read `references/endpoint-security.md` before saying so to the user: it has to be evidenced before it is escalated.

## When endpoint security is the answer

`references/endpoint-security.md` holds two things: how to establish that a step was actually blocked rather than merely broken, and the exact allow-list requests to hand over once it has been. Read it at the point a step fails in a way that looks like a block — never earlier, and never instead of the checks above.

## Done

Setup is finished when steps 1 to 5 have each passed their own check on this machine, and the three required configuration values are present. Re-check the configuration now if it was missing at the start.

Say so plainly, and say what is now true: the activity source is recording, titles carry client codes, the rules classify them, and screenshots are being captured on a schedule. Then hand over the two things that are not this skill's:

- The `daily` skill has its own first run — it scaffolds the workspace and walks the user through the `Timesheets/.context.md` that carries their clients, colleagues and billing conventions. **Hand over the profile-to-code list from step 3 in writing, and say where it goes: `Timesheets/.context.md`, one entry per client alongside that client's other signals.** It is the same information, re-deriving it is waste, and a list that exists only in this conversation is a list that does not survive the session. Tell the user to invoke that skill next, for a day they have already worked.
- Two things go stale on their own and are worth naming now: a new client needs both a profile tag and a matching category rule, and a screenshot task that stops firing does so silently. `Get-ScheduledTaskInfo -TaskName WorkScreenshots` with a `LastTaskResult` of `0` is the health check.

Nothing in this skill posts to a timesheet provider, and the `daily` skill will not either without passing the confirmation gate. Say that too — it is the question a new user has and does not always ask.
