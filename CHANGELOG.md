# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **The day the clocks change is read at its real length.** The configured `TIMESHEET_TIMEZONE` was
  reduced to one offset per day, read at local noon, and applied to every instant in it. On a
  transition day that is wrong at both ends at once: `2026-04-05` in `Pacific/Auckland` is
  twenty-five hours long, so ActivityWatch was asked for the day an hour late and never handed back
  the first hour of work, while everything before the change rendered an hour early — a session that
  started at 00:40 reported starting at 23:40 the night before. Neither failure raised anything; the
  day just read short. Each instant is now converted at the offset in force for it, so a
  twenty-five-hour autumn day and a twenty-three-hour spring one are both bounded correctly. A span
  crossing the change is reported at its elapsed length, which is an hour longer than its two clock
  times look.
- **The hour the clocks go back no longer prints two instants as one time.** On a fall-back day the
  local clock repeats an hour, and both passes rendered `02:30:00`: an hour-long break across the
  change came out as `02:30:00-02:30:00`, two active spans an hour apart abutted, and the timeline's
  web rows — sorted on the rendered string — put that hour's browsing in the wrong order. The second
  pass is now suffixed `*` (`02:30:00*`), and `--window` / `--cover` read the suffix back, so a block
  lifted out of one script's output names the same instant when handed to another. Unmarked still
  means the first pass, and no other time on any other day changed. Web rows sort on the instant.
  A marker on a time the clock reads only once (`09:00*`, or `03:00*` that same morning) is refused
  by name rather than quietly ignored. Before it reaches Harvest the marker must be stripped, and an
  entry must not span the change — `references/output-format.md` §Conventions has the split, which is
  not where it looks: the transition instant is `02:00*`, and `03:00` is an hour after it.
- Headers name the zone (`zone Pacific/Auckland`) when one is configured, rather than printing a
  single offset that a transition day does not have. A run passing `--utc-offset` still reads
  `offset UTC+13`, which is what was typed.
- **`--utc-offset 99` is refused with a message** instead of raising out of the zone constructor.
- **The copied-in installer's `.env.example` lists `TIMESHEET_TIMEZONE`.** A plugin install is asked
  for the key at setup, but a copied-in one only ever learns of a setting from this template — and it
  still described the 0.4 surface. Someone who filled in the two Harvest keys and ran the skill hit
  "refuses to date a day" on their first attempt, over a required setting the file never mentioned.
  `TIMESHEET_ACTIVITY_URL` is listed alongside the other optional settings for the same reason.

## [0.5.0] - 2026-08-28

### Added
- **The plugin declares its configuration surface, and a fresh install asks for it once.**
  `HARVEST_ACCOUNT_ID`, `HARVEST_API_KEY` and `TIMESHEET_TIMEZONE` are required;
  `TIMESHEET_ACTIVITY_URL`, `TIMESHEET_SCREENSHOTS_DIR` and `TIMESHEET_WORKSPACE` are optional and
  skipped. `/plugin configure billables` changes them later. The two Harvest fields are declared
  sensitive, so Claude Code stores them in its own credential store instead of a file inside the
  plugin — the OS keychain on macOS, `~/.claude/.credentials.json` on Windows and Linux. Nothing for
  this skill to git-ignore, and a plugin update cannot carry them off. A SessionStart hook publishes
  the values into the session so the bundled scripts resolve them through the existing seam; no new
  precedence and no second reader.
- **The judgement tunables are settable without editing a script.** `afk_blocks.py` gains `--solid`,
  `--blip-gap`, `--min-uncovered`, `--active-band` and `--thin-band`; `activity_timeline.py` gains
  `--noise-floor` and `--gap-fold`. Each shipped constant is now that flag's default, so an existing
  run is unchanged. They belong to how a person works, so they are documented in the workspace's
  `## Preferences` — which names the flag for each — rather than in a shipped file an update
  overwrites.
- **`TIMESHEET_ACTIVITY_URL`** points the scripts at an ActivityWatch running somewhere other than
  `http://localhost:5600`.

### Changed
- **`--utc-offset` no longer defaults to 12.** Both scripts resolved the day's boundaries at UTC+12
  when no offset was passed, so every user outside New Zealand got a day boundary up to twelve hours
  out — and nothing failed: events landed on the wrong date and the only symptom was a day that
  looked oddly short. The offset now comes from the configured `TIMESHEET_TIMEZONE`, read at the
  date being analysed; a run with neither that nor `--utc-offset` stops and says which value it
  needs. `--utc-offset` still overrides for a single run. The `.context.md` template no longer seeds
  a New Zealand timezone into a new user's workspace.
- **The "credentials not found" message leads with `/plugin configure`**, keeping the `.env` route
  for the copied-in install that has no harness to ask.

### Upgrading
- **Delete any `.env` inside an installed plugin.** The two routes now carry the *same* six keys,
  and the seam puts `.env` above the process environment where the configured values arrive — so a
  leftover file silently outranks `/plugin configure`. The tell is a rotated token that still 401s,
  or a timezone change with no effect. `references/setup.md` § "When the configuration does not
  arrive" covers it, along with the other cause: on Windows the session hook that publishes the
  configuration runs under Git Bash, and cannot start without it (`winget install Git.Git`).
- **The repo is now a plugin marketplace holding one plugin, `billables`.** `/plugin marketplace
  add Cordedmink2/activity-to-timesheet` then `/plugin install billables@activity-to-timesheet`
  installs it; the skill is invoked as `/billables:daily`. The repo is renamed
  `activity-to-timesheet` — the old name still resolves through GitHub's rename redirect.
- **The skill moved from `skill/daily-timesheet/` to `skills/daily/` and is declared as `daily`.**
  The manual install scripts still work and now copy to `~/.claude/skills/daily`; they print a note
  if an older `daily-timesheet` folder is still installed, because two copies of one skill means
  either can answer.
- **`SKILL.md` no longer hardcodes a path into a Claude-specific skills directory.** The `scripts/`
  prefix is resolved from the directory `SKILL.md` was read from, so the bundled scripts are
  findable wherever the skill is installed. A test now fails on any instruction that writes one down.

### Fixed
- **Workspace auto-detection is anchored on the install shape instead of a depth.** It walked two
  arbitrary ancestors and took the first that looked workspace-shaped, so an install nested one
  level deeper than expected resolved to whatever real workspace happened to be above it — silently:
  the refresh reported success and the stale catalogs surfaced days later. It now requires the skill
  to sit directly inside a `skills/` directory, and never treats a plugin's own root as a workspace.
  **Consequence for plugin installs:** the skill is not inside a workspace, so nothing is
  auto-detected and `TIMESHEET_WORKSPACE` has to be set. Refusing is the point — the alternative is
  guessing — and the install now asks for it, as a declared optional option.

## [0.4.11] - 2026-08-28

### Changed
- **A day the user has already ruled on is no longer re-litigated.** Step 1's already-covered
  branch named `Timesheets/<date>_harvest_responses.json` as "a free done-marker", which invites
  an agent to test that the file exists and never open it. It now says to read it whole — the
  schema is ad hoc, so there is no key to look under — and states that a ruling the user gave on a
  window binds: recomputing an `active_ratio` or re-reading a screenshot is the same argument on
  the same data, not new evidence.
- **A proposed *reduction* now pulls in `references/classification-rules.md`.** The branch skips
  the rubric deliberately to avoid redrafting, which is right while verifying and wrong the moment
  it starts subtracting — the guards against over-reading a thin block (supervised agents, meetings
  invisible to the window watcher, browser rows spanning hours) all live there.
- **Screenshot guidance widened.** The folder mechanics licensed checking the other monitors only
  "when hunting a client signal", which still permitted a single-monitor read to answer "is
  anything happening at all". A capture showing wallpaper, a lock screen or a black screen is now
  stated to be evidence about that monitor and nothing else; the AFK watcher owns active/idle.
- Frontmatter `description` shortened to match `disable-model-invocation: true`.

### Added
- **Byte size as screenshot triage.** A black or locked capture is ~6-7 KB, so `Length` ranks a
  long index before spending image tokens on it — with both observed limits: a large file can be a
  detailed wallpaper photo, and constant sizes are a fact about a screensaver, not about the user.
- `references/self-development.md` gains two rows in the multi-copy drift table: "screenshots never
  settle active/idle" and "check the other monitors before trusting one".

### Notes on the evidence
Both changes are rung 1 — an observed production failure, recorded in `TESTING.md`. A prior
session's audit proposed deleting one entry and trimming another on activity-ratio and
single-monitor screenshot evidence; both entries existed because the user had explicitly asked for
them a week earlier, and the response file said in terms that the ratio does not govern them.
Reading a second monitor at the same timestamps refuted both. Caught at the confirmation gate,
nothing was deleted. **The fixes themselves are untested** — the post-fix fresh-agent arms were not
run, so the rung-1 evidence establishes the failure, not the repair.

Also carries reference-file work from earlier sessions that had not been published: the long
browser row rule in `classification-rules.md`, and two observed defects in `new-client-work.md`
(`head`/`grep` buffering the Dataverse device-code prompt into an apparent hang; `--ponumber`
doubling the work-item reference in a client-facing project name).

## [0.4.10] - 2026-08-19

### Upgrading

Re-run the installer; no config or task changes. If you installed this skill rather than
maintaining it, the new `references/reporting-issues.md` is how a run now routes a defect back
here.

### Added
- **A way to report a defect upstream.** Step 11 gains a third destination: a script returning a
  wrong answer, a guard that didn't fire, or an instruction wrong for every user goes to
  `references/reporting-issues.md` when the user installed the skill, and to
  `references/self-development.md` when they maintain it. The reference carries the repository
  URL, what must be redacted first, and the confirmation gate.
- **`.github/ISSUE_TEMPLATE/skill-defect.yml`** — an issue form for anyone arriving at the repo,
  with a required redaction acknowledgement. Plus a "Reporting a problem" section in the README,
  which previously said nothing about issues at all.

### Notes on the evidence
Three fresh agents were given a genuine uncovered script defect and an installed-skill scenario.
All three proposed reporting it upstream unprompted, so no rule tells them to; all three refused
to file it under any circumstances, so the rule *permits* filing behind an explicit yes rather
than restraining it; all three went looking in `self-development.md` for the route, so that file
now points at the right one; and **none of the three mentioned redaction** while drafting a public
issue off a client timesheet run, which is what the new reference mostly exists to fix.

Re-run against this release, same fixture: redaction 0/3 → **3/3**, repo URL without asking 1/3 →
**3/3**, and 3/3 now ask for a yes to *filing* as distinct from agreeing the defect is real.

A fourth destination for "the machine, not a document" was drafted and dropped: the same test
showed agents already route `uncategorized` categories to `references/setup.md` unaided.
`TESTING.md` has both runs, including a first measurement discarded for a leading question in its
own prompt.

`gh issue create` ships **unexercised** — GitHub was unreachable from the release machine.

## [0.4.9] - 2026-08-19

### Upgrading

Re-run the installer; no config or task changes.

### Fixed
- **Verifying an already-billed date never checked what the entries were billed *to*.** Step 1's
  already-covered branch asked for `--cover` plus the `<0.4` idle band, and both are time
  questions — an entry with the right clock and the wrong project passes `--cover` perfectly. In
  a three-agent test against 0.4.8, two agents verified a day containing a known mis-booked entry
  and reported it holds; both stated they had skipped the screenshots and the rubric because the
  branch did not ask for them. The branch now requires reading one screenshot inside every
  non-billable or internal entry, and `classification-rules.md` scopes its timesheet-admin
  screenshot check to verifying an existing entry as well as booking a new one. Re-run after the
  fix: 3/3 caught it.
- **An exclusivity claim in the Step 8 checklist** ("this is the only one that would catch a
  duplicate day") — the shape `references/self-development.md` forbids, committed in the same
  change as the rule forbidding it. Reworded to state what the line does rather than what no
  other line does.

### Changed
- **Step 12 no longer cites its own test results.** The rep count behind the today-in-progress
  bullet moved to `TESTING.md`, which owns test records.

## [0.4.8] - 2026-08-19

### Upgrading

Re-run the installer; no config or task changes. Two behaviour changes worth knowing:
the skill now checks Harvest before rebuilding a date you named, and it reads the whole
of `Timesheets/.context.md` on every run rather than whatever part it thought it needed.

### Fixed
- **A dated run never checked whether the date was already billed.** Given "do yesterday"
  the workflow went straight to rebuilding the day from ActivityWatch. Steps 3, 6 and 8 all
  validate the proposal against ActivityWatch and none against Harvest, so a duplicate day
  passed every guard and double-billed the client — `--cover` reports clean, because the
  blocks are correct, just already posted. Step 1 now checks Harvest (and
  `Timesheets/<date>_harvest_responses.json`) before loading anything, with a restatement in
  the pre-post checklist. Found independently by all three agents in a live three-rep test.
- **Timesheet-admin time was being back-billed onto real client work.** The timesheet run
  happens after the last block it can bill, so it lands on the previous one — observed as a
  24-minute block posted as non-billable admin while every screenshot across it showed
  client work. The rubric now requires confirming a timesheet surface is actually on screen
  before booking timesheet-admin time.
- **Step 12 was ambiguous about today-in-progress**, and three test agents split three ways
  on it. Today-so-far now explicitly counts as a next date. The instruction to re-invoke the
  skill after `/clear` was prose and survived only one run in three; it is now a bullet.

### Changed
- **`Timesheets/.context.md` must be read whole, every run** — never grepped, sliced or
  skimmed. Its facts are cross-cutting, so a partial read yields confident wrong answers
  instead of an obvious gap. This is what the size budget is for, so a file over budget gets
  trimmed rather than partially read.
- **`afk_blocks.py --window` is a focused report.** It keeps the header and the
  `work_end`/blip/tail warnings and drops the breaks and active-spans lists, so validating
  four thin stretches no longer costs four whole-day dumps. `--cover` and `--json` unchanged.

## [0.4.7] - 2026-08-19

### Upgrading

Docs only — no script, config or task changes. `git pull` then re-run the installer.

### Fixed
- **`SKILL.md`'s "Files in this skill" list had drifted.** It omitted `scripts/aw_client.py`
  — a runtime import of both `afk_blocks.py` and `activity_timeline.py`, and already listed
  in the README's directory tree — plus `VERSION`, `tests/` and `pytest.ini`. Nothing catches
  this: the installers and mirrors copy whole trees, so a missing entry never stops a file
  shipping, it just leaves the reader with a wrong map.
- **An exclusivity claim in `references/classification-rules.md`.** "This table is the single
  authoritative mapping — `SKILL.md` does not carry its own copy" is the shape the skill's own
  maintainer rules ban, because it enforces a snapshot and rots silently while still reading
  as authoritative. Reworded to name the owner instead.
- Two rationales that cited a multi-day run in one session, which Step 12 now rules out.

## [0.4.6] - 2026-08-19

### Upgrading

Skill instructions only — no script, config or task changes. `git pull` then re-run
`install\install_skill.ps1`; the `WorkScreenshots` task is unaffected. Behaviour change
worth knowing before your next run: the skill now finishes one date and stops, and asks
you to `/clear` before the next one rather than working through a backfill in a single
session.

### Added
- **Step 12 — one date per session, then reset.** After the date is done (posted or
  explicitly not, wrapped up, and every `.context.md` proposal written or declined), the
  skill asks for a `/clear` before starting the next date, and re-invocation with it since
  `/clear` unloads a non-model-invocable skill. `/compact` is the named fallback if you'd
  rather keep the thread; declining both is honoured. Nothing is said when you're all
  caught up.

### Changed
- **Step 1 takes the oldest gap day instead of asking which to do.** With one date per
  session the choice no longer arises, so the "ask when several prior gap days compete"
  clause is gone; the full gap list is still reported on a no-date run.
- **Step 10 no longer names the next date.** It reports whether days are outstanding and
  leaves the next date to Step 12, so the reset ask comes before the next day is opened.
- `references/self-development.md` registers the new rule's three copies in its
  duplication table.

## [0.4.5] - 2026-08-19

### Upgrading

Docs and demo only — no skill-script, config or task changes. `git pull` then re-run
`install\install_skill.ps1`; the `WorkScreenshots` task is unaffected.

### Added
- `demo/tag-rule-demo.html` — a self-contained interactive demo of the tag/category-rule
  failure modes (mismatched formats, bare codes claiming incidental prose, spaces inside
  alternations), linked from README step 4 and offered by the setup runbook. All sample
  clients and URLs are fictional (ACME, BETA, Ledger, Nimbus).

### Fixed
- **ActivityWatch *is* on winget** — `winget install ActivityWatch.ActivityWatch` pulls the same
  official installer as the download page, and it was the faster route on the install that prompted
  the 0.4.4 docs. `llms.txt` had it flatly backwards ("not on winget — the direct download is the
  only route"); both it and README step 1 now lead with winget on Windows.
- **`llms.txt` handed the agent commands that fail on a stock Windows box.** Steps 8 and 10 used
  `~/…` paths, which Windows PowerShell 5.1 passes to a native command literally (only PowerShell 7
  expands them), and `python`, which is usually the Store stub the same file warns about two
  sections earlier. They now use `py "$HOME/…"`, and environment detection says to check `pwsh`
  exists before using it.
- The demo's second walkthrough claimed a bare `ACME` rule wasn't in the emailed-contract title and
  needed broadening to `Contract|ACME` to cross-claim it. It was: the rule already matched
  `acmetrust.sharepoint…` in the URL. The step now shows that directly, with no rule edit.

### Changed
- README: step 8's credential check now uses `py` and documents the
  `(no time entries …)` success notice; the repo map gained `demo/` and the
  previously-missing `tests/`.
- The prerequisite Python check is `py -m pip --version` — reaching pip is the one check that rules
  out both the 0-byte Store stub and a split install (which prints a version quite happily).
- `llms.txt`'s AV/EDR rule now says to prove a block — a log line, a quarantine entry, a denied
  registration — before sending the user to IT. The install that produced these notes raised an
  allow-list request for what turned out to be a split Python install needing no ticket.

## [0.4.4] - 2026-08-19

### Upgrading

No config or task changes: `git pull` then re-run `install\install_skill.ps1` (the
registered `WorkScreenshots` task keeps working — the interpreter probing applies the
next time the setup script runs). If your clone carries local edits to
`setup_screenshot_pipeline.ps1` or `tests/test_install_scripts.py` from a pre-0.4.4
session hotfix, discard them first (`git checkout -- .`) — this release supersedes them.

### Fixed
- **`setup_screenshot_pipeline.ps1` took the first interpreter that existed, and both
  failure modes on a coworker's first install were interpreters that existed.** The
  Windows Store app-execution alias is a 0-byte `python.exe` that runs nothing, and a
  split install (executables separated from `Lib\`) imports the stdlib through a registry
  `PythonPath` while `sys.prefix` — and with it pip and site-packages — resolves to
  garbage. Either one, selected on existence, registers a task that never captures a
  single screenshot. Every candidate is now probed with a real import (via
  `Start-Process`, because `&` doesn't wait on the GUI-subsystem `pythonw` and leaves
  `$LASTEXITCODE` stale), 0-byte stubs are rejected on size, and the split-install
  warning on stderr fails the probe even on exit 0. A new `-PythonExe` parameter pins the
  interpreter explicitly; a broken `-PythonExe` is an error, never a silent fallback.
- **A test could register a real scheduled task.** The PS 5.1 parameter-binding test
  stripped `PATH` and relied on the "Python not found" guard as its early exit; with the
  interpreter now resolved by probing (system launcher included), that guard is no longer
  guaranteed to fire. The test runs under `-DryRun` with a cleanup fixture, so it can
  never register anything regardless of what the resolver finds.

### Changed
- `harvest_list.py` prints `(no time entries from … to …)` to stderr when the range is
  empty. Success-with-no-entries and a run that silently did nothing were previously
  identical on stdout, and the setup runbook's credential check reads exactly this case.
- Setup docs (`llms.txt`, README, `references/setup.md`) carry the lessons from that
  first coworker install: probe Python rather than trusting names on PATH; ActivityWatch
  is not on winget; the URL-in-Title tag format and the AW category regex must agree
  (and get verified against real events, not the UI); the Dataverse `pac` profile must be
  *named* (`pac auth create --name …`, or `pac auth name --index <N>` to fix an unnamed
  one); Harvest tokens are better pasted into `.env` than into the chat, which is saved
  to disk in plaintext.

## [0.4.3] - 2026-08-18

### Fixed
- **`afk_blocks.py` could not see a break the AFK watcher never recorded.** The watcher
  writes nothing at all while the machine sleeps or is locked, so a long absence leaves a
  *hole* in the event stream rather than an `afk` event. `find_breaks()` filtered on
  recorded `afk` spans and `active_spans()` split only on one, so neither ever measured
  the elapsed time between consecutive events: a hole was invisible to the first and
  merged straight across by the second. On a real day carrying a three-hour morning gap
  and a 47-minute lunch, the skeleton reported `breaks: (none)` and a single unbroken
  12-hour active span — asserting the absence of breaks rather than merely missing them,
  which matters because the skill is told to take that list verbatim. Holes of at least
  the break threshold are now materialised as explicit spans, so they both list as breaks
  and split the surrounding active span.

### Changed
- Breaks in `afk_blocks.py --json` carry a `kind` of `afk` or `gap`, and gap breaks are
  tagged in the text output. A watcher outage is absence of evidence; a recorded `afk`
  span is evidence the user was at their desk and idle. Conflating the two is what allowed
  an empty breaks list to be read as proof the user was never away.
- `classification-rules.md` §5 is now **Environment identifier** rather than "URL
  pattern". Admin tools that connect to a client environment — XrmToolBox, database and
  API clients, RDP sessions, CLI auth profiles — carry a fixed product name in the title
  and show the environment only on screen. The connected environment decides the client;
  the tool name never does, and neither does the workspace behind it. §6's adjacency rule
  explicitly does not extend to them, since connecting to a different environment is
  frequently the switch point itself.
- `TESTING.md` records three findings from 2026-08-18: the data-hole defect above, the
  environment-connected-tools signal, and the replacement of a hand-written prefix →
  client list with a derivation from the Harvest catalogs (a per-user `.context.md`
  change, recorded here because the reasoning belongs with the test record).

## [0.4.2] - 2026-08-14

### Fixed
- **`harvest_lookup.py` could not find a project by its client's name.** It matched
  `project.code` and `project.name` only, so a project named for the *work* it covers —
  carrying the client's name solely on `client.name` — was invisible to a search for that
  client. Where the client also had an old presales or shell project named after them, the
  lookup returned that shell as the only hit, and its all-non-billable task set is easy to
  accept as the answer. Matching now includes `client.name`, in both the catalog path and
  the time-entries fallback, with results ranked exact-code → code/name → client-only and
  each match reporting `matched_on` plus the client. The human-readable listing shows the
  client alongside the project name.

### Changed
- `SKILL.md` documents client name as a first-class search term for `harvest_lookup.py`,
  and warns that the top hit is not automatically the right project — read every candidate,
  and treat an all-non-billable task set as the tell for a shell project.

## [0.4.1] - 2026-08-14

Documentation and test-suite corrections found by reading the four `test_edge_*.py`
modules line by line. No script behaviour changed.

### Fixed
- **Three test docstrings described defects 0.4.0 had already fixed** — a `harvest_patch`
  guard documented as absent while the test's own assertion proved it fires, and two
  claims that `harvest_client.request()` reads an error body without closing it. The
  `ResourceWarning` suppression that accompanied them is replaced by a positive no-leak
  test mirroring the ActivityWatch-side one, so a re-introduced leak fails the run instead
  of being ignored. A stale docstring passes every run; only reading catches this class.
- **`harvest_list`'s missing-metadata test covered one of four shapes.** Its `parametrize`
  carried a single case, and it asserted on a count of `?` across the whole line, which
  cannot tell a missing project code from a missing task name. The project and task
  fallbacks are independent, so each is now exercised alone and asserted per column.

### Changed
- `TESTING.md` records the `SKILL_ROOT` location-dependency bug found during the 0.4.0
  release — a test whose result depended on which checkout it ran from, which the suite
  structurally could not catch and the release mirror did.
- The timeline rollup's first-match-wins attribution for ambiguous spans is now pinned by
  a named test in both class orderings, and recorded as considered-and-kept. An event
  matching two clients credits all of its minutes to whichever rule ActivityWatch ordered
  first; `!MULTI` on the span is the compensating control.

## [0.4.0] - 2026-08-14

### Added
- **A test harness for the scripts.** `tests/support.py` builds a whole day from local
  `HH:MM` strings and serves it from a real HTTP server, so a fixture reads as the day it
  describes rather than as a list of UTC events. `tests/scenarios.py` holds seven such
  days — locked screen, blip-and-tail, interleaved clients, no break, overnight, idle, and
  a UTC+13 daylight-saving day — each pinned by both a golden file and named assertions.
  Goldens catch *change*; named assertions state *intent*; a golden on its own will
  happily bake in a bug. `--regen-golden` rewrites them, `--bench` runs the benchmarks
  (skipped by default). The skill's suite went from 92 tests to 261.
- `tests/README.md` — how to write a day, and why `.locked()` and `.thin()` exist.
- `references/self-development.md` ships for the first time; it was previously live-only.

### Fixed
Seventeen script defects, each reproduced red before being fixed. `TESTING.md`
§ "Script defects" carries the full record with an evidence rung per entry. The ones that
produced a *silently wrong answer* rather than a crash:

- **A dead window watcher read as an empty day.** `activity_timeline.py` printed a
  timeline with no rows and exited 0 — indistinguishable from a day with no activity. It
  now fails when the window bucket is missing.
- **Overlapping `--cover` blocks reported over 100% coverage.** The blocks were summed
  without being unioned first, so the Step 6 floor check passed on overlapping input.
- **Zoom dropped the browser tab that was open when the zoom started** — the row most
  likely to name the client, filtered out for having started before the window.
- **`--json` did not always emit JSON.** A no-activity day printed prose to stdout.
- **`harvest_patch` last-won on a repeated flag** and sent the request anyway. It now
  refuses.
- **The live lookup fallback was not scoped to the caller**, so an admin-scope token
  paginated the whole company's entries and could surface a project the user has no
  assignment to — which then fails, or mis-bills, at post time.
- **`refresh_catalogs.py` deleted the old catalog before writing the new one**, so a
  failed write left no catalog at all and every later lookup fell through to the live API
  without saying so. Pages are now staged and swapped into place.
- **Workspace auto-detection could never work on a stock install.** It walked up two
  levels from the skill root — one short of Claude Code's
  `<workspace>/.claude/skills/<name>` layout — while `.env.example` promised it would.

### Changed
- **The suite is now hermetic.** One test shelled out with `subprocess`, which inherits no
  fixtures: it read the real `.env` and paged 180 days of live Harvest history. That was
  roughly 90% of the old suite's runtime, and a red build whenever Harvest was slow. An
  autouse fixture now points both API clients at an unroutable address and blanks every
  credential source, so a test that reaches for the network fails fast instead of touching
  a real timesheet.
- `TESTING.md` — adds the script-defect record, the code-review round, and two open gaps.

## [0.3.0] - 2026-08-12

### Fixed
- **Step 6 guard 1 could force idle time onto a client invoice.** On a day with
  no breaks, `afk_blocks.py` returns a single span covering the whole day. Guard 1
  required interior sub-blocks to "tile the span exactly", which left a stretch
  excluded under Step 3's `<0.4` band with nowhere to go — while the span-level
  ratio passed `>=0.7` by averaging the dead time away. Guard 1 now states that
  tiling governs adjacent *billed* sub-blocks, and defers to guard 3: an excluded
  stretch is declared under the table, not tiled over.

  Measured both directions on a fixture whose correct answer is 6.5 hr. Control
  (guard 1 as written), 4 reps: **8.21 / 8.21 / 6.52 / 6.52** — half of them
  over-billing by 1.7 hr, with two reps reasoning from the same span ratio to
  opposite conclusions. Treatment, 4 reps: **6.51 / 6.51 / 6.51 / 6.51**.
  Every treatment rep still declared the excluded time and put a question to the
  user, so the fix does not trade over-billing for under-billing.

### Changed
- `TESTING.md` — records the run above, and **amends the 0.2.9 entry**, whose
  "6/6" result overstated its evidence: that fixture pre-supplied the ratios that
  flag the anomaly. On a fixture without them, 0 of 4 reps reached
  `references/activitywatch.md`. The pointer stays out because this release removes
  the billing consequence, but the routing claim is reopened rather than settled.

## [0.2.9] - 2026-08-12

### Changed
- `TESTING.md` — records the first measured two-arm fresh-agent test in this
  skill, and the change it **rejected**. The worry was that `SKILL.md` routes
  `references/activitywatch.md` only as a raw-API reference, while its
  lock-screen fragmentation note matters during ordinary Step 3 blocking with
  ActivityWatch up. Six reps across a control arm and a treatment arm carrying
  an extra Step 3 pointer produced identical output, and all six named
  `references/activitywatch.md` unprompted with the correct expectation of its
  contents, working from the reference index alone. The pointer was not added.
  Two new open gaps are recorded from the same run, both with the fixture flaw
  that prevents them being settled yet written into their entries.

## [0.2.8] - 2026-08-12

### Added
- `classification-rules.md` — **Interleaved days step 7: some days have no
  switch point to find.** Two workspaces with an agent session in each, focus
  alternating every 1–3 minutes for hours, is genuinely parallel work: the
  existing procedure hunts a boundary that does not exist and burns screenshots
  doing it. Step 7 says to stop hunting, ask as step 4 already requires, and —
  only when the user hands the split back — allocate proportionally from a
  per-window tally, placing each boundary where that client's corroborating
  evidence clusters. The resulting boundary must be presented as an allocation
  rather than an observed switch.

### Changed
- `activitywatch.md` — the lock-screen note now covers the consequence that
  bites: a lock fragments the AFK record into chunks that each fall under the
  break threshold, so `afk_blocks.py` reports `breaks: (none)` for a day that
  plainly had them. Such stretches surface as sub-0.4 `active_ratio` windows
  with a matching gap in the captures, and are excluded under the `<0.4` band
  rather than by inventing a break the script never reported.
- `classification-rules.md` — "Focused window ≠ active attention" gained the
  mirror-image case on the AFK side: a low `active_ratio` while an agent runs
  is supervision, not absence, and supervised agent time is billable. Check the
  other monitors for the agent's output before shrinking a thin block or
  dropping a stretch on ratio alone.

## [0.2.7] - 2026-08-11

### Fixed
- `setup_screenshot_pipeline.ps1` baked the resolved absolute interpreter path
  into the scheduled task. A Python upgrade, reinstall, or move between
  per-machine and per-user install left the task pointing at a path that no
  longer exists, and every trigger from that moment failed `0x80070002` —
  silently, with the task still reporting `Ready`. Observed in the wild: a
  full afternoon of captures lost with no error surfaced. Setup now prefers
  the version-independent launcher (`pyw.exe`).
- The same script's dependency check ran through a bare `python.exe`, which on
  Windows is usually the Store app-execution stub. The Pillow/mss imports then
  failed on every run, so setup reinstalled both packages each time and exited
  non-zero. It now resolves through the launcher (`py.exe`).

### Added
- `TESTING.md` — the improvement record for this skill: test method, why rules
  are worded as they are, and options already tried and rejected. Read before
  editing `SKILL.md`; ignored on a normal run. Keeps settled decisions and
  negative results out of the operating instructions.
- `references/setup.md` gained a **Health check — captures stopped** section:
  a dead capture task fails silently, so it documents the
  `LastTaskResult` probe and reads `0x80070002` as "interpreter path moved".

### Changed
- `SKILL.md` Step 3 now compares the last screenshot's timestamp against
  `work_end` while indexing. A short capture folder looks identical whether the
  user stopped working or the grabber died; `work_end` separates them. Blocks
  after a capture failure are flagged as having no screenshot fallback, so they
  reach the user rather than being resolved on thinner evidence than the
  operator realises.
- `SKILL.md` no longer treats `python` in its own commands as a literal. It
  names the Windows Store-stub signature (help text plus exit code 49) as a
  missing interpreter rather than a broken script, and sends the machine's
  answer to `.context.md`.
- `SKILL.md`'s `--cover` guard said "billed entries", which read as excluding
  non-billable ones and invited passing an *excluded* stretch to the check —
  the one input that makes the guard report clean while under-billing goes
  unnoticed. Both copies (Step 6 guard, Step 8 checklist) now say "every entry
  Step 9 will post, non-billable included".
- `SKILL.md` Step 8 gained a skeleton-freshness check for days billed while
  still in progress, or sessions that cross midnight: `work_end` advances and
  late spans appear, moving both the last block's end and the coverage
  denominator.

### Upgrading
- **Re-run `pwsh -File scripts/setup_screenshot_pipeline.ps1`** after updating.
  The `WorkScreenshots` task stores its command line at registration and is not
  re-registered by a skill update, so an existing install keeps the old,
  breakable interpreter path until setup runs again.
- Check an existing install first with
  `Get-ScheduledTaskInfo -TaskName WorkScreenshots`: a `LastTaskResult` of
  `0x80070002` means captures are already silently dead.

## [0.2.6] - 2026-08-07

### Fixed
- `SKILL.md`'s Step 8 confirmation example showed a trailing-`S` ticket
  (`BET2020S`) without the `[Support]` tag its own documented rule requires —
  the example now matches the rule.
- `SKILL.md`'s screenshot-delegation guidance pointed to a procedure
  "above" that wasn't in that file; now cites
  `classification-rules.md`'s "Interleaved days" section directly.
- `references/activitywatch.md` and `references/setup.md` described bucket
  selection as picking by `last_updated` alone, omitting that a suffixed
  bucket is always preferred over an unsuffixed one regardless of recency —
  both now state the full two-part rule.
- `scripts/aw_client.py`'s `pick_bucket()` docstring shortened and corrected
  to match the two-part rule above.

### Changed
- `references/classification-rules.md`: merged two adjacent paragraphs that
  ended on the same remedy, and genericized an example hostname
  (`HOST-OLD`/`HOST-NEW`) so it no longer names this user's real machine in
  a doc meant to be shareable across users.
- `SKILL.md`: removed a duplicated sentence about the AFK-settled rule.

## [0.2.5] - 2026-08-07

### Fixed
- `aw_client.py`'s `pick_bucket()` picked the alphabetically-first hostname-suffixed
  bucket, which silently kept reading a dead old-host bucket after a machine rename or
  reimage — the new host's suffix can sort after the old one. Now breaks ties by
  `last_updated` among suffixed candidates (an unsuffixed leftover still always loses),
  so a renamed/reimaged machine's buckets resolve correctly with no config change.

### Added
- `references/setup.md`: an "After a machine reimage or replacement" checklist covering
  the four things a reimage breaks at once — the screenshot scheduled task's Python path
  and packages, a stale `TIMESHEET_WORKSPACE` in `.env`, missing `pac auth` profiles, and
  the AW hostname suffix.
- `references/classification-rules.md`: a rule to verify a `*.md` window title actually
  lives in the client's repo (`git log --follow` / find) before trusting it as content —
  a Claude Code skill's own reference doc can be open in any workspace and looks like
  client documentation otherwise.

### Changed
- `references/activitywatch.md` notes that bucket discovery breaks ties by
  `last_updated`, not alphabetically, and drops the stale example hostname.
- `SKILL.md`'s frontmatter description shortened, and `disable-model-invocation: true`
  added — the skill now runs only on explicit `/daily-timesheet` invocation rather than
  the model deciding to trigger it.

## [0.2.4] - 2026-07-31

### Added
- `scripts/aw_client.py`: the ActivityWatch request, bucket-discovery, heartbeat-dedupe
  and timestamp helpers `afk_blocks.py` and `activity_timeline.py` each carried their own
  copy of. Both now import them, so a fix lands in one place instead of one script
  silently keeping the old behaviour.
- `setup_screenshot_pipeline.ps1 -DryRun`: builds and prints the scheduled task it would
  register — command line, weekday schedule, repetition, capture directory — then stops
  without installing packages or registering anything. The capture directory is still
  created, so a dry run also tells you whether `-ScreenshotsDir` is usable.

### Changed
- `activity_timeline.py` reads the bucket list once per run instead of once per watcher
  it looks for (four requests down to one).
- The screenshot-setup tests now assert against a real task definition rather than
  pattern-matching the script's source, so argument quoting is covered too.

### Upgrading
Re-copy the skill. The two ActivityWatch scripts now need `aw_client.py` beside them, so
running them from a half-updated `scripts/` folder fails on the import.

    pwsh -File install\install_skill.ps1

## [0.2.3] - 2026-07-31

### Fixed
- `setup_screenshot_pipeline.ps1 -ScreenshotsDir` created the directory you asked for and then
  registered a task that ignored it: `screenshot_capture.py` always wrote to
  `~/Pictures/WorkScreenshots`. The directory is now passed to the capture script, which takes
  it as its first argument, else `TIMESHEET_SCREENSHOTS_DIR` from `.env` (resolved through the
  same helper as every other setting), else the default.
- `references/catalog-refresh.md` and `references/new-client-work.md` wrote the Dataverse case
  helpers as `python scripts/create_incident.py`. `SKILL.md` defines that shape as relative to
  the skill folder, but those two scripts live in the user's workspace, so the documented
  command resolved to a path that doesn't exist. Both are now written as explicit
  `<workspace>/scripts/…` paths.
- Both installers copied `.pytest_cache/` into the installed skill.

### Added
- `skill/daily-timesheet/VERSION`, reported by both installers and checked against this
  changelog by the test suite, so an installed copy can be identified.
- `.gitattributes`. Windows sets `core.autocrlf=true` by default, so a fresh clone rewrote
  `install/*.sh` with CRLF endings and `bash` failed on the shebang's trailing `\r`. Shell
  scripts now check out LF everywhere.
- Unit tests for `afk_blocks.py`, covering work bounds, the end-of-day blip guard, break
  detection, active-span folding and the coverage check.

### Changed
- `afk_blocks.py`'s day arithmetic moved out of `main()` into `to_spans`, `work_bounds`,
  `find_breaks`, `active_spans`, `active_seconds` and `uncovered_segments`. Same output; the
  logic is now reachable without a running ActivityWatch.

### Upgrading
Re-copy the skill:

    pwsh -File install\install_skill.ps1

If you passed `-ScreenshotsDir` before, re-run `setup_screenshot_pipeline.ps1` with it — the
existing scheduled task still has the old argument-free command line.

## [0.2.2] - 2026-07-31

### Fixed
- `setup_screenshot_pipeline.ps1` could not run under Windows PowerShell 5.1 at all: it used the
  pwsh-7-only `?.` and `??` operators (a parse error on 5.1), and built its `-CaptureScript`
  default from `$PSScriptRoot`, which 5.1 leaves empty while binding parameters. Both defaults
  now resolve in the body, spelled out with `if`/`else`.
- `setup_workspace.ps1` failed to parse under Windows PowerShell 5.1. The file was UTF-8 without
  a BOM, so 5.1 read its em dashes as mojibake and lost a string terminator. All three `.ps1`
  files are now ASCII with a UTF-8 BOM.
- `install_skill.sh` deleted the user's `.env` when re-run on a machine without `rsync`: the
  fallback path cleared the whole destination directory first. It now copies in place and keeps
  any existing `.env`, matching what the README documents and what the PowerShell installer does.

### Changed
- The `rsync` path in `install_skill.sh` no longer passes `--delete`, so both copy paths refresh
  files in place rather than mirroring — the behaviour the README describes.
- `README.md` prerequisites now state that the `pwsh -File` commands need PowerShell 7 (not on a
  stock Windows box) and that `powershell.exe -File` works as a substitute.
- `SKILL.md` says where the `python scripts/…` commands resolve from: the skill folder, not the
  workspace the session runs in.

### Added
- `tests/` at the repo root: guards that every `.ps1` parses and runs under Windows PowerShell 5.1
  and that an installer re-run preserves the user's `.env`.

### Upgrading
Re-copy the skill; the screenshot setup script is the file that changed.

    pwsh -File install\install_skill.ps1

## [0.2.1] - 2026-07-31

### Fixed
- `harvest_lookup.py` read `TIMESHEET_WORKSPACE` from OS environment variables only, while
  `refresh_catalogs.py` read it from the skill `.env`. Setting it in `.env` — the way
  `.env.example` documents — left refreshes writing catalogs to one directory and lookups
  reading another, so a lookup reported no match against a stale or absent catalog. Both
  now resolve through one shared function.

### Changed
- `harvest_client.py` gains `config(key)` and `find_workspace()`; `refresh_catalogs.py`'s
  private copies of both are gone. `find_workspace()` returns `None` when it cannot resolve
  a workspace — a refresh stops with an error rather than write to a guessed path, and a
  lookup falls back to the live time-entries API.
- Workspace auto-detection no longer includes a `~/Claude/Work/.mcp` fallback. It now checks
  the current directory and the directory the skill is installed under, taking whichever
  already contains `.mcp/` or `Timesheets/`.

### Upgrading
Re-copy the skill:

    pwsh -File install\install_skill.ps1

If you relied on the removed `~/Claude/Work` fallback — that is, you ran the skill from
somewhere else and never set `TIMESHEET_WORKSPACE` — set it in `.env` to your workspace's
absolute path. Anything that already sets it, or that runs from the workspace itself, is
unaffected.

## [0.2.0] - 2026-07-31

### Added
- `references/setup.md`, `references/activitywatch.md` and `references/new-client-work.md`.
  `SKILL.md` now points at these instead of carrying the detail inline.
- Classification guidance for interleaved days: how to find the point where the work
  switched clients rather than billing the whole block to whichever client dominates.
- Guidance for two cases where the focused window misreports the work: autonomous agent
  sessions on multi-monitor setups, and long agent CLI sessions that pin one editor tab.
- Billing-convention and note-writing defaults, including translating internal artefact
  names into client-readable descriptions.
- Tests for `harvest_client` and for the Dataverse configuration guard.

### Removed
- `skill/daily-timesheet/docs/` — internal plan and spec documents for a past refactor. They
  were never needed to install or run the skill.

### Changed
- `SKILL.md` restructured and reduced from 400 to 249 lines.
- `harvest_lookup.py` now checks a `TIMESHEET_WORKSPACE`-relative `.mcp` directory first,
  ahead of the existing `./.mcp` and `~/Claude/Work/.mcp` fallbacks.
- `harvest_lookup.py` falls back to a live Harvest time-entries API lookup when a project
  isn't in the local catalogs (its assignment archived, for example), recovering the
  project and task ids from entry history instead. New `--no-live` flag skips this and
  stays cache-only; `--days` controls how far back the fallback looks.
- `afk_blocks.py` reports a `work_end_blip` when the computed work end is a momentary
  flicker long after the last substantive activity, so the final block isn't stretched to it.
- `refresh_catalogs.py`'s Harvest refresh now fetches all pages before removing stale
  catalog files, instead of deleting first — an API failure mid-refresh leaves the
  existing catalog intact rather than half-deleted.
- `refresh_catalogs.py` matches incidents modified in the last 120 days as well as open
  ones, so recently closed tickets still resolve.

### Upgrading
Re-copy the skill; three new files under `references/` will not arrive otherwise.

    pwsh -File install\install_skill.ps1

## [0.1.0] - 2026-07-16

First tagged release, covering everything up to `f9184f6`.
