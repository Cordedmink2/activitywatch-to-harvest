# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
  (`CON2020S`) without the `[Support]` tag its own documented rule requires —
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
