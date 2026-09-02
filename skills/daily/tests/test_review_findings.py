"""Regressions for the findings of the 2026-08-14 code review.

Each test here failed before its fix. They are kept together rather than filed into the
per-module edge files because what they share is provenance: a reviewer reading the code
found each one, and grouping them makes the review auditable — you can re-run exactly the
set that was reported.

The unifying shape of the serious ones is **a plausible-looking wrong answer**: an empty
timeline that means "the watcher died" but reads as "no work happened", a coverage
summary over 100%, a PATCH that silently drops half its input. None of them raise.
"""
from __future__ import annotations

import datetime as dt
import importlib
import io
import json
import sys

import pytest

import activity_timeline as tl
import afk_blocks as ab
import aw_client
import harvest_client
import harvest_lookup as hl
import refresh_catalogs as rc
import skill_config
from support import aw_server, day, run_cli


# --------------------------------------------------------------------------------------
# 1. A dead window watcher must not read as an empty day
# --------------------------------------------------------------------------------------

def test_timeline_errors_when_the_window_bucket_is_missing(monkeypatch):
    """`fetch_events(None, …)` returns `[]` by design, so a crashed or renamed window
    watcher produced a well-formed, completely empty timeline and exit 0.

    A model reading that concludes the user did no work, and writes a timesheet to match.
    `afk_blocks` already hard-errors on a missing AFK bucket; this is the same failure
    with none of the noise.
    """
    d = day().active("09:00", "17:00")
    with aw_server({"aw-watcher-afk_TESTHOST": d.afk_events()}, d.settings()) as srv:
        monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", srv.base)
        r = run_cli(tl, [d.date_str()])
    assert r.code == 1
    assert "window" in r.err.lower()
    assert "bucket" in r.err.lower()


# --------------------------------------------------------------------------------------
# 2. Every script must import under a captured stdout
# --------------------------------------------------------------------------------------

def test_the_encoding_fix_survives_a_stdout_that_cannot_be_reconfigured(monkeypatch):
    """A captured or redirected stream — a test harness, a wrapper, `pythonw.exe` — is not
    a `TextIOWrapper` and has no `reconfigure`. A bare call died there with an
    AttributeError naming neither the script nor the cause.

    This used to import `refresh_catalogs` under a swapped stream, because the call sat at
    that module's import scope. It does not any more; `use_utf8()` is called from `main()`
    and is the only copy, so the guard is asserted on the function itself. Doing it that
    way also stops this test from being the thing that decides whether the module is in
    `sys.modules` for whatever runs next.
    """
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    harvest_client.use_utf8()          # must not raise


# --------------------------------------------------------------------------------------
# 3. The bucket preference that was tested but unreachable
# --------------------------------------------------------------------------------------

def test_buckets_are_found_on_an_activitywatch_that_does_not_suffix_them(monkeypatch):
    """`pick_bucket` prefers a hostname-suffixed bucket over an unsuffixed leftover, and a
    test covered that. But every caller passed a prefix ending in `_`, so an unsuffixed
    bucket could never become a candidate in production — the branch was unreachable and
    the preference untested where it mattered.

    Consequence on an AW instance that does not suffix: `afk_blocks` reports "no
    aw-watcher-afk bucket found" on a machine whose watchers are running fine, and
    `references/setup.md` tells the reader recovering from a reimage that this case is
    already handled.
    """
    d = day().active("09:00", "17:00")
    with aw_server({"aw-watcher-afk": d.afk_events(),
                    "aw-watcher-window": d.window_events()}, d.settings()) as srv:
        monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", srv.base)
        r = run_cli(ab, [d.date_str(), "--json"])
    assert r.code == 0
    assert r.json()["work_start"] == "09:00:00"


def test_a_suffixed_bucket_still_wins_over_an_unsuffixed_leftover(monkeypatch):
    """The other half: widening the prefix must not resurrect the stale bucket a reimage
    left behind, which is the case `pick_bucket`'s tie-break exists for."""
    d = day().active("09:00", "17:00")
    stale = day().active("03:00", "04:00")
    with aw_server({"aw-watcher-afk": stale.afk_events(),
                    "aw-watcher-afk_LIVEHOST": d.afk_events(),
                    "aw-watcher-window_LIVEHOST": d.window_events()},
                   d.settings(),
                   last_updated={"aw-watcher-afk": "2026-01-01T00:00:00+00:00",
                                 "aw-watcher-afk_LIVEHOST": "2026-05-28T00:00:00+00:00"}) as srv:
        monkeypatch.setenv("TIMESHEET_ACTIVITY_URL", srv.base)
        r = run_cli(ab, [d.date_str(), "--json"])
    assert r.json()["afk_bucket"] == "aw-watcher-afk_LIVEHOST"
    assert r.json()["work_start"] == "09:00:00"


# --------------------------------------------------------------------------------------
# 4. Coverage can't exceed the day
# --------------------------------------------------------------------------------------

def test_overlapping_cover_blocks_do_not_double_count_covered_minutes(live_aw):
    """`covered_active_min` summed each proposed block independently, so two blocks that
    overlap reported more covered activity than the day contained — 180 of 120 minutes on
    this fixture.

    That line is what the skill reads to judge whether it has under-billed. A number over
    100% is not merely wrong, it is reassuring: it says "you have covered everything"
    exactly when the proposed blocks are malformed.
    """
    d = day().afk("00:00", "09:00").active("09:00", "11:00").afk("11:00", "24:00")
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--json", "--cover", "09:00-11:00,10:00-11:30"])
    report = r.json()["coverage_report"]
    assert report["covered_active_min"] == 120.0
    assert report["covered_active_min"] <= report["total_active_min"]


def test_covered_minutes_still_add_up_for_disjoint_blocks(live_aw):
    """Guard on the fix: de-duplicating overlaps must not start dropping real coverage."""
    d = (day().afk("00:00", "09:00").active("09:00", "10:00")
         .afk("10:00", "11:00").active("11:00", "12:00").afk("12:00", "24:00"))
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--json", "--cover", "09:00-10:00,11:00-12:00"])
    assert r.json()["coverage_report"]["covered_active_min"] == 120.0


# --------------------------------------------------------------------------------------
# 5. Workspace auto-detection on a real Claude Code install
# --------------------------------------------------------------------------------------

def test_workspace_is_found_when_the_skill_is_installed_under_dot_claude(tmp_path, monkeypatch):
    """Auto-detection walked up two levels from the skill, which is right for
    `<workspace>/skills/<name>` and one level short of `<workspace>/.claude/skills/<name>`
    — the layout Claude Code actually installs into.

    So on a stock install with `TIMESHEET_WORKSPACE` unset, `refresh_catalogs.py` refused
    to run against a perfectly valid workspace, while `.env.example` promised auto-detect
    would find it.
    """
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    skill_root = ws / ".claude" / "skills" / "daily"
    skill_root.mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", skill_root)
    monkeypatch.setattr(skill_config, "ENV_PATH", skill_root / ".env")
    monkeypatch.chdir(tmp_path)          # cwd is not the workspace
    assert skill_config.find_workspace() == ws


def test_workspace_detection_still_refuses_to_guess(tmp_path, monkeypatch):
    """Widening the search must not turn "I don't know" into a confident wrong answer:
    with nothing workspace-shaped anywhere above the skill, the result stays None."""
    skill_root = tmp_path / "nowhere" / ".claude" / "skills" / "daily"
    skill_root.mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", skill_root)
    monkeypatch.setattr(skill_config, "ENV_PATH", skill_root / ".env")
    monkeypatch.chdir(tmp_path)
    assert skill_config.find_workspace() is None


# --------------------------------------------------------------------------------------
# 6-7. refresh_catalogs robustness
# --------------------------------------------------------------------------------------

def test_a_null_project_on_a_pending_assignment_does_not_crash_the_poll(workspace, live_harvest):
    """`pa.get("project", {})` returns None — not {} — when the key is present and null,
    so `.get("code")` raised. `wait_for_project` is the pre-billing poll for a
    brand-new project, which is exactly when Harvest is likeliest to serve a
    half-populated row. Every other project access in the skill uses the `or {}` idiom.
    """
    live_harvest({("GET", "/users/me/project_assignments"): (200, {
        "project_assignments": [{"project": None, "task_assignments": []},
                                {"project": {"id": 7, "code": "NEW-1"}, "task_assignments": []}],
        "next_page": None})})
    pa = rc.wait_for_project("NEW-1", attempts=1)
    assert pa is not None, "the null-project row swallowed the real one behind it"
    assert pa["project"]["code"] == "NEW-1"


def test_a_failed_first_write_does_not_destroy_the_existing_catalog(workspace, live_harvest, monkeypatch):
    """The old files were deleted before the first new one was written. If that write
    failed — disk full, a sync client holding the directory, a permissions change — the
    catalog was gone with nothing to replace it, and every later lookup fell through to
    the live time-entries API without saying so.
    """
    mcp = workspace / ".mcp"
    existing = mcp / "harvest_assignments.json"
    existing.write_text('{"project_assignments": [{"project": {"id": 1, "code": "OLD"}}]}',
                        encoding="utf-8")
    before = existing.read_text(encoding="utf-8")

    live_harvest({("GET", "/users/me/project_assignments"):
                  (200, {"project_assignments": [], "next_page": None})})

    real_open = open

    def exploding_open(path, mode="r", *a, **kw):
        if "w" in mode and "harvest_assignments" in str(path):
            raise OSError(28, "No space left on device")
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", exploding_open)
    with pytest.raises((OSError, SystemExit)):
        rc.refresh_harvest()
    monkeypatch.undo()

    assert existing.exists(), "the old catalog was deleted with nothing to replace it"
    assert existing.read_text(encoding="utf-8") == before


def test_an_unreadable_pac_profile_list_warns_instead_of_silently_switching(workspace, capsys, monkeypatch):
    """`_active_pac_index` returns None when `pac auth list` fails or changes format, and
    the restore was then skipped in silence — leaving the user's active profile switched
    to the timesheet one. That cross-tenant drift is the exact thing the restore was
    written to prevent, so it must at least say so."""
    monkeypatch.setattr(
        rc, "dataverse_settings",
        lambda: ("https://example.crm6.dynamics.com", "timesheet"))
    monkeypatch.setattr(rc.shutil, "which", lambda _: "pac")
    monkeypatch.setattr(rc, "_active_pac_index", lambda _: None)

    class Result:
        returncode = 0
        stdout = "ticketnumber\ttitle\n"
        stderr = ""

    monkeypatch.setattr(rc.subprocess, "run", lambda *a, **kw: Result())
    rc.refresh_dataverse()
    out = capsys.readouterr()
    assert "WARN" in (out.out + out.err)


# --------------------------------------------------------------------------------------
# 8. The live fallback must stay scoped to this user
# --------------------------------------------------------------------------------------

def test_the_time_entries_fallback_asks_only_for_this_users_entries(live_harvest):
    """The fallback queried `/time_entries` with no `user_id`, unlike `harvest_list.py`
    which always scopes by it. On a member PAT the results coincide; on an admin-scope
    token it paginates the whole company and can surface a project/task pair the user has
    no assignment to — which then fails, or mis-bills, at post time.
    """
    srv = live_harvest({
        ("GET", "/users/me"): (200, {"id": 4242}),
        ("GET", "/time_entries"): (200, {"time_entries": [{
            "project": {"id": 111, "code": "ARCH-9", "name": "Archived"},
            "task": {"id": 222, "name": "Gen - Development/Configuration"},
            "billable": True}], "next_page": None}),
    })
    matches = hl.lookup_from_entries("ARCH-9")
    assert matches[0]["project_id"] == 111
    queries = [r["query"] for r in srv.sent("GET", "/time_entries")]
    assert queries and all(q.get("user_id") == "4242" for q in queries), (
        f"time-entries fallback was not scoped to the caller: {queries}")
