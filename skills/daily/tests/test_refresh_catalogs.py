"""Guards that the Dataverse config stays environment-driven.

These used to read the script as *text* — `'DV_URL = setting("DATAVERSE_URL")' in SOURCE`,
and index arithmetic over the string to prove one statement came before another — because
importing the module resolved the workspace at import time and exited when there wasn't
one. The tests could not run the code, so they described it instead, and a rename broke
them with behaviour unchanged while a behaviour change slipped past untouched.

The module imports cleanly now, so they call it — the plain `import refresh_catalogs` at
the top of this file is itself the evidence that the import-time exit is gone, which is
why no test here asserts it separately. `test_config_seam.py` holds the general rule for
every bundled script. What is still asserted against the source
is only what is genuinely a property of the source: that no tenant URL is written down
anywhere in `scripts/`, which is a claim about every file rather than about this one's
behaviour.
"""

import re
from pathlib import Path

import pytest

import refresh_catalogs as rc
import skill_config

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

TENANT_URL = re.compile(r"https://[a-z0-9-]+\.crm\d*\.dynamics\.com", re.IGNORECASE)


@pytest.fixture
def unresolvable(env_file, tmp_path, monkeypatch):
    """Nothing anywhere resolves a workspace: no `.env`, no cwd, no install directory.

    All three sources `find_workspace()` consults have to be neutralised together, or the
    result depends on where the checkout happens to sit — `TESTING.md` § "A test's result
    depended on where the checkout sat" records the run where it did.
    """
    monkeypatch.setattr(skill_config, "SKILL_ROOT", tmp_path / "skills" / "daily")
    monkeypatch.chdir(tmp_path)
    return env_file


def test_no_hardcoded_dataverse_org():
    """The one thing here that is a property of the text rather than of a run: a tenant
    URL written into any script is wrong wherever it appears and whatever it does."""
    for path in sorted(SCRIPTS.glob("*.py")):
        match = TENANT_URL.search(path.read_text(encoding="utf-8"))
        assert match is None, (
            f"{path.name} hardcodes Dataverse org {match.group(0)!r}; it belongs in .env")


def test_dataverse_settings_read_from_the_config_seam(unresolvable):
    """Both values arrive through `skill_config`, so they honour its precedence.

    The `.env` layer is used rather than the process environment because it is the one
    that only exists if the seam is doing the reading — a script that had quietly gone
    back to `os.environ` would pass an env-var version of this test.
    """
    unresolvable.write_text(
        "DATAVERSE_URL=https://example.invalid/\nPAC_AUTH_PROFILE=timesheets\n",
        encoding="utf-8")
    assert rc.dataverse_settings() == ("https://example.invalid/", "timesheets")


def test_dataverse_settings_are_none_when_unset(unresolvable):
    """The replaced `_env(key, default)` reader let an unset key fall back to a baked-in
    org. Unset has to read as unset, so `refresh_dataverse()` can skip rather than send
    someone else's tenant a query."""
    assert rc.dataverse_settings() == (None, None)


def test_workspace_resolution_fails_loudly_rather_than_guessing(unresolvable):
    """An unresolved workspace stops the refresh instead of falling back to a guessed
    path, through the shared `fail_missing()` contract: one `ERROR:` line, non-zero exit,
    never a traceback. The contract itself is asserted in `test_config_seam.py`; what is
    pinned here is that this guard routes through it."""
    with pytest.raises(SystemExit) as exc:
        rc.mcp_dir()
    assert str(exc.value).startswith("ERROR:")
    assert "TIMESHEET_WORKSPACE" in str(exc.value)


def test_the_workspace_is_resolved_freshly_on_each_call(unresolvable, tmp_path):
    """`MCP_DIR` was frozen at import, so a second workspace could not be addressed
    without reimporting the module — which is why two test files carried a fixture whose
    only job was to stage that import."""
    first, second = tmp_path / "one", tmp_path / "two"
    for ws in (first, second):
        (ws / ".mcp").mkdir(parents=True)
    unresolvable.write_text(f"TIMESHEET_WORKSPACE={first}\n", encoding="utf-8")
    assert rc.mcp_dir() == first / ".mcp"
    unresolvable.write_text(f"TIMESHEET_WORKSPACE={second}\n", encoding="utf-8")
    assert rc.mcp_dir() == second / ".mcp"


def test_dataverse_refresh_skips_when_unconfigured(unresolvable, monkeypatch, capsys):
    """Dataverse is optional: unset means `refresh_dataverse()` returns before touching
    `pac` at all, rather than passing None through to it.

    The old version of this proved the ordering by comparing the index of the guard
    against the index of `shutil.which(` in the file's text. Here `pac` is simply made
    fatal to look for, so reaching it fails the test on its own.
    """
    def never(*args, **kwargs):
        pytest.fail("refresh_dataverse() went looking for pac with nothing configured")

    monkeypatch.setattr(rc.shutil, "which", never)
    rc.refresh_dataverse()
    assert "Skipping Dataverse refresh" in capsys.readouterr().out
