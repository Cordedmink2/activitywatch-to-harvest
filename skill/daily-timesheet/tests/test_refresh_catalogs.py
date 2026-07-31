"""Guards that the Dataverse config stays environment-driven.

Reads the source as text: importing the module runs _resolve_workspace() at
import time, which exits when no workspace is found.
"""

import re
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "scripts" / "refresh_catalogs.py").read_text(
    encoding="utf-8"
)

TENANT_URL = re.compile(r"https://[a-z0-9-]+\.crm\d*\.dynamics\.com", re.IGNORECASE)


def test_no_hardcoded_dataverse_org():
    match = TENANT_URL.search(SOURCE)
    assert match is None, f"hardcoded Dataverse org {match.group(0)!r}; it belongs in .env"


def test_no_config_reader_with_default():
    # The replaced _env(key, default) reader let an unset key fall back to a
    # baked-in org. _config(key) returns None instead.
    assert "_env(" not in SOURCE


def test_dataverse_settings_read_from_config():
    assert 'DV_URL = _config("DATAVERSE_URL")' in SOURCE
    assert 'PAC_PROFILE = _config("PAC_AUTH_PROFILE")' in SOURCE


def test_workspace_resolution_can_fail_loudly():
    assert "def _resolve_workspace()" in SOURCE
    assert "sys.exit(" in SOURCE


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
