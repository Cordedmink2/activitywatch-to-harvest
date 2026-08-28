"""Guards that the Dataverse config stays environment-driven.

Reads the source as text: importing the module resolves the workspace at import
time, which exits when no workspace is found.
"""

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SOURCE = (SCRIPTS / "refresh_catalogs.py").read_text(encoding="utf-8")

TENANT_URL = re.compile(r"https://[a-z0-9-]+\.crm\d*\.dynamics\.com", re.IGNORECASE)


def test_no_hardcoded_dataverse_org():
    for path in sorted(SCRIPTS.glob("*.py")):
        match = TENANT_URL.search(path.read_text(encoding="utf-8"))
        assert match is None, f"{path.name} hardcodes Dataverse org {match.group(0)!r}; it belongs in .env"


def test_no_config_reader_with_default():
    # The replaced _env(key, default) reader let an unset key fall back to a
    # baked-in org. setting(key) returns None instead.
    assert "_env(" not in SOURCE


def test_dataverse_settings_read_from_the_config_seam():
    assert "from skill_config import" in SOURCE
    assert 'DV_URL = setting("DATAVERSE_URL")' in SOURCE
    assert 'PAC_PROFILE = setting("PAC_AUTH_PROFILE")' in SOURCE


def test_workspace_resolution_can_fail_loudly():
    # An unresolved workspace must stop the refresh, not fall back to a guessed path.
    # `fail_missing()` is the shared error contract — an ERROR line and a non-zero exit,
    # asserted in test_config_seam.py; here we only pin that this guard routes through it.
    assert "WORKSPACE = find_workspace()" in SOURCE
    assert "if WORKSPACE is None:" in SOURCE
    guard = SOURCE.index("if WORKSPACE is None:")
    assert "fail_missing(" in SOURCE[guard:SOURCE.index("MCP_DIR", guard)]


def test_dataverse_refresh_skips_when_unconfigured():
    # Dataverse is optional: if DV_URL or PAC_PROFILE is unset, refresh_dataverse()
    # must return before touching `pac` at all, not pass None through to it.
    start = SOURCE.index("def refresh_dataverse():")
    end = SOURCE.index("\ndef ", start + 1)
    body = SOURCE[start:end]
    guard_pos = body.find("if not DV_URL or not PAC_PROFILE")
    pac_call_pos = body.find("shutil.which(")
    assert guard_pos != -1, "refresh_dataverse() lost its optional-config guard"
    assert guard_pos < pac_call_pos, "guard must run before any pac invocation"
    assert "return" in body[guard_pos:pac_call_pos]
