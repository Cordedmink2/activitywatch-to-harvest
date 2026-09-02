"""Writing to the provider, driven at the module rather than through a script's CLI.

`test_cli_contracts.py` holds the confirmation gate as the two write scripts expose it,
end to end. These hold the implementation both scripts now share — the gate, the preview
and the `OK` / `ERR` contract — at the function, so a change to it is measured once, where
it lives, and not twice through two scripts that happen to call it.

Every write here is declared the way the scripts declare one (`create(...)` /
`update(...)`) and handed to `perform()`; what went on the wire is read off the fake
server, not off what was printed.
"""
from __future__ import annotations

import json

import pytest

import harvest_write as hw
from support import run_cli

BODY = {"project_id": 48084036, "task_id": 20753151, "spent_date": "2026-08-12",
        "started_time": "09:00", "ended_time": "10:30", "notes": "Drafted the spec"}
ENTRY_ID = "2988748904"


class _Main:
    """Wrap a `perform()` call as a `main()` so `run_cli` can capture its streams and
    exit code the way it does for a script. The module itself has no `main()` — it is
    not a script."""

    __file__ = "harvest_write-under-test"

    def __init__(self, fn):
        self.fn = fn

    def main(self):
        return self.fn()


def performed(write: hw.Write, confirmed: bool):
    return run_cli(_Main(lambda: hw.perform(write, confirmed)), [])


# --------------------------------------------------------------------------------------
# The gate is taken off the argument list before anything else reads it
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    ["a", "b", "--confirm"],
    ["--confirm", "a", "b"],
    ["a", "--confirm", "b"],
], ids=["trailing", "leading", "between"])
def test_the_gate_is_found_wherever_it_was_typed(argv):
    """The two scripts once disagreed on this — one read the entry id off `argv[1]` before
    looking, so a leading flag became `Unknown flag: <id>`. One grammar now."""
    assert hw.take_gate(argv) == (["a", "b"], True)


def test_an_absent_gate_leaves_the_arguments_alone_and_reports_unconfirmed():
    """Nothing is stripped that was not the flag, so a positional is never lost to it."""
    assert hw.take_gate(["a", "b"]) == (["a", "b"], False)


def test_the_gate_is_removed_before_a_dangling_field_flag_could_take_it_as_a_value():
    """`--notes --confirm`: the flag is gone from the list a parser reads, so what the
    parser sees is `--notes` with nothing after it — a usage error and not a note."""
    rest, confirmed = hw.take_gate([ENTRY_ID, "--notes", "--confirm"])
    assert rest == [ENTRY_ID, "--notes"]
    assert confirmed is True


# --------------------------------------------------------------------------------------
# Unconfirmed: a preview that is the body itself, and nothing on the wire
# --------------------------------------------------------------------------------------

def test_an_unconfirmed_create_previews_and_sends_nothing(live_harvest):
    """Asserted on the recorded requests, not the exit code: a module that posted and then
    printed a preview would pass on the latter."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 4001})})
    r = performed(hw.create(BODY), confirmed=False)

    assert srv.requests == [], "no flag, no request of any kind"
    assert r.code == 0 and r.err == ""
    assert r.lines[0].startswith("WOULD POST ")
    assert hw.CONFIRM_FLAG in r.lines[1], "the second line names the flag that would post"


def test_an_unconfirmed_update_previews_the_entry_it_would_change(live_harvest):
    """A patch body says what would change and not where, so the preview carries the id —
    without it the user approves a change to an entry they cannot see named."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = performed(hw.update(ENTRY_ID, {"notes": "x"}), confirmed=False)

    assert srv.requests == []
    assert r.code == 0
    assert r.lines[0].startswith(f"WOULD PATCH {ENTRY_ID} ")
    assert hw.CONFIRM_FLAG in r.lines[1]


@pytest.mark.parametrize("write", [
    hw.create(BODY),
    hw.update(ENTRY_ID, {"started_time": "09:15", "ended_time": "10:45"}),
], ids=["create", "update"])
def test_the_preview_is_byte_for_byte_the_body_the_confirmed_run_sends(live_harvest, write):
    """The property the gate rests on: what the user approves is what goes on the wire.
    Both come out of one `Write`, so they cannot drift — and this is the assertion that
    says so, for both kinds of write, without a script in between."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 1}),
                        ("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})

    preview = performed(write, confirmed=False)
    performed(write, confirmed=True)

    line = preview.lines[0]
    previewed = json.loads(line[line.index("{"):])
    assert previewed == srv.requests[0]["body"]
    assert hw.preview_line(write) == line


def test_a_preview_never_reads_as_a_posted_entry(live_harvest):
    """`OK <id>` is the shape a run records an entry by; a preview borrowing it would have
    the run record an id for an entry nobody made."""
    live_harvest({("POST", "/time_entries"): (201, {"id": 4003})})
    r = performed(hw.create(BODY), confirmed=False)
    assert not r.out.startswith("OK ")


# --------------------------------------------------------------------------------------
# Confirmed: the write, then `OK <id>` — or `ERR …` and exit 1
# --------------------------------------------------------------------------------------

def test_a_confirmed_create_posts_the_body_and_prints_the_new_id(live_harvest):
    """The body on the wire is the body declared, unaltered, and the id printed is the one
    the provider returned — the run's only record of what it made."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 4002})})
    r = performed(hw.create(BODY), confirmed=True)

    assert r.code == 0 and r.lines == ["OK 4002"]
    assert srv.sent("POST", "/time_entries")[0]["body"] == BODY


def test_a_confirmed_update_patches_that_entry_and_only_that_body(live_harvest):
    """PATCH semantics: only the fields declared go over the wire, to the path that names
    the entry, so a note change cannot touch the times."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = performed(hw.update(ENTRY_ID, {"notes": "x"}), confirmed=True)

    assert r.code == 0 and r.lines == [f"OK {ENTRY_ID}"]
    sent = srv.sent("PATCH", "/time_entries")
    assert [(s["path"], s["body"]) for s in sent] == [(f"/v2/time_entries/{ENTRY_ID}",
                                                       {"notes": "x"})]


def test_a_rejected_write_is_an_err_line_carrying_the_status_and_exit_one(live_harvest):
    """A model reads this output; a traceback reads to it as "the tool is broken" and sends
    it debugging the script instead of fixing its own argument."""
    live_harvest({("POST", "/time_entries"): (422, {"message": "Task is not assigned"})})
    r = performed(hw.create(BODY), confirmed=True)

    assert r.code == 1 and r.out == ""
    assert r.err.startswith("ERR 422")
    assert "Task is not assigned" in r.err
    assert "Traceback" not in r.err


# --------------------------------------------------------------------------------------
# The guard both writers share: two clock times, in order, or `ERR` before any of that
# --------------------------------------------------------------------------------------

def test_a_forward_range_comes_back_as_both_readings_in_minutes():
    """The create needs the minutes for its duration arithmetic; 12-hour forms are accepted
    because that is how the tables the user reads from print them."""
    assert hw.ordered_minutes("8:15am", "12:21pm") == (495, 741)


@pytest.mark.parametrize("started,ended", [("10:00", "09:00"), ("09:00", "09:00")],
                         ids=["reversed", "zero-length"])
def test_a_range_that_does_not_run_forward_is_refused_by_name(started, ended):
    """Harvest stores a reversed range as a 23h entry and a zero-length one as 0h, silently.
    The refusal names the arguments as the caller spelled them, so it reads as a fix."""
    r = run_cli(_Main(lambda: hw.ordered_minutes(started, ended, "--start", "--end")), [])
    assert r.code == 1 and r.out == ""
    assert r.err.startswith("ERR --start (")
    assert "must be before --end" in r.err


def test_a_time_that_cannot_be_parsed_is_an_err_line_not_a_traceback():
    """The parser raises `ValueError`; left alone that is a traceback, and the model reading
    it would debug the script instead of retyping the time."""
    r = run_cli(_Main(lambda: hw.ordered_minutes("nine", "10:00")), [])
    assert r.code == 1
    assert r.err.startswith("ERR") and "nine" in r.err
    assert "Traceback" not in r.err
