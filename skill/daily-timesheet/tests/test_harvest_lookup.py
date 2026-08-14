import json, os, sys
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import harvest_client as hc
import harvest_lookup as hl
from support import run_cli


def _write_catalog(mcp_dir):
    # Page 1 holds NLS-CR202; a later page holds a different project + a dupe of NLS-CR202.
    page1 = {"project_assignments": [
        {"project": {"id": 48084036, "code": "NLS-CR202",
                     "name": "CMS Backlog Requirements Implementation Phase 2"},
         "task_assignments": [
             {"billable": True,  "task": {"id": 20753151, "name": "Gen - Development/Configuration"}},
             {"billable": False, "task": {"id": 20878969, "name": "Gen - Development/Configuration (NB)"}}]}]}
    page7 = {"project_assignments": [
        {"project": {"id": 37122824, "code": "ACL-001", "name": "Admin"},
         "task_assignments": [
             {"billable": False, "task": {"id": 20759111, "name": "Meeting - Standup Meetings"}}]},
        {"project": {"id": 48084036, "code": "NLS-CR202", "name": "CMS Backlog Phase 2"},
         "task_assignments": []}]}  # duplicate project id, must be de-duped
    with open(os.path.join(mcp_dir, "harvest_assignments.json"), "w", encoding="utf-8") as f:
        json.dump(page1, f)
    with open(os.path.join(mcp_dir, "harvest_assignments_p7.json"), "w", encoding="utf-8") as f:
        json.dump(page7, f)


def test_finds_project_on_first_page_across_pages(tmp_path):
    _write_catalog(str(tmp_path))
    rows = list(hl.iter_assignments(str(tmp_path)))
    ids = [r["project"]["id"] for r in rows]
    assert ids.count(48084036) == 1          # de-duped across pages
    assert 37122824 in ids


def test_lookup_returns_billable_task(tmp_path):
    _write_catalog(str(tmp_path))
    matches = hl.lookup("NLS-CR202", str(tmp_path))
    assert len(matches) == 1
    m = matches[0]
    assert m["project_id"] == 48084036
    dev = [t for t in m["tasks"] if t["id"] == 20753151][0]
    assert dev["billable"] is True


def _write_client_named_catalog(mcp_dir):
    """One client, two projects: a dead presales shell named for the *client*, and the
    live delivery project named for the *work*. Searching the client's name has to find
    the second one — its name shares no substring with the query."""
    page = {"project_assignments": [
        {"project": {"id": 1001, "code": "PSO-1000", "name": "Contoso - D365 CRM Foundation"},
         "client": {"name": "Contoso Pty Ltd"},
         "task_assignments": [
             {"billable": False, "task": {"id": 2001, "name": "Presales - Meetings"}}]},
        {"project": {"id": 1002, "code": "CTO2000",
                     "name": "Check app access still enabled after the security group migration"},
         "client": {"name": "Contoso Pty Ltd"},
         "task_assignments": [
             {"billable": True, "task": {"id": 2002, "name": "Gen - Investigation"}}]}]}
    with open(os.path.join(mcp_dir, "harvest_assignments.json"), "w", encoding="utf-8") as f:
        json.dump(page, f)


def test_lookup_matches_on_client_name(tmp_path):
    """A project findable only by its client used to be invisible: lookup read
    project.code and project.name but never client.name, so searching a client's name
    returned only the projects *named* after them — typically a stale presales shell —
    while the live delivery project, named for the work, was missed entirely. Match on
    client too, and rank code/name hits above client-only hits."""
    _write_client_named_catalog(str(tmp_path))
    matches = hl.lookup("Contoso", str(tmp_path))
    by_code = {m["code"]: m for m in matches}
    assert by_code["CTO2000"]["matched_on"] == "client"
    assert by_code["CTO2000"]["tasks"][0]["billable"] is True
    assert matches[0]["code"] == "PSO-1000"          # name match outranks client-only
    assert by_code["PSO-1000"]["matched_on"] == "code/name"


def test_lookup_tolerates_a_catalog_without_client_names(tmp_path):
    _write_catalog(str(tmp_path))
    assert hl.lookup("NLS-CR202", str(tmp_path))[0]["client"] == ""


def test_cli_exit_nonzero_on_no_match(tmp_path):
    """`--no-live` is what makes this a test rather than a live query.

    It used to shell out with `subprocess`, which inherits none of conftest's guards: the
    script read the real `.env`, and with no catalog match it fell through to the live
    time-entries API and paged 180 days of the user's real Harvest history. That was
    ~90% of the whole suite's runtime, and it meant a red build could be caused by
    Harvest being down. In-process, cache-only, and offline.
    """
    _write_catalog(str(tmp_path))
    r = run_cli(hl, ["NOPE", "--mcp-dir", str(tmp_path), "--no-live"])
    assert r.code != 0
    assert "no project matching" in r.err


def test_cli_falls_back_to_time_entries_when_the_catalog_misses(tmp_path, live_harvest):
    """An archived assignment drops out of the catalog while its entries remain. The
    fallback is the only way to recover the project id, so it gets a real exercise
    against a fake API rather than being left to the live one."""
    _write_catalog(str(tmp_path))
    live_harvest({
        ("GET", "/users/me"): (200, {"id": 4242}),
        ("GET", "/time_entries"): (200, {"time_entries": [{
            "project": {"id": 111, "code": "ARCH-9", "name": "Archived project"},
            "task": {"id": 222, "name": "Gen - Development/Configuration"},
            "billable": True,
        }], "next_page": None}),
    })
    r = run_cli(hl, ["ARCH-9", "--mcp-dir", str(tmp_path), "--json"])
    assert r.code == 0
    assert r.json()[0]["project_id"] == 111
    assert "recovered from own time entries" in r.err


def test_catalog_dir_honours_workspace_from_env_file(tmp_path, monkeypatch):
    """The reader must read TIMESHEET_WORKSPACE the way the writer does.

    It used to check os.environ only, so setting the workspace the documented way — in
    the skill `.env` — sent refreshes to one directory and lookups to another, and the
    lookup silently reported no match against a stale or empty catalog.
    """
    ws = tmp_path / "ws"
    (ws / ".mcp").mkdir(parents=True)
    env = tmp_path / ".env"
    env.write_text(f"TIMESHEET_WORKSPACE={ws}\n", encoding="utf-8")
    monkeypatch.setattr(hc, "ENV_PATH", env)
    monkeypatch.delenv("TIMESHEET_WORKSPACE", raising=False)

    assert hl.find_catalog_dir(None) == str(ws / ".mcp")


def test_explicit_mcp_dir_wins_over_configured_workspace(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(f"TIMESHEET_WORKSPACE={tmp_path / 'ws'}\n", encoding="utf-8")
    monkeypatch.setattr(hc, "ENV_PATH", env)
    assert hl.find_catalog_dir("/explicit") == "/explicit"


def test_reader_shares_the_writers_resolver():
    # Guards against a private copy of the resolution logic reappearing here: the two
    # copies drifting apart is what caused the bug above.
    assert hl.find_workspace is hc.find_workspace
