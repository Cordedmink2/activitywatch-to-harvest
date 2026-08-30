"""Contracts every command-line script in this skill has to honour.

The scripts are run by a model reading their stdout, so their failure modes are part of
their interface. Four promises, made in the module docstrings and the SKILL.md guards:

* bad input produces `ERR …` on stderr and a non-zero exit — never a Python traceback,
  which reads to the model as "the script is broken" and sends it debugging the tool
  instead of fixing the argument;
* `--json` means JSON, so the output can be parsed without sniffing it first;
* the scripts import cleanly under a captured stdout, or they cannot be tested at all;
* a script that writes to the provider writes nothing without `--confirm`, and says what
  it would have written instead.

Each test here was written against the failing behaviour first.
"""
from __future__ import annotations

import datetime as dt
import gc
import importlib
import io
import json
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
    r = run_cli(hpost, ["ACM-CR202", "20753151", "2026-08-12", "09:00", "10:00", "notes",
                        "--confirm"])
    assert r.code == 1
    assert r.err.startswith("ERR")
    assert "project" in r.err.lower()


def test_post_rejects_a_non_numeric_task_id():
    r = run_cli(hpost, ["48084036", "Gen - Development", "2026-08-12", "09:00", "10:00", "n",
                        "--confirm"])
    assert r.code == 1
    assert r.err.startswith("ERR")


def test_patch_rejects_a_non_numeric_hours_value():
    """`--hours abc` went through `float()` unguarded during argument parsing."""
    r = run_cli(hp, ["2988748904", "--hours", "abc", "--confirm"])
    assert r.code == 1
    assert r.err.startswith("ERR")


def test_patch_rejects_a_non_numeric_project_id():
    r = run_cli(hp, ["2988748904", "--project-id", "ACM-CR202", "--confirm"])
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
# The confirmation gate is part of the invocation, not only the prose
# --------------------------------------------------------------------------------------
#
# SKILL.md's frontmatter carries `disable-model-invocation: true`, which is what stops a
# model starting a billing run unprompted — and which Claude Code honours and several other
# Agent Skills harnesses drop on the floor. Where the field is ignored, the flag below is
# the whole gate: a script reached by a model that was never told to bill still writes
# nothing. So these are tests about a promise the frontmatter cannot keep everywhere.

POST_ARGS = ["48084036", "20753151", "2026-08-12", "09:00", "10:30", "Drafted the spec"]
PATCH_ARGS = ["2988748904", "--notes", "Reworded for the client"]


def previewed_body(result, verb: str) -> dict:
    """The JSON body out of a `WOULD POST …` / `WOULD PATCH <id> …` preview line."""
    line = result.lines[0]
    assert line.startswith(verb), f"expected a {verb!r} preview, got {line!r}"
    return json.loads(line[line.index("{"):])


def test_post_writes_nothing_without_the_confirmation_flag(live_harvest):
    """The failure this gate exists for is a time entry on a client-facing timesheet that
    nobody asked for. Asserted against the recorded requests rather than the exit code,
    because a script that posted and *then* printed a preview would pass on the latter."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 4001})})
    r = run_cli(hpost, POST_ARGS)

    assert srv.sent("POST", "/time_entries") == [], "no flag, no write"
    assert r.code == 0, "a missing confirmation is the normal case, not a failure"
    assert r.err == ""


def test_a_post_preview_is_exactly_the_body_a_confirmed_run_sends(live_harvest):
    """"What it would have posted" has to mean it literally, or the preview becomes a
    second description of the entry that can drift from the first — and the reviewer is
    then approving a paraphrase. Both runs below take the same arguments, so the preview
    is compared against the body the confirmed one actually put on the wire.
    """
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 4002})})

    preview = run_cli(hpost, POST_ARGS)
    confirmed = run_cli(hpost, POST_ARGS + ["--confirm"])

    assert preview.code == 0
    assert confirmed.lines == ["OK 4002"], "the flag leaves the success contract alone"
    assert previewed_body(preview, "WOULD POST") == \
        srv.sent("POST", "/time_entries")[0]["body"]


def test_a_post_preview_cannot_be_read_as_a_posted_entry(live_harvest):
    """`OK <entry_id>` is what tells the caller an entry now exists and what its id is. A
    preview borrowing that shape would have Step 10 record an id for an entry nobody
    created; the preview says so in words instead, and names the flag that would post it.
    """
    live_harvest({("POST", "/time_entries"): (201, {"id": 4003})})
    r = run_cli(hpost, POST_ARGS)

    assert not r.out.startswith("OK ")
    assert "--confirm" in r.out


def test_patch_writes_nothing_without_the_confirmation_flag(live_harvest):
    """A patch is the more dangerous of the two: it overwrites a line that has already
    been reviewed and may already have been invoiced, and there is no undo."""
    srv = live_harvest({("PATCH", "/time_entries/2988748904"): {"id": 2988748904}})
    r = run_cli(hp, PATCH_ARGS)

    assert srv.sent("PATCH", "/time_entries") == []
    assert r.code == 0
    assert r.err == ""


def test_a_patch_preview_is_exactly_the_body_a_confirmed_run_sends(live_harvest):
    srv = live_harvest({("PATCH", "/time_entries/2988748904"): {"id": 2988748904}})

    preview = run_cli(hp, PATCH_ARGS)
    confirmed = run_cli(hp, PATCH_ARGS + ["--confirm"])

    assert preview.code == 0
    assert confirmed.lines == ["OK 2988748904"]
    assert previewed_body(preview, "WOULD PATCH") == \
        srv.sent("PATCH", "/time_entries")[0]["body"]


def test_a_patch_preview_names_the_entry_it_would_have_changed(live_harvest):
    """The body alone says what would change but not *where*. An id in the preview is what
    lets the reviewer check it against the entry they meant before handing over the flag.
    """
    live_harvest({("PATCH", "/time_entries/2988748904"): {"id": 2988748904}})
    r = run_cli(hp, PATCH_ARGS)

    assert not r.out.startswith("OK ")
    assert "2988748904" in r.lines[0]
    assert "--confirm" in r.out


def test_the_confirmation_flag_is_not_a_field_to_update(live_harvest):
    """`--confirm` says *whether* to write, never *what* to write. Counted as a field it
    would make `harvest_patch.py <id> --confirm` an empty PATCH — which Harvest answers 200
    to, so the caller is told an edit landed when none was ever described."""
    srv = live_harvest({("PATCH", "/time_entries/2988748904"): {"id": 2988748904}})
    r = run_cli(hp, ["2988748904", "--confirm"])

    assert r.code != 0
    assert "at least one field" in r.err
    assert srv.sent("PATCH", "/time_entries") == []


def test_a_command_that_could_never_post_is_an_error_rather_than_a_preview():
    """The guards run first, so an unconfirmed bad command fails on the spot. Previewing it
    as "here is what I would have done" would invite the caller to re-run it with the flag,
    and the reversed range would then be caught on the second attempt instead of the first
    — with the caller having read a preview of an entry that was never postable."""
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "10:00", "09:00", "n"])
    assert r.code == 1
    assert "must be before" in r.err
    assert r.out == ""


# --------------------------------------------------------------------------------------
# The guards that already worked — pinned so a refactor can't drop them
# --------------------------------------------------------------------------------------
#
# Each of these passes `--confirm`, so the refusal under test is the guard named in the
# test and not the confirmation gate standing in front of it.

def test_post_refuses_a_reversed_time_range():
    """Harvest silently stores 10:00-09:00 as a 23-hour entry. The script is the only
    thing standing between a typo and a 23-hour line on a client invoice."""
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "10:00", "09:00", "n",
                        "--confirm"])
    assert r.code == 1
    assert "must be before" in r.err


def test_post_refuses_a_zero_length_entry():
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "09:00", "09:00", "n",
                        "--confirm"])
    assert r.code == 1


def test_patch_refuses_a_reversed_time_range():
    r = run_cli(hp, ["2988748904", "--start", "10:00", "--end", "09:00", "--confirm"])
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


def test_a_hole_in_the_afk_record_reaches_the_cli_as_a_labelled_break(live_aw):
    """End-to-end guard for the *wiring*, not just the helper.

    The watcher writes nothing at all while the machine sleeps, so 11:00-12:00 below
    carries no event of any kind. Reverting `insert_data_gaps` out of main leaves every
    unit test green while the CLI goes back to reporting `breaks: (none)` on a day the
    user plainly spent an hour away - which is the 2026-08-18 defect exactly."""
    d = day().active("08:30", "11:00").active("12:00", "15:00")   # hole: 11:00-12:00
    live_aw(d)
    r = run_cli(ab, [d.date_str(), "--json"])
    assert r.code == 0
    payload = r.json()
    assert [(b["start"], b["end"], b["kind"]) for b in payload["breaks"]] == [
        ("11:00:00", "12:00:00", "gap")]
    assert [(s["start"], s["end"]) for s in payload["active_spans"]] == [
        ("08:30:00", "11:00:00"), ("12:00:00", "15:00:00")]


def test_web_rows_inside_the_repeated_hour_are_ordered_by_instant_not_by_clock(live_aw):
    """`Pacific/Auckland` goes back at 03:00 on 2026-04-05, so 02:00-03:00 runs twice.

    The runbook tab is opened at 02:40 on the first pass and the ticket at 02:10 on the
    second — half an hour later on the clock, thirty minutes *earlier* by the reading. A
    sort on the rendered string puts the ticket first and tells the model the day went the
    other way round; only a sort on the instant gets it right. The zoom ends at `02:30*`,
    a genuinely ambiguous reading, so the CLI's own `--window` parse is on the hook too.
    """
    d = day(dt.date(2026, 4, 5), zone="Pacific/Auckland")
    d.active("01:30", "03:30*")
    d.window("01:30", "03:30*", "msedge.exe", "ACME")
    d.web("02:40", "02:50", "ACME release runbook", "https://acme.example/runbook")
    d.web("02:10*", "02:20*", "ACME ticket 4471", "https://acme.example/tickets/4471")
    live_aw(d)

    r = run_cli(tl, [d.date_str(), "--window", "02:00-02:30*", "--json"])
    assert r.code == 0
    assert [(w["time"], w["title"]) for w in r.json()["web"]] == [
        ("02:40:00", "ACME release runbook"),
        ("02:10:00*", "ACME ticket 4471"),
    ]
