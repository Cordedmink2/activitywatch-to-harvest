# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
