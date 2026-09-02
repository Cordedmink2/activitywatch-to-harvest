"""Edge cases in the catalog write path (`refresh_catalogs`) and the read path
(`harvest_lookup`).

The two tests at the top guard promises the source makes in comments and nothing
else checks: a refresh fetches every page before it deletes anything, and it clears
page files a shorter run left behind. Both failures are silent — the user sees a
successful-looking lookup against a catalog that is half gone or half stale.
"""
from __future__ import annotations

import json
import time
import os
from pathlib import Path

import pytest

import harvest_lookup as hl
import refresh_catalogs as rc
import skill_config
from support import assignments_page, paged_assignments, project, run_cli, write_catalog


def _snapshot(directory: Path):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def _write(directory: Path, name: str, text: str):
    """A file that is not a catalog page — an unrelated neighbour, or a truncated one."""
    (directory / name).write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------------------
# refresh_harvest(): the two invariants the comments promise
# --------------------------------------------------------------------------------------

def test_a_failure_on_page_two_leaves_every_existing_catalog_file_byte_for_byte_intact(workspace, live_harvest):
    """A refresh that dies halfway must not have started deleting.

    If it deletes first and fetches second, a Harvest outage mid-refresh leaves the user
    with a catalog missing whole pages — every project on them then looks archived, and
    the next lookup silently bills through the time-entries fallback or not at all. A
    stale catalog is recoverable; a half-deleted one is not.
    """
    mcp = workspace / ".mcp"
    write_catalog(mcp, {
        "harvest_assignments.json": assignments_page(1, 2, [project(1, "OLD-1", "Kept page one")]),
        "harvest_assignments_p2.json": assignments_page(2, 2, [project(2, "OLD-2", "Kept page two")]),
    })
    _write(mcp, "dv_active_incidents.txt", "unrelated catalog\n")
    before = _snapshot(mcp)

    live_harvest(paged_assignments([assignments_page(1, 2, [project(9, "NEW-9")]),
                         assignments_page(2, 2, [project(10, "NEW-10")])], fail_on=2))
    r = run_cli(rc, ["--harvest-only"])

    assert r.code != 0
    assert "existing catalog left untouched" in (r.err + r.out)
    # Contents *and* the filename set: a half-written page would slip past a
    # contents-only check on the seeded files.
    assert _snapshot(mcp) == before


def test_a_refresh_returning_fewer_pages_deletes_the_leftover_page_files(workspace, live_harvest):
    """Consumers glob `harvest_assignments*.json`, so a page file the shorter run did not
    overwrite is read as current data. The user sees projects that no longer exist, or
    task ids that have since moved, presented exactly like live ones.
    """
    mcp = workspace / ".mcp"
    write_catalog(mcp, {
        "harvest_assignments.json": assignments_page(1, 3, [project(1, "OLD-1")]),
        "harvest_assignments_p2.json": assignments_page(2, 3, [project(2, "OLD-2")]),
        "harvest_assignments_p3.json": assignments_page(3, 3, [project(3, "OLD-3")]),
    })

    live_harvest(paged_assignments([assignments_page(1, 1, [project(9, "NEW-9")])]))
    r = run_cli(rc, ["--harvest-only"])

    assert r.code == 0
    assert sorted(p.name for p in mcp.iterdir()) == ["harvest_assignments.json"]
    kept = json.loads((mcp / "harvest_assignments.json").read_text(encoding="utf-8"))
    assert [pa["project"]["code"] for pa in kept["project_assignments"]] == ["NEW-9"]
    assert [pa["project"]["code"] for pa in hl.iter_assignments(str(mcp))] == ["NEW-9"]


def test_page_one_is_unsuffixed_and_later_pages_each_hold_their_own_payload(workspace, live_harvest):
    """The reader globs for `harvest_assignments*.json` and the docs name the files
    explicitly. Renaming or duplicating a page here means a lookup either misses every
    project after the first hundred, or reports page one's tasks for all of them.
    """
    mcp = workspace / ".mcp"
    pages = [assignments_page(1, 3, [project(1, "P1-A"), project(2, "P1-B")]),
             assignments_page(2, 3, [project(3, "P2-A")]),
             assignments_page(3, 3, [project(4, "P3-A")])]

    live_harvest(paged_assignments(pages))
    r = run_cli(rc, ["--harvest-only"])

    assert r.code == 0
    names = ["harvest_assignments.json", "harvest_assignments_p2.json",
             "harvest_assignments_p3.json"]
    assert sorted(p.name for p in mcp.iterdir()) == sorted(names)
    for name, expected in zip(names, pages):
        assert json.loads((mcp / name).read_text(encoding="utf-8")) == expected


def test_the_dataverse_refresh_reports_a_skip_when_the_org_is_not_configured(workspace):
    """Dataverse is optional. If the unconfigured guard stops working, `refresh_dataverse`
    reaches the `pac` CLI with a None environment — a user who never opted in gets an
    error, and their active `pac` auth profile gets switched out from under them.
    """
    r = run_cli(rc, ["--dataverse-only"])
    assert r.code == 0
    assert "Skipping Dataverse refresh" in r.out


# --------------------------------------------------------------------------------------
# wait_for_project(): the pre-billing poll for an eventually-consistent row
# --------------------------------------------------------------------------------------

def test_wait_for_project_returns_the_assignment_from_whichever_page_holds_the_code(workspace, live_harvest, monkeypatch):
    """This is what a user runs before billing a freshly-created project. If it only
    looked at page one, anyone with more than a hundred assignments would be told their
    new project does not exist yet and would wait out the whole poll for nothing.
    """
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    live_harvest(paged_assignments([assignments_page(1, 2, [project(1, "OTHER-1")]),
                         assignments_page(2, 2, [project(2, "ACM-CR900", "Brand new case")])]))

    pa = rc.wait_for_project("ACM-CR900", attempts=3, delay=15)

    assert pa is not None, "the project on page 2 was never found"
    assert pa["project"]["id"] == 2
    assert pa["project"]["name"] == "Brand new case"
    assert slept == []          # found on the first attempt, so it never waits


def test_wait_for_project_returns_none_once_its_attempts_are_exhausted(workspace, live_harvest, monkeypatch):
    """A code that never appears has to come back as None so the caller can say "not
    visible yet". Looping forever, or raising, strands the user mid-timesheet.
    """
    slept = []
    monkeypatch.setattr(time, "sleep", slept.append)
    live_harvest(paged_assignments([assignments_page(1, 1, [project(1, "OTHER-1")])]))

    assert rc.wait_for_project("NEVER-1", attempts=3, delay=15) is None
    assert slept == [15, 15]    # waits between attempts, not after the last one


# --------------------------------------------------------------------------------------
# harvest_lookup.iter_assignments(): reading a catalog someone else wrote
# --------------------------------------------------------------------------------------

def test_a_page_of_unparseable_json_is_skipped_instead_of_aborting_the_whole_lookup(tmp_path):
    """A refresh killed mid-write leaves one truncated page. Every *other* page is still
    good, so the lookup should degrade to "that project is missing" rather than failing
    outright and sending the user off to debug the tool.
    """
    _write(tmp_path, "harvest_assignments.json", '{"project_assignments": [{"proj')
    write_catalog(tmp_path, {"harvest_assignments_p2.json":
                            assignments_page(2, 2, [project(2, "GOOD-2", "Survivor")])})

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["code"] for pa in rows] == ["GOOD-2"]


def test_a_page_stored_as_a_bare_json_list_is_read_like_a_wrapped_one(tmp_path):
    """Hand-maintained and hand-trimmed catalogs get saved as a plain list of
    assignments. Ignoring that shape reports "no project matching" for a catalog the
    user can see the project sitting in.
    """
    write_catalog(tmp_path, {"harvest_assignments.json":
                            [project(1, "BARE-1", "Written as a list")]})

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["code"] for pa in rows] == ["BARE-1"]


def test_a_page_keyed_on_assignments_is_read_like_one_keyed_on_project_assignments(tmp_path):
    """Both spellings exist in the wild. Accepting only Harvest's own key makes a
    perfectly valid catalog look empty.
    """
    write_catalog(tmp_path, {"harvest_assignments.json":
                            {"assignments": [project(1, "ALT-1", "Short key")]}})

    rows = list(hl.iter_assignments(str(tmp_path)))

    assert [pa["project"]["code"] for pa in rows] == ["ALT-1"]


def test_a_project_appearing_on_several_pages_is_yielded_once_from_the_first_page(tmp_path):
    """Paging is not a snapshot: a project can be captured twice while the pages are
    being fetched. Yielding both makes the same project appear twice in a lookup, and
    the model picks whichever copy it read last — possibly the one with no tasks.
    """
    write_catalog(tmp_path, {
        "harvest_assignments.json": assignments_page(1, 2, [
            project(48084036, "ACM-CR202", "Full row, with tasks",
                     [{"billable": True, "task": {"id": 7, "name": "Gen - Development"}}])]),
        "harvest_assignments_p2.json": assignments_page(2, 2, [
            project(48084036, "ACM-CR202", "Duplicate row, no tasks"),
            project(37122824, "NWC-001", "Admin")]),
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
    write_catalog(tmp_path, {"harvest_assignments.json": assignments_page(1, 1, [
        # "ACON-1" sorts before "CON" alphabetically, so this only passes if the
        # exact-match key is doing the work.
        project(1, "ACON-1", "Alpha consulting"),
        project(2, "CON-2", "Consulting, part two"),
        project(3, "CON", "Consulting"),
        project(4, "ZZZ-9", "Nothing to do with the query"),
    ])})

    matches = hl.lookup("CON", str(tmp_path))

    assert [m["code"] for m in matches] == ["CON", "ACON-1", "CON-2"]


def test_the_task_filter_is_a_case_insensitive_substring_of_the_task_name(tmp_path):
    """`--task development` is how the model narrows a project with a dozen task rows.
    Case- or prefix-sensitivity here shows an empty task list for a project that plainly
    has the task, and the entry gets posted against the wrong task id.
    """
    write_catalog(tmp_path, {"harvest_assignments.json": assignments_page(1, 1, [
        project(1, "CON-1", "Consulting", [
            {"billable": True, "task": {"id": 10, "name": "Gen - Development/Configuration"}},
            {"billable": False, "task": {"id": 11, "name": "Meeting - Standup Meetings"}}])])})

    matches = hl.lookup("CON-1", str(tmp_path), task_filter="development")

    assert [t["id"] for t in matches[0]["tasks"]] == [10]


def test_billable_comes_from_the_task_assignments_own_flag_not_from_the_task_name(tmp_path):
    """The "(NB)" naming convention is a human hint, not the source of truth — the
    assignment carries the real flag. Reading the name instead misreports billability,
    and billability is the field an invoice is built from.
    """
    write_catalog(tmp_path, {"harvest_assignments.json": assignments_page(1, 1, [
        project(1, "CON-1", "Consulting", [
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
    write_catalog(tmp_path, {"harvest_assignments.json": assignments_page(1, 1, [
        {"project": {"id": 1, "code": "BARE-1", "name": "No tasks yet"}}])})

    matches = hl.lookup("BARE-1", str(tmp_path))

    assert len(matches) == 1
    assert matches[0]["project_id"] == 1
    assert matches[0]["tasks"] == []


# --------------------------------------------------------------------------------------
# harvest_lookup.find_catalog_dir(): where to read when nothing is configured
# --------------------------------------------------------------------------------------

def test_find_catalog_dir_falls_back_to_a_dot_mcp_under_the_current_directory(tmp_path, monkeypatch):
    """With no workspace configured, a missing catalog is not fatal for the reader: it
    names the directory it looked in and recovers via the live time-entries API. Raising
    or returning None instead turns "no catalog here" into a traceback.
    """
    # SKILL_ROOT must be repointed too, not just the cwd. find_workspace() also walks the
    # directories the skill is installed under, so this test's result depended on where the
    # checkout happened to sit: it passed from `~/.claude/skills/`, and failed from the
    # public repo at `~/Admin/activitywatch-to-harvest/skill/`, because `~/Admin` is a real
    # workspace and the walk resolved to it. Caught by the release mirror, not by this suite.
    # TESTING.md § "A test's result depended on where the checkout sat" has the entry.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", tmp_path / "skills" / "daily")
    assert skill_config.find_workspace() is None, "the fallback branch is only reachable unresolved"

    got = hl.find_catalog_dir(None)

    assert os.path.basename(got) == ".mcp"
    assert os.path.samefile(os.path.dirname(got), str(tmp_path))
