import json, os, sys, subprocess
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import harvest_client as hc
import harvest_lookup as hl


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


def test_cli_exit_nonzero_on_no_match(tmp_path):
    _write_catalog(str(tmp_path))
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "harvest_lookup.py"),
                        "NOPE", "--mcp-dir", str(tmp_path)], capture_output=True, text=True)
    assert r.returncode != 0


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
