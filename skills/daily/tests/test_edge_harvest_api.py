"""Edge cases of the three Harvest CLIs and the client they share.

Everything here asserts on what actually went over the wire — the recorded request body,
the query string, the headers — rather than on what the script said it did. The two are
not the same thing, and the gap between them is where the expensive bugs live: a body
that says `hours` instead of `started_time` still prints `OK 12345`.

No `subprocess` anywhere. `run_cli` runs `main()` in-process so conftest's hermeticity
fixture still holds; a subprocess would read the real `.env` and post real time entries
to a client's timesheet.

Every invocation here carries `--confirm`, including the ones asserting a refusal. The
confirmation gate would block all of them on its own, so a guard test run without the flag
would pass whether or not the guard it names still exists. The gate's own contract is in
`test_cli_contracts.py`.
"""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

import pytest

import harvest_client as hc
import harvest_list as hlist
import harvest_patch as hp
import harvest_post as hpost
import harvest_write as hw
import skill_config
import timezone as tz
from support import CREATE_ARGS, NO_BODY, resource_warnings_from, run_cli

CONFIRM = "--confirm"
POST_ARGS = [*CREATE_ARGS, CONFIRM]
ENTRY_ID = "2988748904"


# ======================================================================================
# harvest_post.py — the invariant this whole file exists for
# ======================================================================================

def test_post_always_sends_started_and_ended_time_and_never_a_bare_hours_field(live_harvest):
    """On a start/end-time Harvest account — which is the account this skill is used on —
    a body carrying `hours` instead of `started_time`/`ended_time` does not create a
    fixed entry. It starts a **running timer**, which keeps accruing until someone
    notices, and the day's total silently inflates on a client-facing invoice.

    The module docstring and SKILL.md Step 9 both promise this and nothing enforced it.
    Asserted against the recorded body, because `OK <id>` is printed either way.
    """
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 3001})})
    r = run_cli(hpost, POST_ARGS)
    assert r.code == 0

    posts = srv.sent("POST", "/time_entries")
    assert len(posts) == 1, "one entry per invocation, no retries"
    body = posts[0]["body"]

    assert "hours" not in body, "a bare `hours` field creates a running timer, not an entry"
    assert body == {
        "project_id": 48084036,          # coerced to int, not left as the argv string
        "task_id": 20753151,
        "spent_date": "2026-08-12",
        "started_time": "09:00",
        "ended_time": "10:30",
        "notes": "Drafted the spec",
    }


def test_post_passes_12_hour_times_through_verbatim(live_harvest):
    """The script accepts `8:15am` as well as `08:15` and must forward whichever the user
    typed. Normalising to 24h here would be a second, silent parser between the user and
    Harvest — and the one place the two disagree is exactly where a wrong entry lands."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 3002})})
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "8:15am", "12:21pm", "n",
                        CONFIRM])
    assert r.code == 0

    body = srv.sent("POST", "/time_entries")[0]["body"]
    assert body["started_time"] == "8:15am"
    assert body["ended_time"] == "12:21pm"
    assert "hours" not in body


def test_post_prints_ok_and_the_entry_id_and_exits_zero(live_harvest):
    """`OK <id>` is the whole machine-readable contract: the id is what a follow-up
    `harvest_patch.py` needs. A reworded success line orphans every entry it creates."""
    live_harvest({("POST", "/time_entries"): (201, {"id": 3003})})
    r = run_cli(hpost, POST_ARGS)
    assert r.code == 0
    assert r.lines == ["OK 3003"]


def test_post_sends_notes_through_the_json_body_byte_for_byte(live_harvest):
    """Notes carry money references (`$5k`), client names with accents, and occasionally a
    newline. If any of those are mangled between argv and the JSON body, the mangling
    lands on the invoice line a client reads — and nobody re-reads notes after posting."""
    notes = "Reviewed $5k variation with Renée — naïve estimate\nfollow-up: $12.5k cap"
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 3004})})
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "09:00", "10:30", notes,
                        CONFIRM])
    assert r.code == 0
    assert srv.sent("POST", "/time_entries")[0]["body"]["notes"] == notes


def test_post_turns_an_api_rejection_into_an_err_line_not_a_traceback(live_harvest):
    """Harvest rejects a task that is not assigned to the project. The model reading this
    output has to tell "your arguments were wrong" from "the tool is broken"; a traceback
    reads as the latter and sends it debugging the script instead of fixing the ids."""
    live_harvest({("POST", "/time_entries"): (422, {"message": "Task is not assigned"})})
    r = run_cli(hpost, POST_ARGS)
    assert r.code == 1
    assert r.err.startswith("ERR")
    assert "422" in r.err
    assert "Task is not assigned" in r.err
    assert "Traceback" not in r.err
    assert r.out == ""


def post_on(monkeypatch, live_harvest, zone, date, start, end):
    """A confirmed create against a named zone, with the wire watched.

    Returns `(result, requests)`. The scenario-day case is in `test_scenarios.py`; these
    are the zones and dates that break an assumption the New Zealand one cannot reach.
    """
    monkeypatch.setenv("TIMESHEET_TIMEZONE", zone)
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 3010})})
    r = run_cli(hpost, ["48084036", "20753151", date, start, end, "Cutover", CONFIRM])
    return r, srv.sent("POST", "/time_entries")


def test_a_change_of_half_an_hour_is_split_at_half_an_hour(monkeypatch, live_harvest):
    """`Australia/Lord_Howe` moves by thirty minutes, so 01:30-02:00 is the span that
    happens twice and the second entry has to start at `01:30`, not at an assumed hour
    earlier. 1.0 + 1.5 is the 2.5 hrs really worked between 01:00 and 03:00 there; an
    assumed hour would name a second entry of 2.0 and bill half an hour that never
    happened."""
    r, sent = post_on(monkeypatch, live_harvest, "Australia/Lord_Howe",
                      "2026-04-05", "01:00", "03:00")
    assert sent == [] and r.code != 0
    assert "01:00 02:00" in r.err and "01:30 03:00" in r.err
    assert "(1.0 hrs)" in r.err and "(1.5 hrs)" in r.err
    assert "2.5 hrs that really passed" in r.err


def test_an_entry_across_a_spring_forward_is_left_alone(monkeypatch, live_harvest):
    """Out of scope for the refusal, and deliberately so: the clock skips rather than
    repeating, so this entry is over-billed rather than short and its two pieces would be
    separated by a gap where the fall-back ones abut. A message written for one and shown
    for the other sends the reader hunting the wrong hour — `TESTING.md` § Open gaps
    carries what is left.

    Two independent checks stop it, so this alone cannot say which: on a spring-forward the
    two readings also arrive in the order that makes the span look like it wraps midnight.
    The test below pins the one that states the scope."""
    r, sent = post_on(monkeypatch, live_harvest, "Pacific/Auckland",
                      "2026-09-27", "01:30", "04:15")
    assert r.code == 0 and r.lines == ["OK 3010"]
    assert (sent[0]["body"]["started_time"], sent[0]["body"]["ended_time"]) == ("01:30", "04:15")


def test_the_direction_of_the_change_is_what_decides_it_not_the_arithmetic(monkeypatch):
    """`repeats` is the line between the two kinds of transition day, and it has to be a
    check somebody wrote rather than a side effect of the containment test collapsing —
    which is the criticism `TESTING.md` § Open gaps already makes of a refusal that emerged
    from arithmetic in `parse_range`. Removing it changes no result today, because the
    reading order catches the same days by coincidence, so nothing else here would notice.

    The pair below is therefore constructed and not a real zone's: a fall-back's readings
    with the direction flipped. No zone produces it, and that is the point — it isolates
    the one branch. 90 and 255 are `01:30` and `04:15` in minutes since midnight."""
    zone = ZoneInfo("Pacific/Auckland")
    fall_back = tz.Transition(dt.time(3, 0), dt.time(2, 0), repeats=True)
    monkeypatch.setattr(tz, "transition_clocks", lambda *a: fall_back)
    assert hw.refusal_for_a_straddled_change(dt.date(2026, 4, 5), 90, 255, zone)

    monkeypatch.setattr(tz, "transition_clocks", lambda *a: fall_back._replace(repeats=False))
    assert hw.refusal_for_a_straddled_change(dt.date(2026, 4, 5), 90, 255, zone) is None


def test_clocks_going_back_at_midnight_do_not_refuse_an_ordinary_working_day(
        monkeypatch, live_harvest):
    """`America/Santiago` goes back at 00:00 to 23:00, so its repeated span is the last
    hour of the date and no entry this script accepts can contain it — a reversed one is
    already refused. The containment test is written in minutes since midnight, where that
    span reads as 23:00 *to* 00:00 and so contains every entry of the day. Nine to five on
    that date posts normally."""
    r, sent = post_on(monkeypatch, live_harvest, "America/Santiago",
                      "2026-04-04", "09:00", "17:00")
    assert r.code == 0 and r.lines == ["OK 3010"]
    assert (sent[0]["body"]["started_time"], sent[0]["body"]["ended_time"]) == ("09:00", "17:00")


def test_a_date_that_is_not_a_date_is_refused_before_anything_is_sent(live_harvest):
    """The date is now read rather than passed through, because the guard above needs to
    know whether the clocks changed on it. Harvest answers a malformed one with a 422 of
    its own; saying so here costs a round trip less and names the format."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 3011})})
    r = run_cli(hpost, ["48084036", "20753151", "12/08/2026", "09:00", "10:30", "n", CONFIRM])
    assert srv.sent("POST", "/time_entries") == []
    assert r.code == 1 and r.err.startswith("ERR") and "YYYY-MM-DD" in r.err
    assert "Traceback" not in r.err


# ======================================================================================
# harvest_client.request()
# ======================================================================================

def test_query_parameters_set_to_none_are_dropped_from_the_url(live_harvest):
    """Callers build one query dict and leave the optional keys as None. Encoded literally
    they become `to=None`, which Harvest reads as a date and rejects — or worse, ignores,
    returning a range nobody asked for."""
    srv = live_harvest({("GET", "/time_entries"): {"time_entries": []}})
    hc.request("GET", "/time_entries",
               query={"from": "2026-08-12", "to": None, "page": 2, "user_id": None})

    assert srv.sent("GET", "/time_entries")[0]["query"] == {"from": "2026-08-12", "page": "2"}


def test_a_query_of_only_none_values_sends_no_query_string_at_all(live_harvest):
    srv = live_harvest({("GET", "/users/me"): {"id": 7}})
    hc.request("GET", "/users/me", query={"page": None})
    assert srv.sent("GET", "/users/me")[0]["query"] == {}


def test_an_http_error_becomes_a_runtime_error_carrying_status_and_body(live_harvest):
    """`urllib` raises `HTTPError`, whose `str()` is "HTTP Error 422: Unprocessable Entity"
    — the reason Harvest gives is in the body, which `HTTPError` throws away once read.
    Every CLI catches `RuntimeError` only, so an escaping `HTTPError` is a traceback."""
    live_harvest({("POST", "/time_entries"): (422, {"message": "Task is not assigned"})})

    with pytest.raises(RuntimeError) as exc:
        hc.request("POST", "/time_entries", body={"project_id": 1})

    assert str(exc.value).startswith("422 ")
    assert "Task is not assigned" in str(exc.value)


def test_a_failed_request_does_not_leak_its_error_response(live_harvest):
    """`urllib`'s `HTTPError` *is* the response — it owns a spooled temp file, so an
    exception whose body is read and then dropped without being closed leaves the handle
    for the garbage collector, whose destructor raises
    `ResourceWarning: Implicitly cleaning up <HTTPError 422: ...>`.

    A warning raised inside `__del__` is *unraisable*: under this suite's
    `filterwarnings = error` it fails whichever test the collector happened to interrupt,
    in a file with no connection to the request that made the mess. Three independent
    agents hit exactly that and each blamed a different test.

    `request()` closes it with `with e:`. This is the test that says it must keep doing
    so — the Harvest-side twin of `test_edge_timeline.py`'s
    `test_an_unavailable_settings_endpoint_does_not_leak_the_error_response`. Collecting
    inside the recorder is what removes the GC-timing ambiguity: the object is either
    closed by now or it warns here, in the test that owns it.
    """
    live_harvest({("POST", "/time_entries"): (422, {"message": "Task is not assigned"})})

    def attempt():
        with pytest.raises(RuntimeError):
            hc.request("POST", "/time_entries", body={"project_id": 1})

    assert resource_warnings_from(attempt) == []


def test_a_huge_error_body_is_capped_at_300_characters(live_harvest):
    """Harvest can answer with an HTML error page. Uncapped it floods the model's context
    with markup, pushing the one useful line out of view."""
    live_harvest({("POST", "/time_entries"): (500, {"error": "x" * 4000 + "TAIL-SENTINEL"})})

    with pytest.raises(RuntimeError) as exc:
        hc.request("POST", "/time_entries", body={})

    message = str(exc.value)
    assert message.startswith("500 ")
    assert len(message) == 304          # "500 " + a 300-character excerpt, nothing more
    assert "TAIL-SENTINEL" not in message


def test_an_empty_response_body_reads_as_an_empty_dict(live_harvest):
    """Harvest answers a DELETE with `200` and zero bytes. `json.loads("")` raises, so an
    unguarded parse turns a successful call into a traceback from inside the client.
    `NO_BODY` is the fake sending nothing — not `null`, which is four bytes of JSON."""
    live_harvest({("DELETE", "/time_entries/1"): (200, NO_BODY)})
    assert hc.request("DELETE", "/time_entries/1") == {}


def test_every_request_carries_the_account_bearer_and_user_agent_headers(live_harvest):
    """Harvest 401s without both `Harvest-Account-Id` and the bearer token, and asks
    integrations to identify themselves with a User-Agent. Losing any one of the three is
    a blanket auth failure that looks like expired credentials."""
    srv = live_harvest({("GET", "/users/me"): {"id": 7}})
    hc.request("GET", "/users/me")

    # urllib title-cases header names on the way out, and HTTP names are case-insensitive.
    sent = {k.lower(): v for k, v in srv.sent("GET", "/users/me")[0]["headers"].items()}
    assert sent["harvest-account-id"] == "test-account"
    assert sent["authorization"] == "Bearer test-key"
    assert sent["user-agent"] == hc.USER_AGENT


def test_load_creds_caches_so_a_second_call_re_reads_nothing(tmp_path, monkeypatch):
    """`harvest_list` makes one call per page. Re-reading `.env` per request costs a file
    open on every one, and — worse — makes the credentials mutable mid-run, so a half-paged
    listing could start authenticating as a different account."""
    env = tmp_path / ".env"
    env.write_text("HARVEST_ACCOUNT_ID=first\nHARVEST_API_KEY=key-one\n", encoding="utf-8")
    monkeypatch.setattr(skill_config, "ENV_PATH", env)
    monkeypatch.setattr(hc, "_CREDS_CACHE", None)

    assert hc.load_creds() == ("first", "key-one")

    env.write_text("HARVEST_ACCOUNT_ID=second\nHARVEST_API_KEY=key-two\n", encoding="utf-8")
    assert hc.load_creds() == ("first", "key-one")

    env.unlink()                        # the file is not consulted again even once gone
    assert hc.load_creds() == ("first", "key-one")


# ======================================================================================
# harvest_patch.py
# ======================================================================================

def test_patch_sends_only_the_fields_whose_flags_were_passed(live_harvest):
    """PATCH means "change these, leave the rest". Any key the script adds on its own —
    a defaulted `hours`, an echoed `spent_date` — overwrites a field on the server that
    the user never asked to touch, and there is no undo on a submitted timesheet."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--notes", "Reworded for the client", CONFIRM])
    assert r.code == 0
    assert r.lines == [f"OK {ENTRY_ID}"]

    assert srv.sent("PATCH", "/time_entries")[0]["body"] == {"notes": "Reworded for the client"}


def test_patch_sends_both_times_and_nothing_else_when_shifting_a_block(live_harvest):
    """The GET is routed because a patch that moves the times reads the entry to learn
    which *date* they would land on — see the fall-back section below. It changes nothing
    about the body that goes out: the read is the guard's, not the write's."""
    srv = live_harvest({
        ("GET", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID), "spent_date": "2026-08-12",
                                               "started_time": "9:00am", "ended_time": "10:30am"},
        ("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)},
    })
    r = run_cli(hp, [ENTRY_ID, "--start", "09:15", "--end", "10:45", CONFIRM])
    assert r.code == 0

    body = srv.sent("PATCH", "/time_entries")[0]["body"]
    assert body == {"started_time": "09:15", "ended_time": "10:45"}
    assert "hours" not in body          # Harvest recomputes hours from the times itself


def test_patch_accepts_hours_on_its_own(live_harvest):
    """A documented footgun on start/end-time accounts, and deliberately still allowed —
    duration-mode accounts have no other way to correct a duration. Pinned so that a
    future "let's just block the footgun" edit is a conscious decision, not a surprise
    for whoever is on a duration-mode account."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--hours", "1.5", CONFIRM])
    assert r.code == 0

    assert srv.sent("PATCH", "/time_entries")[0]["body"] == {"hours": 1.5}


def test_patch_refuses_the_same_flag_given_twice(live_harvest):
    """Last-wins would write only 'b' and exit 0, so the caller believes both landed. A
    repeated flag is never a deliberate act — it is a command assembled twice, or a model
    appending to an argument list it already populated — and the safe answer is to refuse
    rather than to pick one silently and write it to the timesheet.

    Every sibling guard in this skill (reversed times, non-numeric ids) blocks before the
    request, and `parse_args` blocks this one the same way — which is why the assertion
    below is that nothing reached the wire, not merely that the exit code was non-zero.
    """
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--notes", "first draft", "--notes", "second draft", CONFIRM])

    assert r.code != 0
    assert srv.sent("PATCH", "/time_entries") == [], "nothing may be written on ambiguous input"


def test_patch_rejects_an_unknown_flag_by_name(live_harvest):
    """A typo like `--note` would otherwise be swallowed or, worse, parsed as an entry id.
    Naming the offending flag is what makes the message actionable."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--note", "typo", CONFIRM])

    assert r.code != 0
    assert "Unknown flag: --note" in r.err
    assert "Usage:" in r.err            # the message shows the flags that do exist
    assert srv.sent("PATCH", "/time_entries") == []


def test_patch_rejects_a_flag_with_no_value(live_harvest):
    """A shell that ate an empty quoted argument leaves a trailing bare flag. Reading past
    the end of argv is an IndexError traceback; the contract is a named error.

    `--confirm` goes first here, because `--notes` has to stay the *last* argument for
    there to be nothing after it to read — put the gate after it and `--notes` swallows
    the flag as its value, which is a different test entirely."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, CONFIRM, "--notes"])

    assert r.code != 0
    assert "Missing value for --notes" in r.err
    assert srv.sent("PATCH", "/time_entries") == []


def test_patch_rejects_an_entry_id_with_no_flags_at_all(live_harvest):
    """An empty PATCH body is a no-op that Harvest answers 200 to. Exiting 0 on it tells
    the caller the edit landed when nothing was even attempted."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, CONFIRM])

    assert r.code != 0
    assert "at least one field" in r.err
    assert srv.sent("PATCH", "/time_entries") == []


def test_patch_passes_a_non_numeric_entry_id_straight_through_to_the_url(live_harvest):
    """Pinned as acceptable, deliberately. Unlike `--project-id`, where a project *code*
    is a plausible and recoverable mistake, nothing local can tell a valid entry id from
    an invalid one — only Harvest knows which ids exist. So the id is forwarded verbatim
    and Harvest's 404 is what the user sees, as an `ERR` line rather than a traceback.
    A client-side numeric check would add a second failure mode without removing this one.
    """
    srv = live_harvest({("PATCH", "/time_entries/not-an-id"): (404, {"message": "Not Found"})})
    r = run_cli(hp, ["not-an-id", "--notes", "x", CONFIRM])

    assert srv.sent("PATCH", "/time_entries")[0]["path"] == "/v2/time_entries/not-an-id"
    assert r.code == 1
    assert r.err.startswith("ERR")
    assert "404" in r.err
    assert "Traceback" not in r.err


# --------------------------------------------------------------------------------------
# The entry a patch would leave behind, on the day the clocks go back — #32
# --------------------------------------------------------------------------------------
#
# `harvest_post.py` refuses a create that runs straight through the fall-back, because
# Harvest bills the difference between the two clock times and that entry is short by the
# span that happened twice. The same entry can be *arrived at* by patching a correct one,
# and a patch carries only what it changes — so the guard is on the result, which is the
# body over what the entry already says, and reading that is the one GET this script makes.

AUCKLAND_FALL_BACK = "2026-04-05"       # the clocks go back at 03:00 to 02:00
STRADDLE = ("01:30", "04:15")           # 2.75 clock hours over the 3.75 really worked


def entry_on(date: str = AUCKLAND_FALL_BACK, start: str | None = "1:30am",
             end: str | None = "4:15am") -> dict:
    """One entry as Harvest returns it — 12-hour times, which is how the API writes them."""
    return {"spent_date": date, "started_time": start, "ended_time": end}


def patched(monkeypatch, live_harvest, args, current=None, zone="Pacific/Auckland",
            confirm=True):
    """A patch against a named zone, with the entry Harvest already holds behind the GET.

    Returns `(result, server)`, so a test can say both what the run did and whether it
    paid for the read. `current` is what `GET /time_entries/<id>` answers with; a test
    that expects no read may leave it at its default and assert `srv.sent("GET") == []`.
    """
    monkeypatch.setenv("TIMESHEET_TIMEZONE", zone)
    srv = live_harvest({
        ("GET", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID),
                                               **(current if current is not None
                                                  else entry_on())},
        ("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)},
    })
    argv = [ENTRY_ID, *args] + ([CONFIRM] if confirm else [])
    return run_cli(hp, argv), srv


def test_a_patch_whose_result_straddles_the_change_is_refused_and_nothing_is_sent(
        monkeypatch, live_harvest):
    """The defect #23 predicted and left open: the entry `harvest_post.py` now refuses can
    still be reached by patching a correct one. `01:30`-`04:15` on the fall-back day bills
    2.75 hrs against 3.75 worked, is well-formed, and reads correctly in every listing
    afterwards — so there is no later moment at which anyone finds out."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--start", STRADDLE[0], "--end", STRADDLE[1]],
                     entry_on(start="9:00am", end="10:30am"))

    assert srv.sent("PATCH") == [], "nothing may be written that would bill short"
    assert r.code == 1 and r.out == ""
    assert "runs straight through the daylight-saving change" in r.err
    assert "Traceback" not in r.err


def test_the_refusal_is_the_create_s_message_rather_than_a_second_wording(
        monkeypatch, live_harvest):
    """One message, one owner — `references/self-development.md` § "Rules with more than
    one copy" registers it as `refusal_for_a_straddled_change()`'s. A restatement here
    would be a second thing to keep true, and the arithmetic in it has already been wrong
    in prose once."""
    r, _ = patched(monkeypatch, live_harvest,
                   ["--start", STRADDLE[0], "--end", STRADDLE[1]])

    expected = hw.refusal_for_a_straddled_change(
        dt.date(2026, 4, 5), 90, 255, ZoneInfo("Pacific/Auckland"))
    assert expected is not None
    assert r.err.strip() == expected.strip()


@pytest.mark.parametrize("args,current", [
    (["--start", "01:30"], entry_on(start="2:30am")),
    (["--end", "04:15"], entry_on(end="2:30am")),
    (["--date", AUCKLAND_FALL_BACK], entry_on(date="2026-08-12")),
], ids=["start-alone", "end-alone", "date-alone"])
def test_every_flag_that_can_produce_the_straddle_on_its_own_reaches_the_guard(
        monkeypatch, live_harvest, args, current):
    """A patch carries only what it changes, so each of these is a *whole* straddling
    entry once it lands on the one already there. The third is the one no arithmetic over
    the arguments could see: the date moves under times nobody typed."""
    r, srv = patched(monkeypatch, live_harvest, args, current)

    assert srv.sent("PATCH") == []
    assert r.code == 1
    assert "runs straight through the daylight-saving change" in r.err


def test_hours_states_a_duration_the_clock_cannot_and_is_never_refused(
        monkeypatch, live_harvest):
    """`--hours 3.75` is the *correct* answer on a transition day — the one way to record
    what really passed when the two clock times cannot say it. Refusing it would leave no
    way to fix the entry at all. It settles the duration outright, so it also ends the
    question before the read."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--date", AUCKLAND_FALL_BACK, "--hours", "3.75"])

    assert r.code == 0
    assert srv.sent("PATCH")[0]["body"] == {"spent_date": AUCKLAND_FALL_BACK, "hours": 3.75}
    assert srv.sent("GET") == [], "the duration is stated, so the entry's times decide nothing"


def test_hours_is_an_exception_for_the_duration_alone_not_a_way_past_the_guard(
        monkeypatch, live_harvest):
    """The escape hatch is for the duration the two clock times cannot state. It is not a
    flag that suspends the check: where the same body also carries times, Harvest
    recomputes hours from them — which is what
    `test_patch_sends_both_times_and_nothing_else_when_shifting_a_block` pins — so the
    entry lands at the 2.75 hrs this exists to refuse, with a `3.75` in the request that
    changed nothing. A model assembling one command to fix both is the likely way here."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--date", AUCKLAND_FALL_BACK, "--start", STRADDLE[0],
                      "--end", STRADDLE[1], "--hours", "3.75"])

    assert r.code == 1 and srv.sent("PATCH") == []
    assert "runs straight through the daylight-saving change" in r.err


def test_the_entry_is_read_once_where_it_is_read_at_all(monkeypatch, live_harvest):
    """The cost the ticket accepted is one read per invocation. A guard that resolved the
    result field by field, or re-read it to answer a second question, would multiply a
    request on the path where PATCH semantics are already the documented trap."""
    r, srv = patched(monkeypatch, live_harvest, ["--start", "09:15", "--end", "10:45"],
                     entry_on(date="2026-08-12", start="9:00am", end="10:30am"))

    assert r.code == 0
    assert len(srv.sent("GET")) == 1


def test_an_unconfirmed_time_patch_still_previews_rather_than_writing(
        monkeypatch, live_harvest):
    """The read is the guard's and the gate is still the write's. Every other preview test
    passes a note, which no longer reaches the read at all — so without this one the
    preview's new dependency on the provider answering is unasserted."""
    r, srv = patched(monkeypatch, live_harvest, ["--start", "09:15", "--end", "10:45"],
                     entry_on(date="2026-08-12", start="9:00am", end="10:30am"),
                     confirm=False)

    assert r.code == 0
    assert r.lines[0].startswith(f"WOULD PATCH {ENTRY_ID} ")
    assert srv.sent("PATCH") == [], "the gate still stands between the preview and the write"


@pytest.mark.parametrize("args", [
    ["--notes", "Reworded for the client"],
    ["--project-id", "48084036"],
], ids=["notes", "project"])
def test_a_patch_that_cannot_move_a_clock_does_not_pay_for_the_read(
        monkeypatch, live_harvest, args):
    """The read is not a tax on every patch. Nothing time-shaped in the body means nothing
    the guard could refuse, and a note correction is the commonest patch there is."""
    r, srv = patched(monkeypatch, live_harvest, args)

    assert r.code == 0
    assert srv.sent("GET") == []


def test_a_date_with_no_transition_settles_it_without_reading_the_entry(
        monkeypatch, live_harvest):
    """The patch names the date, and nothing repeats on it, so no reading of the entry's
    own times could produce a straddle. Ordinary days are every day but two a year."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--start", STRADDLE[0], "--end", STRADDLE[1], "--date", "2026-08-12"])

    assert r.code == 0
    assert srv.sent("GET") == []
    assert srv.sent("PATCH")[0]["body"] == {"started_time": "01:30", "ended_time": "04:15",
                                            "spent_date": "2026-08-12"}


def test_a_patch_that_names_the_date_and_both_times_is_refused_without_reading_anything(
        monkeypatch, live_harvest):
    """The other half of the same rule: the body already says everything the guard needs,
    so the refusal costs nothing either."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--start", STRADDLE[0], "--end", STRADDLE[1],
                      "--date", AUCKLAND_FALL_BACK])

    assert r.code == 1 and srv.sent("PATCH") == []
    assert srv.sent("GET") == []


@pytest.mark.parametrize("start,end", [("01:30", "03:00"), ("02:00", "04:15")],
                         ids=["first", "second"])
def test_the_two_entries_the_refusal_recommends_can_themselves_be_patched(
        monkeypatch, live_harvest, start, end):
    """The guard must not refuse its own advice. Both replacements have one end *at* the
    transition, which the containment test keeps strictly outside — and a run told to
    correct a straddling entry will patch it to the first of these."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--start", start, "--end", end, "--date", AUCKLAND_FALL_BACK])

    assert r.code == 0, r.err
    assert srv.sent("PATCH")[0]["body"]["started_time"] == start


def test_a_straddling_patch_is_refused_before_the_preview_as_well(monkeypatch, live_harvest):
    """The preview is what the user says yes to, and its own last line says to re-run with
    the flag. A change that must not be applied must not be offered."""
    r, srv = patched(monkeypatch, live_harvest,
                     ["--start", STRADDLE[0], "--end", STRADDLE[1]], confirm=False)

    assert r.code == 1 and r.out == "", "nothing may be previewed that cannot then be applied"
    assert srv.sent("PATCH") == []


def test_an_entry_with_no_clock_times_at_all_is_left_alone(monkeypatch, live_harvest):
    """A duration-mode entry comes back with `started_time` null. There is no clock
    interval to straddle, and the guard refuses only what it can read — inventing one
    would block the accounts `--hours` exists for."""
    r, srv = patched(monkeypatch, live_harvest, ["--start", "01:30"],
                     entry_on(start=None, end=None))

    assert r.code == 0
    assert srv.sent("PATCH")[0]["body"] == {"started_time": "01:30"}


def test_a_patch_date_that_is_not_a_date_is_refused_by_name(live_harvest):
    """The date is now read rather than passed through, because the guard needs to know
    whether the clocks changed on it. Harvest answers a malformed one with a 422 of its
    own; saying so here costs a round trip less and names the format."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--date", "05/04/2026", CONFIRM])

    assert srv.sent("PATCH") == []
    assert r.code == 1 and "YYYY-MM-DD" in r.err
    assert "Traceback" not in r.err


def test_an_entry_the_provider_will_not_hand_back_is_an_err_line_not_a_traceback(
        monkeypatch, live_harvest):
    """The read is a request like any other, and a wrong entry id now fails on it rather
    than on the PATCH. Same contract either way — a status and a line, never a traceback,
    and nothing written."""
    monkeypatch.setenv("TIMESHEET_TIMEZONE", "Pacific/Auckland")
    srv = live_harvest({
        ("GET", f"/time_entries/{ENTRY_ID}"): (404, {"message": "Not Found"}),
        ("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)},
    })
    r = run_cli(hp, [ENTRY_ID, "--start", "01:30", CONFIRM])

    assert srv.sent("PATCH") == []
    assert r.code == 1 and r.err.startswith("ERR") and "404" in r.err
    assert "Traceback" not in r.err


# ======================================================================================
# harvest_list.py
# ======================================================================================

def _entry(eid: int, date: str, start: str, end: str, *, hours: float = 1.0,
           notes: str = "note", code: str | None = "ACM-CR202",
           task: str | None = "Gen - Development") -> dict:
    """One Harvest time entry, in the shape the API returns it."""
    out: dict = {"id": eid, "spent_date": date, "started_time": start, "ended_time": end,
                 "hours": hours, "notes": notes}
    if code is not None:
        out["project"] = {"id": 48084036, "code": code}
    if task is not None:
        out["task"] = {"id": 20753151, "name": task}
    return out


def _list_routes(pages: list[list[dict]]):
    """Route `/time_entries` as `pages`, chaining `next_page` the way Harvest does.

    One list of entries per page — every call site has always passed that; the annotation
    said `list[dict]` and made a typechecker shout at all of them.
    """
    def entries(query, body):
        n = int(query["page"])
        return 200, {"time_entries": pages[n - 1],
                     "next_page": n + 1 if n < len(pages) else None}
    return {("GET", "/users/me"): {"id": 7}, ("GET", "/time_entries"): entries}


def test_list_follows_next_page_and_shows_entries_from_every_page(live_harvest):
    """A busy fortnight passes 100 entries. Stopping at page one silently drops the rest,
    and a "what did I log?" review then reports fewer hours than were actually posted —
    the failure mode that makes someone re-enter a day they already had."""
    srv = live_harvest(_list_routes([
        [_entry(101, "2026-08-12", "9:00am", "10:00am")],
        [_entry(202, "2026-08-12", "2:00pm", "3:00pm")],
    ]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0

    calls = srv.sent("GET", "/time_entries")
    assert [c["query"]["page"] for c in calls] == ["1", "2"]
    assert [ln.split()[0] for ln in r.lines] == ["101", "202"]


def test_list_stops_after_one_page_when_there_is_no_next_page(live_harvest):
    srv = live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am")]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0
    assert len(srv.sent("GET", "/time_entries")) == 1


def test_list_sorts_by_date_then_real_start_time_then_id(live_harvest):
    """Harvest returns entries in no useful order, and their times are 12-hour strings.
    Sorted as text, `"12:21pm"` precedes `"8:15am"` — an afternoon block is printed above
    the morning that preceded it, and the day reads as though it happened backwards.
    The ids here are also out of order so the third sort key is exercised, not assumed.
    """
    live_harvest(_list_routes([[
        _entry(500, "2026-08-13", "9:00am", "10:00am"),    # next day — last whatever its time
        _entry(300, "2026-08-12", "12:21pm", "1:30pm"),    # sorts first as a naive string
        _entry(200, "2026-08-12", "8:15am", "9:00am"),     # ties with 100 on date + time
        _entry(100, "2026-08-12", "8:15am", "9:00am"),
    ]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-13"])
    assert r.code == 0
    assert [ln.split()[0] for ln in r.lines] == ["100", "200", "300", "500"]


def test_list_truncates_notes_over_60_characters_with_an_ellipsis(live_harvest):
    """One entry per line is what makes the listing scannable and cheap to read. A pasted
    paragraph in the notes field wraps the terminal and buries every other entry."""
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am", notes="N" * 80)]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0
    assert r.lines[0].endswith("N" * 59 + "…")
    assert "N" * 60 not in r.lines[0]


def test_list_leaves_a_note_of_exactly_60_characters_alone(live_harvest):
    """The boundary: truncating at the limit rather than past it would clip a note that fit."""
    note = "M" * 60
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am", notes=note)]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0
    assert r.lines[0].endswith(note)
    assert "…" not in r.lines[0]


def test_list_flattens_newlines_so_one_entry_stays_on_one_line(live_harvest):
    """Notes composed in an editor arrive with `\\n` and, on Windows, `\\r\\n`. Printed raw
    they split one entry across several lines, and anything counting lines — a human
    scanning, or a model summarising the day — miscounts the entries."""
    live_harvest(_list_routes([[
        _entry(101, "2026-08-12", "9:00am", "10:00am", notes="line one\nline two\r\nline three"),
    ]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0
    assert len(r.lines) == 1
    for fragment in ("line one", "line two", "line three"):
        assert fragment in r.lines[0]


def _columns(line: str) -> list[str]:
    """Split a `harvest_list` row into its fields.

    The row is padded columns joined by two spaces, so a two-or-more-space split recovers
    them while leaving the single spaces inside a task name ("Gen - Development") intact.
    Index 4 is the project code, index 5 the task name.
    """
    return re.split(r"\s{2,}", line.strip())


@pytest.mark.parametrize("code,task,shown_code,shown_task", [
    (None, None, "?", "?"),
    (None, "Gen - Development", "?", "Gen - Development"),
    ("ACM-CR202", None, "ACM-CR202", "?"),
], ids=["both-missing", "code-missing", "task-missing"])
def test_list_renders_a_missing_project_code_or_task_name_as_a_question_mark(
        live_harvest, code, task, shown_code, shown_task):
    """Personal or archived projects come back without a code, and a deleted task without a
    name. Indexing into the missing dict is a KeyError that kills the whole listing — so
    one degraded entry would hide every good one alongside it.

    The two fallbacks in `harvest_list` are independent — `(e.get("project") or {})` and
    `(e.get("task") or {})` — so each is exercised alone as well as together. The
    assertions name the column: counting `?` across the line cannot tell a missing code
    from a missing task, and would still read 2 if one fallback leaked into both.
    """
    live_harvest(_list_routes([[
        _entry(101, "2026-08-12", "9:00am", "10:00am", notes="no metadata",
               code=code, task=task),
    ]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0

    fields = _columns(r.lines[0])
    assert fields[4] == shown_code
    assert fields[5] == shown_task


def test_list_renders_an_entry_whose_hours_are_null(live_harvest):
    """The same shape as the null project below, on the numeric field. `hours` formats with
    `:.2f`, so an explicit `null` is a TypeError that takes the whole listing down — one
    degraded entry hiding every good one, which is the failure the fallbacks exist to
    prevent."""
    entry = _entry(101, "2026-08-12", "9:00am", "10:00am")
    entry["hours"] = None
    live_harvest(_list_routes([[entry]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0
    assert "0.00h" in r.lines[0]


def test_by_day_totals_an_entry_whose_hours_are_null(live_harvest):
    """And on the sweep, where it would take down a month rather than a day."""
    entry = _entry(101, "2026-08-12", "9:00am", "10:00am")
    entry["hours"] = None
    live_harvest(_list_routes([[entry, _entry(102, "2026-08-12", "2:00pm", "3:00pm",
                                              hours=1.0)]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert "1.00h" in r.lines[0]


def test_by_day_survives_an_entry_with_no_date_on_it(live_harvest):
    """The field the rows are grouped by. Absent, it is a KeyError before anything prints —
    and the sweep is the caller reading the most entries, so it is the likeliest to meet
    one and the most expensive to lose."""
    entry = _entry(101, "2026-08-12", "9:00am", "10:00am")
    del entry["spent_date"]
    live_harvest(_list_routes([[entry]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert "0.00h" in r.lines[0]
    assert "Traceback" not in r.err


def test_by_day_says_when_it_could_not_place_an_entry(live_harvest):
    """Surviving it is half the job. An entry dropped from the totals subtracts from a
    date, and a date reading `0.00h` is read downstream as a day nobody billed — which is
    a worklist row telling the user to bill a day that is already billed. The row cannot
    carry the caveat, so stderr does, beside the "(no time entries…)" notice."""
    entry = _entry(101, "2026-08-12", "9:00am", "10:00am")
    del entry["spent_date"]
    live_harvest(_list_routes([[entry]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert "skipped 1" in r.err and "101" in r.err


def test_by_day_says_nothing_when_every_entry_was_placed(live_harvest):
    """The notice has to mean something. Printed on a clean month it is noise the caller
    learns to skip, and then it is not there on the month that needed it."""
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am")]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert "skipped" not in r.err


def test_by_day_says_one_entry_rather_than_one_entries(live_harvest):
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am")]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert "1 entry" in r.lines[0] and "1 entries" not in r.lines[0]


def test_list_renders_a_null_project_and_task_as_question_marks(live_harvest):
    """The other shape of the same problem: the keys are present but explicitly null,
    which `.get(...)` returns happily and `.get(...).get(...)` then dies on."""
    entry = _entry(101, "2026-08-12", "9:00am", "10:00am", notes="no metadata")
    entry["project"] = None
    entry["task"] = None
    live_harvest(_list_routes([[entry]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0

    fields = _columns(r.lines[0])
    assert fields[4] == "?"
    assert fields[5] == "?"


# ======================================================================================
# harvest_list.py --by-day — the month sweep the `reconcile` skill runs
# ======================================================================================
#
# Reconciliation asks one question of a month: which days were never billed, and which
# were billed short. That is arithmetic over the same listing, and the reason it lives
# here rather than in a model's head is the same reason the day skeleton does — a total
# summed by eye off a hundred printed rows is wrong occasionally and silently, and the
# cost is a day billed twice or a day left unbilled forever.
#
# The zero-entry rows are the whole point of the mode: a day with no entries is *absent*
# from the per-entry listing, and absent is exactly what a gap looks like.

def test_by_day_prints_one_row_per_date_in_the_range_including_the_empty_ones(live_harvest):
    """A gap day has no entries, so it has no line in the default listing. Reading gaps
    off an entry listing means reasoning about what *isn't* printed, which is how a
    forgotten Tuesday stays forgotten."""
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am", hours=1.0)]]))
    r = run_cli(hlist, ["2026-08-11", "2026-08-13", "--by-day"])
    assert r.code == 0

    assert [ln.split()[0] for ln in r.lines] == ["2026-08-11", "2026-08-12", "2026-08-13"]
    assert "0.00h" in r.lines[0] and "0.00h" in r.lines[2]
    assert "1.00h" in r.lines[1]


def test_by_day_totals_every_entry_on_a_date_and_counts_them(live_harvest):
    """Billed-short is a comparison against a total, not against one entry: a day holding
    a 0.25h standup and nothing else is short, and it is not empty."""
    live_harvest(_list_routes([[
        _entry(101, "2026-08-12", "9:00am", "9:15am", hours=0.25),
        _entry(102, "2026-08-12", "1:00pm", "3:30pm", hours=2.5),
    ]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert len(r.lines) == 1
    assert "2.75h" in r.lines[0]
    assert "2 entries" in r.lines[0]


def test_by_day_totals_across_every_page(live_harvest):
    """A month passes 100 entries routinely. Stopping at page one under-reports the days
    on later pages — and an under-reported day reads as a day billed short, which sends a
    subagent to investigate a day that was fine."""
    srv = live_harvest(_list_routes([
        [_entry(101, "2026-08-12", "9:00am", "10:00am", hours=1.0)],
        [_entry(202, "2026-08-12", "2:00pm", "4:00pm", hours=2.0)],
    ]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert [c["query"]["page"] for c in srv.sent("GET", "/time_entries")] == ["1", "2"]
    assert "3.00h" in r.lines[0]


def test_by_day_names_the_weekday_so_a_weekend_is_not_chased(live_harvest):
    """Most unbilled Saturdays are Saturdays, not gaps. The weekday is what lets the sweep
    drop them before anything is dispatched to investigate them."""
    live_harvest(_list_routes([[]]))
    r = run_cli(hlist, ["2026-08-15", "2026-08-17", "--by-day"])
    assert r.code == 0
    assert [ln.split()[1] for ln in r.lines] == ["Sat", "Sun", "Mon"]


def test_by_day_names_the_projects_already_billed_on_a_short_day(live_harvest):
    """A day billed short is usually a day billed to *one* of the clients that were on
    screen. Naming what is already there is what tells the worklist which client to look
    past, and it costs nothing — the listing was fetched anyway."""
    live_harvest(_list_routes([[
        _entry(101, "2026-08-12", "9:00am", "10:00am", code="ACM-CR202"),
        _entry(102, "2026-08-12", "10:00am", "11:00am", code="NWC-001"),
        _entry(103, "2026-08-12", "11:00am", "12:00pm", code="ACM-CR202"),
    ]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert "ACM-CR202" in r.lines[0] and "NWC-001" in r.lines[0]
    assert r.lines[0].count("ACM-CR202") == 1, "each project named once, not once per entry"


def test_by_day_refuses_a_range_that_ends_before_it_starts(live_harvest):
    """A transposed month prints no rows at all, and no rows is indistinguishable from a
    month with no gaps in it — the sweep would report "all caught up" over a month it
    never looked at."""
    live_harvest(_list_routes([[]]))
    r = run_cli(hlist, ["2026-08-31", "2026-08-01", "--by-day"])
    assert r.code != 0
    assert "Traceback" not in r.err


def test_by_day_refuses_a_date_it_cannot_parse(live_harvest):
    """The mode walks the range date by date, so a malformed bound is a crash rather than
    the API's own error message."""
    live_harvest(_list_routes([[]]))
    r = run_cli(hlist, ["2026-08-01", "the-31st", "--by-day"])
    assert r.code != 0
    assert "Traceback" not in r.err


def test_by_day_replaces_the_per_entry_rows_rather_than_adding_to_them(live_harvest):
    """The sweep is one cheap read of a month. Printing both shapes puts the per-entry
    listing it was meant to replace back into the context it was meant to save."""
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am")]]))
    r = run_cli(hlist, ["2026-08-12", "2026-08-12", "--by-day"])
    assert r.code == 0
    assert len(r.lines) == 1
    assert "101" not in r.lines[0], "the entry id belongs to the per-entry listing"


def test_the_default_listing_is_unchanged_by_the_flag_existing(live_harvest):
    """The pin on the older contract: `harvest_list.py <date>` is what Step 1 of the
    `daily` skill and `references/setup.md`'s credential check both run."""
    live_harvest(_list_routes([[_entry(101, "2026-08-12", "9:00am", "10:00am")]]))
    r = run_cli(hlist, ["2026-08-12"])
    assert r.code == 0
    assert r.lines[0].split()[0] == "101"
