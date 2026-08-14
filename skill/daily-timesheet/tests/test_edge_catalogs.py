"""Edge cases in the catalog write path (`refresh_catalogs`) and the read path
(`harvest_lookup`).

The two tests at the top guard promises the source makes in comments and nothing
else checks: a refresh fetches every page before it deletes anything, and it clears
page files a shorter run left behind. Both failures are silent — the user sees a
successful-looking lookup against a catalog that is half gone or half stale.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

import pytest

import harvest_client as hc
import harvest_lookup as hl
from support import run_cli

ASSIGNMENTS = ("GET", "/users/me/project_assignments")


# --------------------------------------------------------------------------------------
# Importing refresh_catalogs
# --------------------------------------------------------------------------------------

@pytest.fixture
def refresh(workspace):
    """Import `refresh_catalogs` for one test, with a workspace already resolvable.

    IMPORT HAZARD — read this before adding a test. `refresh_catalogs` calls
    `find_workspace()` at *module scope* and `sys.exit()`s when nothing resolves, so it
    can never be imported at the top of this file the way `harvest_lookup` is: a bare
    `import refresh_catalogs` would abort collection on any machine without a workspace.
    It also freezes `WORKSPACE` / `MCP_DIR` into module globals at import time, so a
    cached copy from an earlier test points at that test's (now deleted) tmp directory.
    Hence: drop any cached copy, import inside the test with the `workspace` fixture
    active, and drop it again on teardown. Every test that touches the module must take
    this fixture — including ones that never write a file.
    """
    sys.modules.pop("refresh_catalogs", None)
    module = importlib.import_module("refresh_catalogs")
    yield module
    sys.modules.pop("refresh_catalogs", None)


# --------------------------------------------------------------------------------------
# Fake-catalog helpers
# --------------------------------------------------------------------------------------

def _project(pid, code, name="Some project", tasks=()):
    return {"project": {"id": pid, "code": code, "name": name},
            "task_assignments": list(tasks)}


def _page(number, last, rows=()):
    """One `/users/me/project_assignments` page, with Harvest's `next_page` wiring."""
    return {"project_assignments": list(rows),
            "page": number,
            "total_entries": 7,
            "next_page": None if number >= last else number + 1}


def _paged(pages, fail_on=None):
    """Serve `pages[n-1]` for `?page=n`; return a 500 for page `fail_on` instead."""
    def route(query, body):
        n = int(query.get("page", 1))
        if n == fail_on:
            return 500, {"error": "read replica unavailable"}
        return 200, pages[n - 1]
    return {ASSIGNMENTS: route}


def _snapshot(directory: Path):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def _write(directory: Path, name: str, text: str):
    (directory / name).write_text(text, encoding="utf-8")


def _write_pages(directory: Path, pages: dict):
    for name, payload in pages.items():
        _write(directory, name, json.dumps(payload))


# --------------------------------------------------------------------------------------
# refresh_harvest(): the two invariants the comments promise
# --------------------------------------------------------------------------------------

def test_a_failure_on_page_two_leaves_every_existing_catalog_file_byte_for_byte_intact(
        workspace, live_harvest, refresh):
    """A refresh that dies halfway must not have started deleting.

    If it deletes first and fetches second, a Harvest outage mid-refresh leaves the user
    with a catalog missing whole pages — every project on them then looks archived, and
    the next lookup silently bills through the time-entries fallback or not at all. A
    stale catalog is recoverable; a half-deleted one is not.
    """
    mcp = workspace / ".mcp"
    _write_pages(mcp, {
        "harvest_assignments.json": _page(1, 2, [_project(1, "OLD-1", "Kept page one")]),
        "harvest_assignments_p2.json": _page(2, 2, [_project(2, "OLD-2", "Kept page two")]),
    })
    _write(mcp, "dv_active_incidents.txt", "unrelated catalog\n")
    before = _snapshot(mcp)

    live_harvest(_paged([_page(1, 2, [_project(9, "NEW-9")]),
                         _page(2, 2, [_project(10, "NEW-10")])], fail_on=2))
    r = run_cli(refresh, ["--harvest-only"])

    assert r.code != 0
    assert "existing catalog left untouched" in (r.err + r.out)
    # Contents *and* the filename set: a half-written page would slip past a
    # contents-only check on the seeded files.
    assert _snapshot(mcp) == before


def test_a_refresh_returning_fewer_pages_deletes_the_leftover_page_files(
        workspace, live_harvest, refresh):
    """Consumers glob `harvest_assignments*.json`, so a page file the shorter run did not
    overwrite is read as current data. The user sees projects that no longer exist, or
    task ids that have since moved, presented exactly like live ones.
    """
    mcp = workspace / ".mcp"
    _write_pages(mcp, {
        "harvest_assignments.json": _page(1, 3, [_project(1, "OLD-1")]),
        "harvest_assignments_p2.json": _page(2, 3, [_project(2, "OLD-2")]),
        "harvest_assignments_p3.json": _page(3, 3, [_project(3, "OLD-3")]),
    })

    live_harvest(_paged([_page(1, 1, [_project(9, "NEW-9")])]))
    r = run_cli(refresh, ["--harvest-only"])

    assert r.code == 0
    assert sorted(p.name for p in mcp.iterdir()) == ["harvest_assignments.json"]
    kept = json.loads((mcp / "harvest_assignments.json").read_text(encoding="utf-8"))
    assert [pa["project"]["code"] for pa in kept["project_assignments"]] == ["NEW-9"]
    assert [pa["project"]["code"] for pa in hl.iter_assignments(str(mcp))] == ["NEW-9"]


def test_page_one_is_unsuffixed_and_later_pages_each_hold_their_own_payload(
        workspace, live_harvest, refresh):
    """The reader globs for `harvest_assignments*.json` and the docs name the files
    explicitly. Renaming or duplicating a page here means a lookup either misses every
    project after the first hundred, or reports page one's tasks for all of them.
    """
    mcp = workspace / ".mcp"
    pages = [_page(1, 3, [_project(1, "P1-A"), _project(2, "P1-B")]),
             _page(2, 3, [_project(3, "P2-A")]),
             _page(3, 3, [_project(4, "P3-A")])]

    live_harvest(_paged(pages))
    r = run_cli(refresh, ["--harvest-only"])

    assert r.code == 0
    names = ["harvest_assignments.json", "harvest_assignments_p2.json",
             "harvest_assignments_p3.json"]
    assert sorted(p.name for p in mcp.iterdir()) == sorted(names)
    for name, expected in zip(names, pages):
        assert json.loads((mcp / name).read_text(encoding="utf-8")) == expected


def test_the_dataverse_refresh_reports_a_skip_when_the_org_is_not_configured(
        workspace, refresh):
    """Dataverse is optional. If the unconfigured guard stops working, `refresh_dataverse`
    reaches the `pac` CLI with a None environment — a user who never opted in gets an
    error, and their active `pac` auth profile gets switched out from under them.
    """
    r = run_cli(refresh, ["--dataverse-only"])
    assert r.code == 0
    assert "Skipping Dataverse refresh" in r.out


# --------------------------------------------------------------------------------------
# wait_for_project(): the pre-billing poll for an eventually-consistent row
# --------------------------------------------------------------------------------------

def test_wait_for_project_returns_the_assignment_from_whichever_page_holds_the_code(
        workspace, live_harvest, refresh, monkeypatch):
    """This is what a user runs before billing a freshly-created project. If it only
    looked at page one, anyone with more than a hundred assignments would be told their
    new project does not exist yet and would wait out the whole poll for nothing.
    """
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    live_harvest(_paged([_page(1, 2, [_project(1, "OTHER-1")]),
                         _page(2, 2, [_project(2, "NLS-CR900", "Brand new case")])]))

    pa = refresh.wait_for_project("NLS-CR900", attempts=3, delay=15)

    assert pa["project"]["id"] == 2
    assert pa["project"]["name"] == "Brand new case"
    assert slept == []          # found on the first attempt, so it never waits


def test_wait_for_project_returns_none_once_its_attempts_are_exhausted(
        workspace, live_harvest, refresh, monkeypatch):
    """A code that never appears has to come back as None so the caller can say "not
    visible yet". Looping forever, or raising, strands the user mid-timesheet.
    """
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    live_harvest(_paged([_page(1, 1, [_project(1, "OTHER-1")])]))

    assert refresh.wait_for_project("NEVER-1", attempts=3, delay=15) is None
    assert slept == [15, 15]    # waits between attempts, not after the last one


# --------------------------------------------------------------------------------------
# harvest_lookup.iter_assignments(): reading a catalog someone else wrote
# --------------------------------------------------------------------------------------

def test_a_page_of_unparseable_json_is_skipped_instead_of_aborting_the_whole_lookup(
        tmp_path):
    """A refresh killed mid-write leaves one truncated page. Every *other* page is still
    good, so the lookup should degrade to "that project is missing" rather than failing
    outright and sending the user off to debug the tool.
    """
    _write(tmp_path, "harvest_assignments.json", '{"project_assignments": [{"proj')
    _write_pages(tmp_path, {"harvest_assignments_p2.json":
                            _page(2, 2, [_project(2, "GOOD-2", "Survivor")])})

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["code"] for pa in rows] == ["GOOD-2"]


def test_a_page_stored_as_a_bare_json_list_is_read_like_a_wrapped_one(tmp_path):
    """Hand-maintained and hand-trimmed catalogs get saved as a plain list of
    assignments. Ignoring that shape reports "no project matching" for a catalog the
    user can see the project sitting in.
    """
    _write_pages(tmp_path, {"harvest_assignments.json":
                            [_project(1, "BARE-1", "Written as a list")]})

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["code"] for pa in rows] == ["BARE-1"]


def test_a_page_keyed_on_assignments_is_read_like_one_keyed_on_project_assignments(
        tmp_path):
    """Both spellings exist in the wild. Accepting only Harvest's own key makes a
    perfectly valid catalog look empty.
    """
    _write_pages(tmp_path, {"harvest_assignments.json":
                            {"assignments": [_project(1, "ALT-1", "Short key")]}})

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["code"] for pa in rows] == ["ALT-1"]


def test_a_project_appearing_on_several_pages_is_yielded_once_from_the_first_page(
        tmp_path):
    """Paging is not a snapshot: a project can be captured twice while the pages are
    being fetched. Yielding both makes the same project appear twice in a lookup, and
    the model picks whichever copy it read last — possibly the one with no tasks.
    """
    _write_pages(tmp_path, {
        "harvest_assignments.json": _page(1, 2, [
            _project(48084036, "NLS-CR202", "Full row, with tasks",
                     [{"billable": True, "task": {"id": 7, "name": "Gen - Development"}}])]),
        "harvest_assignments_p2.json": _page(2, 2, [
            _project(48084036, "NLS-CR202", "Duplicate row, no tasks"),
            _project(37122824, "ACL-001", "Admin")]),
    })

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["id"] for pa in rows] == [48084036, 37122824]
    dupe = rows[0]
    assert dupe["project"]["name"] == "Full row, with tasks"
    assert dupe["task_assignments"] != []


# --------------------------------------------------------------------------------------
# harvest_lookup.lookup(): choosing between the matches
# --------------------------------------------------------------------------------------

def test_an_exact_code_match_sorts_ahead_of_the_substring_matches(tmp_path):
    """The model bills against the first row printed. With plain alphabetical order a
    code that merely *contains* the query can outrank the code the user typed verbatim,
    which puts the hours on the wrong project.
    """
    _write_pages(tmp_path, {"harvest_assignments.json": _page(1, 1, [
        # "ACON-1" sorts before "CON" alphabetically, so this only passes if the
        # exact-match key is doing the work.
        _project(1, "ACON-1", "Alpha consulting"),
        _project(2, "CON-2", "Consulting, part two"),
        _project(3, "CON", "Consulting"),
        _project(4, "ZZZ-9", "Nothing to do with the query"),
    ])})

    matches = hl.lookup("CON", str(tmp_path))

    assert [m["code"] for m in matches] == ["CON", "ACON-1", "CON-2"]


def test_the_task_filter_is_a_case_insensitive_substring_of_the_task_name(tmp_path):
    """`--task development` is how the model narrows a project with a dozen task rows.
    Case- or prefix-sensitivity here shows an empty task list for a project that plainly
    has the task, and the entry gets posted against the wrong task id.
    """
    _write_pages(tmp_path, {"harvest_assignments.json": _page(1, 1, [
        _project(1, "CON-1", "Consulting", [
            {"billable": True, "task": {"id": 10, "name": "Gen - Development/Configuration"}},
            {"billable": False, "task": {"id": 11, "name": "Meeting - Standup Meetings"}}])])})

    matches = hl.lookup("CON-1", str(tmp_path), task_filter="development")

    assert [t["id"] for t in matches[0]["tasks"]] == [10]


def test_billable_comes_from_the_task_assignments_own_flag_not_from_the_task_name(
        tmp_path):
    """The "(NB)" naming convention is a human hint, not the source of truth — the
    assignment carries the real flag. Reading the name instead misreports billability,
    and billability is the field an invoice is built from.
    """
    _write_pages(tmp_path, {"harvest_assignments.json": _page(1, 1, [
        _project(1, "CON-1", "Consulting", [
            # Name says non-billable, flag says billable — and the reverse.
            {"billable": True, "task": {"id": 10, "name": "Gen - Development (NB)"}},
            {"billable": False, "task": {"id": 11, "name": "Billable Development"}}])])})

    tasks = {t["id"]: t["billable"] for t in hl.lookup("CON-1", str(tmp_path))[0]["tasks"]}

    assert tasks == {10: True, 11: False}


def test_a_project_with_no_task_assignments_returns_an_empty_task_list(tmp_path):
    """A project can legitimately carry no assigned tasks (a duplicate paging row, or an
    assignment being set up). The lookup has to still report the project and its id — a
    crash here takes out every other match in the same run.
    """
    _write_pages(tmp_path, {"harvest_assignments.json": _page(1, 1, [
        {"project": {"id": 1, "code": "BARE-1", "name": "No tasks yet"}}])})

    matches = hl.lookup("BARE-1", str(tmp_path))

    assert len(matches) == 1
    assert matches[0]["project_id"] == 1
    assert matches[0]["tasks"] == []


# --------------------------------------------------------------------------------------
# harvest_lookup.find_catalog_dir(): where to read when nothing is configured
# --------------------------------------------------------------------------------------

def test_find_catalog_dir_falls_back_to_a_dot_mcp_under_the_current_directory(
        tmp_path, monkeypatch):
    """With no workspace configured, a missing catalog is not fatal for the reader: it
    names the directory it looked in and recovers via the live time-entries API. Raising
    or returning None instead turns "no catalog here" into a traceback.
    """
    # SKILL_ROOT must be repointed too, not just the cwd. find_workspace() also walks the
    # directories the skill is installed under, so this test's result depended on where the
    # checkout happened to sit: it passed from `~/.claude/skills/`, and failed from the
    # public repo at `~/Admin/activitywatch-to-harvest/skill/`, because `~/Admin` is a real
    # workspace and the walk resolved to it. Caught by the release mirror, not by this suite.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hc, "SKILL_ROOT", tmp_path / "skills" / "daily-timesheet")
    assert hc.find_workspace() is None, "the fallback branch is only reachable unresolved"

    got = hl.find_catalog_dir(None)

    assert os.path.basename(got) == ".mcp"
    assert os.path.samefile(os.path.dirname(got), str(tmp_path))
