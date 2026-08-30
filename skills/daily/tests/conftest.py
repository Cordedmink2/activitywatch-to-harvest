"""Shared fixtures — and, first, the guard that makes this suite safe to run.

## Why the hermeticity fixture exists

This skill's scripts talk to two live systems that are *running on the machine the
tests run on*:

* **ActivityWatch** on `http://localhost:5600`. A test that forgets to stub it reads
  the user's real event stream: it passes today, fails next Tuesday, and asserts
  nothing about the code.
* **Harvest**, with real credentials sitting in `.env` at the skill root. A test that
  reaches `harvest_client.request()` unstubbed can **create a real time entry on a
  client-facing timesheet**. That is the one genuinely dangerous failure mode here.

So `_hermetic` is autouse: it repoints both base URLs at a port nothing listens on and
blanks the credential sources. An unstubbed call then fails immediately and visibly
instead of touching production. Tests that *want* a server ask for `live_aw` /
`live_harvest`, which point the same constants at a local fake.

**Corollary: never shell out to a script with `subprocess`.** A subprocess inherits none
of this and reads the real `.env`. Use `support.run_cli`, which runs `main()` in-process.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
SKILL = TESTS.parent
SCRIPTS = SKILL / "scripts"
for p in (str(SCRIPTS), str(TESTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import aw_client                     # noqa: E402
import harvest_client                # noqa: E402
import skill_config                  # noqa: E402
from support import (SETTING_KEYS, Day, aw_server, day,  # noqa: E402,F401
                     harvest_server, run_cli, with_heartbeats)

# Port 0 is not a port. A connection to it cannot be routed anywhere, by anything, which
# is a stronger guarantee than "a port nothing happens to be listening on right now" —
# and it fails in ~30ms where a closed loopback port costs 2s of SYN retries on Windows.
DEAD = "http://127.0.0.1:0"

# UTC+12, fixed. See `_hermetic` below for why the suite configures one at all.
TEST_ZONE = "Etc/GMT-12"


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """No test reaches a real ActivityWatch, a real Harvest, or the real `.env`.

    One `setattr` blanks the credential file because `skill_config` is the only module
    that opens it — a property `test_config_seam.py` asserts rather than assumes, since
    a second reader appearing elsewhere in `scripts/` would leave this guard covering
    half of what it claims to.
    """
    monkeypatch.setattr(aw_client, "AW_BASE", f"{DEAD}/api/0")
    monkeypatch.setattr(harvest_client, "API_BASE", f"{DEAD}/v2")
    monkeypatch.setattr(skill_config, "ENV_PATH", tmp_path / "no-such-.env")
    monkeypatch.setattr(harvest_client, "_CREDS_CACHE", None)
    # Left set, a developer's own shell would leak into assertions about defaults.
    for key in SETTING_KEYS:
        monkeypatch.delenv(key, raising=False)
    # ...and then one is put back, because there is no longer a built-in offset to fall
    # back on: a script with no `--utc-offset` and no configured zone refuses to date a
    # day at all, which is the point of that change. `Etc/GMT-12` is UTC+12 with no
    # daylight saving (the sign in the name is inverted, per POSIX), so it matches
    # `support.DEFAULT_OFFSET` on every date and the golden files stay stable. A test
    # about the unconfigured state deletes it again.
    monkeypatch.setenv("TIMESHEET_TIMEZONE", TEST_ZONE)
    yield


@pytest.fixture
def live_aw(monkeypatch):
    """Start a fake ActivityWatch serving a `Day` and point the scripts at it.

        srv = live_aw(day().active("09:00", "17:00"))

    Extra keyword arguments go through to `support.aw_server` (`settings_status`,
    `last_updated`, ...). Returns the `FakeServer` so a test can inspect `.requests`.

    A day built with `zone=` also configures that zone, because pointing the scripts at a
    day means pointing them at *when* it happened as much as at where its events are. A
    zone day exists to exercise the real resolution, so handing it back a `--utc-offset`
    would leave the thing under test unrun.
    """
    started = []

    def _start(d: Day, **kw):
        srv = aw_server(d.buckets(), d.settings(), **kw)
        srv.__enter__()
        started.append(srv)
        monkeypatch.setattr(aw_client, "AW_BASE", f"{srv.base}/api/0")
        if d.zone_name:
            monkeypatch.setenv("TIMESHEET_TIMEZONE", d.zone_name)
        return srv

    yield _start
    for srv in started:
        srv.__exit__(None, None, None)


@pytest.fixture
def live_harvest(monkeypatch):
    """Start a fake Harvest API, point the scripts at it, and supply dummy credentials.

        srv = live_harvest({("POST", "/time_entries"): (201, {"id": 99})})

    Credentials are injected into the cache rather than written to a `.env`, so the
    real credential file stays unread even by the code path that would read it.
    """
    started = []

    def _start(routes=None, handler=None):
        srv = harvest_server(routes, handler)
        srv.__enter__()
        started.append(srv)
        monkeypatch.setattr(harvest_client, "API_BASE", f"{srv.base}/v2")
        monkeypatch.setattr(harvest_client, "_CREDS_CACHE", ("test-account", "test-key"))
        return srv

    yield _start
    for srv in started:
        srv.__exit__(None, None, None)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """A writable stand-in for the skill `.env`, with the seam pointed at it.

    Returns the path, so a test writes the settings it wants:

        env_file.write_text("TIMESHEET_SCREENSHOTS_DIR=D:\\\\Shots\\n", encoding="utf-8")

    The autouse hermetic fixture has already cleared `SETTING_KEYS` out of the process
    environment, so a result depends only on what the test puts in this file.
    """
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(skill_config, "ENV_PATH", env)
    return env


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A throwaway workspace tree (`.mcp/` + `Timesheets/`) that `find_workspace()` resolves to."""
    ws = tmp_path / "workspace"
    (ws / ".mcp").mkdir(parents=True)
    (ws / "Timesheets").mkdir()
    env = tmp_path / "workspace.env"
    env.write_text(f"TIMESHEET_WORKSPACE={ws}\n", encoding="utf-8")
    monkeypatch.setattr(skill_config, "ENV_PATH", env)
    return ws


def pytest_addoption(parser):
    parser.addoption("--regen-golden", action="store_true", default=False,
                     help="Rewrite tests/golden/*.json from the current script output. "
                          "Review the diff by hand: it is the record of what changed.")
    parser.addoption("--bench", action="store_true", default=False,
                     help="Run the benchmark tests (skipped by default).")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--bench"):
        return
    skip = pytest.mark.skip(reason="benchmarks: pass --bench to run")
    for item in items:
        if "bench" in item.keywords:
            item.add_marker(skip)
