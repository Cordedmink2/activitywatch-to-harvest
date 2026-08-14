"""Contracts every command-line script in this skill has to honour.

The scripts are run by a model reading their stdout, so their failure modes are part of
their interface. Three promises, made in the module docstrings and the SKILL.md guards:

* bad input produces `ERR …` on stderr and a non-zero exit — never a Python traceback,
  which reads to the model as "the script is broken" and sends it debugging the tool
  instead of fixing the argument;
* `--json` means JSON, so the output can be parsed without sniffing it first;
* the scripts import cleanly under a captured stdout, or they cannot be tested at all.

Each test here was written against the failing behaviour first.
"""
from __future__ import annotations

import datetime as dt
import gc
import importlib
import io
import sys
import warnings

import pytest

import activity_timeline as tl
import afk_blocks as ab
import aw_client
import harvest_client
import harvest_patch as hp
import harvest_post as hpost
from support import day, run_cli


def resource_warnings_from(fn) -> list:
    """Run `fn`, force a collection, and return any ResourceWarning it left behind.

    The warning we are hunting is emitted from a destructor during garbage collection,
    so it has no stack relationship to the code that leaked — which is why it surfaces
    as an unraisable exception blamed on whichever test happened to be running when the
    collector fired. Forcing the collection here pins it to its real cause.
    """
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn()
        gc.collect()
    return [w for w in caught if issubclass(w.category, ResourceWarning)]


# --------------------------------------------------------------------------------------
# Bad input is an ERR line, not a traceback
# --------------------------------------------------------------------------------------

def test_timeline_rejects_a_reversed_window(live_aw):
    """`afk_blocks` refuses `17:00-09:00`; `activity_timeline` used to accept it and print
    an empty timeline, which reads as "nothing happened then" rather than "you typed the
    range backwards". Two scripts taking the same flag must fail the same way."""
    d = day().active("09:00", "17:00")
    live_aw(d)
    r = run_cli(tl, [d.date_str(), "--window", "17:00-09:00"])
    assert r.code == 2
    assert "ERR bad --window" in r.err


def test_timeline_rejects_an_empty_window(live_aw):
    d = day().active("09:00", "17:00")
    live_aw(d)
    r = run_cli(tl, [d.date_str(), "--window", "11:00-11:00"])
    assert r.code == 2
    assert "ERR bad --window" in r.err


def test_post_rejects_a_non_numeric_project_id():
    """`int(project_id)` on a fat-fingered argument raised a bare ValueError. The
    documented contract is `ERR …` + exit 1, and this path runs *before* any HTTP, so a
    traceback here is pure noise between the model and its own typo."""
    r = run_cli(hpost, ["NLS-CR202", "20753151", "2026-08-12", "09:00", "10:00", "notes"])
    assert r.code == 1
    assert r.err.startswith("ERR")
    assert "project" in r.err.lower()


def test_post_rejects_a_non_numeric_task_id():
    r = run_cli(hpost, ["48084036", "Gen - Development", "2026-08-12", "09:00", "10:00", "n"])
    assert r.code == 1
    assert r.err.startswith("ERR")


def test_patch_rejects_a_non_numeric_hours_value():
    """`--hours abc` went through `float()` unguarded during argument parsing."""
    r = run_cli(hp, ["2988748904", "--hours", "abc"])
    assert r.code == 1
    assert r.err.startswith("ERR")


def test_patch_rejects_a_non_numeric_project_id():
    r = run_cli(hp, ["2988748904", "--project-id", "NLS-CR202"])
    assert r.code == 1
    assert r.err.startswith("ERR")


# --------------------------------------------------------------------------------------
# A failed request must not leak the response it read
# --------------------------------------------------------------------------------------

def test_a_harvest_error_response_is_closed_after_its_body_is_read(live_harvest):
    """`urllib`'s HTTPError *is* the response object: it owns a spooled temp file that
    stays open until the collector runs its destructor. Reading `e.read()` and dropping
    the exception leaks that handle on every failed API call — and a backfill that hits a
    string of 422s leaks one apiece, in a process that also holds the user's credentials.
    """
    live_harvest({("GET", "/users/me"): (500, {"error": "boom"})})

    def attempt():
        with pytest.raises(RuntimeError):
            harvest_client.request("GET", "/users/me")

    assert resource_warnings_from(attempt) == []


def test_an_activitywatch_error_response_is_closed_too(live_aw):
    """Same leak, other client. `load_classes()` swallows the exception from a missing
    settings endpoint by design, so nothing downstream ever sees the response object —
    which makes this the copy most likely to go unnoticed."""
    d = day().active("09:00", "17:00")
    live_aw(d, settings_status=404)

    def attempt():
        with pytest.raises(Exception):
            aw_client.get("/settings")

    assert resource_warnings_from(attempt) == []


# --------------------------------------------------------------------------------------
# --json means JSON
# --------------------------------------------------------------------------------------

def test_json_mode_always_emits_json_even_with_no_activity(live_aw):
    """A day where nobody touched the machine printed the sentence "No not-afk activity
    found." under `--json` and exited 0. Anything piping the output into a parser gets a
    decode error on the one day it most needs a clean empty answer."""
    d = day().afk("00:00", "24:00")
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--json"])
    assert r.code == 0
    payload = r.json()
    assert payload["work_start"] is None
    assert payload["work_end"] is None
    assert payload["active_spans"] == []
    assert payload["breaks"] == []


def test_text_mode_still_says_so_in_words(live_aw):
    """The human-readable path must keep its sentence — the model reads text by default."""
    d = day().afk("00:00", "24:00")
    live_aw(d)
    r = run_cli(ab, [d.date_str()])
    assert r.code == 0
    assert "No not-afk activity found" in r.out


# --------------------------------------------------------------------------------------
# Importable under captured stdout
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["harvest_post", "harvest_patch", "harvest_list",
                                  "activity_timeline", "harvest_lookup"])
def test_scripts_import_under_a_stdout_that_cannot_be_reconfigured(name, monkeypatch):
    """These scripts call `sys.stdout.reconfigure(...)` at import time. Under pytest's
    capture — and under any harness that swaps in a plain file-like object — that
    attribute does not exist, so importing the module raises and the script becomes
    untestable. `activity_timeline` and `harvest_lookup` already guard it; the three
    Harvest CLIs did not, which is why they had no tests at all."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    importlib.reload(importlib.import_module(name))


# --------------------------------------------------------------------------------------
# The guards that already worked — pinned so a refactor can't drop them
# --------------------------------------------------------------------------------------

def test_post_refuses_a_reversed_time_range():
    """Harvest silently stores 10:00-09:00 as a 23-hour entry. The script is the only
    thing standing between a typo and a 23-hour line on a client invoice."""
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "10:00", "09:00", "n"])
    assert r.code == 1
    assert "must be before" in r.err


def test_post_refuses_a_zero_length_entry():
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "09:00", "09:00", "n"])
    assert r.code == 1


def test_patch_refuses_a_reversed_time_range():
    r = run_cli(hp, ["2988748904", "--start", "10:00", "--end", "09:00"])
    assert r.code == 1
    assert "must be before" in r.err


def test_afk_blocks_rejects_a_malformed_date():
    r = run_cli(ab, ["12-08-2026"])
    assert r.code == 2
    assert "expected YYYY-MM-DD" in r.err


def test_timeline_rejects_a_malformed_date():
    r = run_cli(tl, ["12-08-2026"])
    assert r.code == 2
    assert "expected YYYY-MM-DD" in r.err


def test_afk_blocks_reports_an_unreachable_activitywatch_as_exit_one():
    """Nothing is listening on the hermetic base URL, which is exactly the "AW is down"
    case SKILL.md tells the model to fall back from. It must be distinguishable from a
    bad argument (exit 2) so the fallback is chosen for the right reason."""
    r = run_cli(ab, [dt.date(2026, 8, 12).isoformat()])
    assert r.code == 1
    assert "ActivityWatch unreachable" in r.err


def test_timeline_reports_an_unreachable_activitywatch_as_exit_one():
    r = run_cli(tl, [dt.date(2026, 8, 12).isoformat()])
    assert r.code == 1
    assert "ActivityWatch unreachable" in r.err
