"""The one seam every script reads its configuration through.

Settings used to arrive from three places with no stated rule about which won: the skill
`.env`, the process environment, and a per-command flag. Each script merged whichever
subset it cared about in its own way — `load_creds()` re-implemented the `.env`/OS-env
walk that `config()` already did, `screenshot_capture` layered `argv[0]` on top by hand,
`harvest_lookup` layered `--mcp-dir` on top a different way. Three readers, three chances
for the rule to drift.

`skill_config` is now the reader, and its module docstring carries the precedence rule;
`references/self-development.md` § "Rules with more than one copy" registers where that
rule is restated. These tests hold the shape: the precedence itself, the error contract a
missing required value has to honour, and the structural guards that stop a second reader
growing back somewhere else in `scripts/`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import harvest_client as hc            # noqa: E402
import skill_config                    # noqa: E402
from support import SETTING_KEYS       # noqa: E402


@pytest.fixture
def isolated(env_file, tmp_path, monkeypatch):
    """`env_file`, plus the other two sources `find_workspace()` consults.

    A test whose precondition is "nothing resolves" has to neutralise every source the
    resolver reads: the walk up from `SKILL_ROOT` found a real workspace when the suite
    ran from one checkout and not from another — `TESTING.md` § "A test's result depended on where the checkout sat". Returns the `.env` path for a
    test to write settings into.
    """
    monkeypatch.setattr(skill_config, "SKILL_ROOT", tmp_path / "skills" / "daily")
    monkeypatch.chdir(tmp_path)
    return env_file


# --------------------------------------------------------------------------------------
# The precedence, in the order the docstring states it
# --------------------------------------------------------------------------------------

def test_a_flag_beats_the_env_file(isolated, monkeypatch):
    """A flag overrides a single run, which is the whole reason the scripts offer them."""
    isolated.write_text("TIMESHEET_WORKSPACE=/from-file\n", encoding="utf-8")
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert skill_config.setting("TIMESHEET_WORKSPACE", flag="/from-flag") == "/from-flag"


def test_the_env_file_beats_the_process_environment(isolated, monkeypatch):
    isolated.write_text("TIMESHEET_WORKSPACE=/from-file\n", encoding="utf-8")
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert skill_config.setting("TIMESHEET_WORKSPACE") == "/from-file"


def test_the_process_environment_beats_the_default(isolated, monkeypatch):
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert skill_config.setting("TIMESHEET_WORKSPACE", default="/fallback") == "/from-os"


def test_the_default_is_the_last_resort(isolated):
    assert skill_config.setting("TIMESHEET_WORKSPACE", default="/fallback") == "/fallback"


def test_an_unset_setting_with_no_default_is_none(isolated):
    """Callers decide whether that is fatal — the seam never invents a value."""
    assert skill_config.setting("DATAVERSE_URL") is None


# --------------------------------------------------------------------------------------
# Blank means unset, at every layer
# --------------------------------------------------------------------------------------

def test_a_blank_flag_does_not_win(isolated):
    """Task Scheduler passes an empty string through when its argument is blank, and a
    blank that wins is worse than no flag at all: it silently discards the configured
    value in favour of nothing."""
    isolated.write_text("TIMESHEET_SCREENSHOTS_DIR=D:\\FromDotEnv\n", encoding="utf-8")
    assert skill_config.setting("TIMESHEET_SCREENSHOTS_DIR", flag="  ") == r"D:\FromDotEnv"


def test_a_blank_env_file_value_does_not_win(isolated, monkeypatch):
    """`DATAVERSE_URL=` left in a copied `.env.example` is a user saying "not this",
    not a user configuring an empty org."""
    isolated.write_text("DATAVERSE_URL=   \n", encoding="utf-8")
    monkeypatch.setenv("DATAVERSE_URL", "https://example.invalid/")
    assert skill_config.setting("DATAVERSE_URL") == "https://example.invalid/"


# --------------------------------------------------------------------------------------
# find_workspace(): the one derived setting, resolved the same way for reader and writer
# --------------------------------------------------------------------------------------

def test_find_workspace_honours_the_env_file(isolated, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    isolated.write_text(f"TIMESHEET_WORKSPACE={ws}\n", encoding="utf-8")
    assert skill_config.find_workspace() == ws


def test_find_workspace_uses_cwd_when_it_looks_like_a_workspace(isolated, tmp_path):
    (tmp_path / ".mcp").mkdir()
    assert skill_config.find_workspace() == tmp_path


def test_find_workspace_returns_none_rather_than_guessing(isolated):
    # No override, and nothing nearby looks like a workspace. Callers must be told
    # so they can fail loudly instead of writing catalogs to an invented path.
    assert skill_config.find_workspace() is None


def test_find_workspace_uses_the_directory_the_skill_is_installed_under(isolated, tmp_path,
                                                                       monkeypatch):
    """`<workspace>/skills/<name>` — the shape a workspace-local install has."""
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", ws / "skills" / "daily")
    assert skill_config.find_workspace() == ws


def test_find_workspace_does_not_climb_past_the_skills_directory(isolated, tmp_path,
                                                                monkeypatch):
    """Anchored on the install shape, so an unrelated ancestor is not a candidate at all.

    Reasoning and the record: `TESTING.md` § "Workspace resolution is anchored on the
    install shape, not on a depth".
    """
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", ws / "checkout" / "skills" / "daily")
    assert skill_config.find_workspace() is None


def test_a_plugin_install_never_resolves_to_a_workspace_around_it(isolated, tmp_path,
                                                                 monkeypatch):
    """`<plugin>/skills/<name>` matches the workspace-local shape exactly, and must not
    resolve: the plugin holds no user data, so nothing around it is this user's workspace.
    `.claude-plugin/` beside the skills directory is what says so.

    Pinned rather than left to a green suite because the wrong answer is silent and
    delayed — the refresh reports success and the staleness surfaces days later.
    Reasoning: `TESTING.md` § "Workspace resolution is anchored on the install shape, not
    on a depth".
    """
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    plugin = ws / "activity-to-timesheet"
    (plugin / ".claude-plugin").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", plugin / "skills" / "daily")
    assert skill_config.find_workspace() is None


# --------------------------------------------------------------------------------------
# The error contract for a required value that isn't there
# --------------------------------------------------------------------------------------

def test_a_missing_required_value_is_an_error_line_and_a_non_zero_exit():
    """The scripts are read by a model. A traceback reads as "the tool is broken" and
    sends it debugging the script instead of filling in the setting."""
    with pytest.raises(SystemExit) as exc:
        skill_config.fail_missing("Harvest credentials not found.")
    assert str(exc.value).startswith("ERROR: ")
    assert exc.value.code != 0


def test_missing_credentials_still_name_the_file_to_create(isolated):
    """The message a first-run user actually sees, unchanged by the move."""
    hc._CREDS_CACHE = None
    with pytest.raises(SystemExit) as exc:
        hc.load_creds()
    message = str(exc.value)
    assert message.startswith("ERROR: Harvest credentials not found.")
    assert ".env.example" in message
    assert "HARVEST_ACCOUNT_ID" in message and "HARVEST_API_KEY" in message


# --------------------------------------------------------------------------------------
# Structural: no second reader grows back
# --------------------------------------------------------------------------------------

# A read of the process environment. `os.environ["PYTHONIOENCODING"] = "utf-8"` is a
# write — several scripts set it before reconfiguring their streams — so the subscript
# form only counts when it is not the target of an assignment.
ENV_READ = re.compile(r"os\.environ\.get\(|os\.getenv\(|os\.environ\[(?![^\]]*\]\s*=)")


def scripts():
    return sorted(p for p in SCRIPTS.glob("*.py") if p.name != "skill_config.py")


def test_only_the_seam_reads_the_process_environment():
    offenders = [f"{p.name}:{n}" for p in scripts()
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if ENV_READ.search(line)]
    assert not offenders, (
        "these read the environment directly instead of through skill_config.setting(), "
        "which is how the .env layer got skipped before:\n  " + "\n  ".join(offenders))


def test_only_the_seam_parses_the_env_file():
    definers = [p.name for p in SCRIPTS.glob("*.py")
                if "def _parse_env_file" in p.read_text(encoding="utf-8")]
    assert definers == ["skill_config.py"]


def test_every_script_naming_a_setting_resolves_it_through_the_seam():
    offenders = [p.name for p in scripts()
                 if any(k in (t := p.read_text(encoding="utf-8")) for k in SETTING_KEYS)
                 and "skill_config" not in t]
    assert not offenders, (
        "these name a setting without going through skill_config:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("name", ["config", "find_workspace", "ENV_PATH", "_parse_env_file"])
def test_the_api_client_no_longer_doubles_as_the_config_reader(name):
    """`harvest_client` held the settings reader by accident of history. Leaving an alias
    behind would put the seam back to two names — and two things to patch, which is how a
    hermetic fixture ends up guarding the wrong one and a test suite reads the real `.env`.
    """
    assert not hasattr(hc, name)


def test_the_precedence_is_stated_where_it_is_implemented():
    """One statement of the rule, next to the only code that applies it."""
    doc = skill_config.__doc__ or ""
    assert "Precedence" in doc
    for source in ("flag", ".env", "environment", "default"):
        assert source in doc, f"the precedence docstring never mentions the {source} layer"
