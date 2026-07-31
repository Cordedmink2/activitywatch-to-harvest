# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
