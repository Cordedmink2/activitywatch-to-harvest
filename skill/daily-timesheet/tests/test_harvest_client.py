import os, sys
import pytest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)
import harvest_client as hc
from harvest_client import parse_time_to_minutes
from harvest_list import to_24h


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point config/workspace resolution at a throwaway tree with no real settings.

    Patches every source find_workspace() consults so the result depends only on what
    each test sets up, not on the machine running it.
    """
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(hc, "ENV_PATH", env)
    monkeypatch.setattr(hc, "SKILL_ROOT", tmp_path / "skills" / "daily-timesheet")
    monkeypatch.delenv("TIMESHEET_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    return env


@pytest.mark.parametrize("raw,expected", [
    ("8:15am", 8 * 60 + 15),
    ("08:15", 8 * 60 + 15),
    ("12:30pm", 12 * 60 + 30),   # noon stays 12
    ("12:30am", 30),             # midnight wraps to 0
    ("12:00am", 0),
    ("1:05pm", 13 * 60 + 5),
    ("11:59pm", 23 * 60 + 59),
    (" 9:00 AM ", 9 * 60),       # whitespace + uppercase suffix
    ("00:00", 0),
    ("23:59", 23 * 60 + 59),
])
def test_parse_valid(raw, expected):
    assert parse_time_to_minutes(raw) == expected


@pytest.mark.parametrize("raw", [
    "",            # empty
    "9am",         # no minutes
    "9.15am",      # wrong separator
    "24:00",       # hour out of range
    "10:60",       # minute out of range
    "13:00pm",     # 13pm is nonsense (would map to 25)
    "abc",
    "10:xx",
])
def test_parse_invalid_raises(raw):
    with pytest.raises(ValueError):
        parse_time_to_minutes(raw)


def test_to_24h_delegates_and_keeps_contract():
    assert to_24h("8:15am") == "08:15"
    assert to_24h("12:21pm") == "12:21"
    assert to_24h("08:15") == "08:15"
    assert to_24h(None) == "--:--"      # missing input
    assert to_24h("") == "--:--"
    assert to_24h("garbage") == "garbage"  # unparseable returns original


def test_config_reads_the_env_file(isolated):
    isolated.write_text("DATAVERSE_URL=https://example.invalid/\n", encoding="utf-8")
    assert hc.config("DATAVERSE_URL") == "https://example.invalid/"


def test_config_returns_none_when_unset(isolated):
    assert hc.config("DATAVERSE_URL") is None


def test_config_falls_back_to_os_env(isolated, monkeypatch):
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert hc.config("TIMESHEET_WORKSPACE") == "/from-os"


def test_env_file_beats_os_env(isolated, monkeypatch):
    isolated.write_text("TIMESHEET_WORKSPACE=/from-file\n", encoding="utf-8")
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert hc.config("TIMESHEET_WORKSPACE") == "/from-file"


def test_find_workspace_honours_env_file(isolated, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    isolated.write_text(f"TIMESHEET_WORKSPACE={ws}\n", encoding="utf-8")
    assert hc.find_workspace() == ws


def test_find_workspace_uses_cwd_when_it_looks_like_a_workspace(isolated, tmp_path):
    (tmp_path / ".mcp").mkdir()
    assert hc.find_workspace() == tmp_path


def test_find_workspace_returns_none_rather_than_guessing(isolated):
    # No override, and nothing nearby looks like a workspace. Callers must be told
    # so they can fail loudly instead of writing catalogs to an invented path.
    assert hc.find_workspace() is None
