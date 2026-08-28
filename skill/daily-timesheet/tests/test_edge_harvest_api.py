"""Edge cases of the three Harvest CLIs and the client they share.

Everything here asserts on what actually went over the wire — the recorded request body,
the query string, the headers — rather than on what the script said it did. The two are
not the same thing, and the gap between them is where the expensive bugs live: a body
that says `hours` instead of `started_time` still prints `OK 12345`.

No `subprocess` anywhere. `run_cli` runs `main()` in-process so conftest's hermeticity
fixture still holds; a subprocess would read the real `.env` and post real time entries
to a client's timesheet.
"""
from __future__ import annotations

import contextlib
import gc
import re
import threading
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import harvest_client as hc
import harvest_list as hlist
import harvest_patch as hp
import harvest_post as hpost
from support import run_cli

POST_ARGS = ["48084036", "20753151", "2026-08-12", "09:00", "10:30", "Wrote the edge tests"]
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
        "notes": "Wrote the edge tests",
    }


def test_post_passes_12_hour_times_through_verbatim(live_harvest):
    """The script accepts `8:15am` as well as `08:15` and must forward whichever the user
    typed. Normalising to 24h here would be a second, silent parser between the user and
    Harvest — and the one place the two disagree is exactly where a wrong entry lands."""
    srv = live_harvest({("POST", "/time_entries"): (201, {"id": 3002})})
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "8:15am", "12:21pm", "n"])
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
    r = run_cli(hpost, ["48084036", "20753151", "2026-08-12", "09:00", "10:30", notes])
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

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(RuntimeError):
            hc.request("POST", "/time_entries", body={"project_id": 1})
        gc.collect()

    assert [w for w in caught if issubclass(w.category, ResourceWarning)] == []


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


def test_an_empty_response_body_reads_as_an_empty_dict(monkeypatch):
    """Harvest answers a DELETE with `200` and zero bytes. `json.loads("")` raises, so an
    unguarded parse turns a successful call into a traceback from inside the client.

    `support.FakeServer` always `json.dumps` its payload and so can never send an empty
    body; this is the one case that needs a raw server.
    """
    with _raw_http(200, b"") as base:
        monkeypatch.setattr(hc, "API_BASE", f"{base}/v2")
        monkeypatch.setattr(hc, "_CREDS_CACHE", ("test-account", "test-key"))
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
    monkeypatch.setattr(hc, "ENV_PATH", env)
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
    r = run_cli(hp, [ENTRY_ID, "--notes", "Reworded for the client"])
    assert r.code == 0
    assert r.lines == [f"OK {ENTRY_ID}"]

    assert srv.sent("PATCH", "/time_entries")[0]["body"] == {"notes": "Reworded for the client"}


def test_patch_sends_both_times_and_nothing_else_when_shifting_a_block(live_harvest):
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--start", "09:15", "--end", "10:45"])
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
    r = run_cli(hp, [ENTRY_ID, "--hours", "1.5"])
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
    r = run_cli(hp, [ENTRY_ID, "--notes", "first draft", "--notes", "second draft"])

    assert r.code != 0
    assert srv.sent("PATCH", "/time_entries") == [], "nothing may be written on ambiguous input"


def test_patch_rejects_an_unknown_flag_by_name(live_harvest):
    """A typo like `--note` would otherwise be swallowed or, worse, parsed as an entry id.
    Naming the offending flag is what makes the message actionable."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--note", "typo"])

    assert r.code != 0
    assert "Unknown flag: --note" in r.err
    assert "Usage:" in r.err            # the message shows the flags that do exist
    assert srv.sent("PATCH", "/time_entries") == []


def test_patch_rejects_a_flag_with_no_value(live_harvest):
    """A shell that ate an empty quoted argument leaves a trailing bare flag. Reading past
    the end of argv is an IndexError traceback; the contract is a named error."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID, "--notes"])

    assert r.code != 0
    assert "Missing value for --notes" in r.err
    assert srv.sent("PATCH", "/time_entries") == []


def test_patch_rejects_an_entry_id_with_no_flags_at_all(live_harvest):
    """An empty PATCH body is a no-op that Harvest answers 200 to. Exiting 0 on it tells
    the caller the edit landed when nothing was even attempted."""
    srv = live_harvest({("PATCH", f"/time_entries/{ENTRY_ID}"): {"id": int(ENTRY_ID)}})
    r = run_cli(hp, [ENTRY_ID])

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
    r = run_cli(hp, ["not-an-id", "--notes", "x"])

    assert srv.sent("PATCH", "/time_entries")[0]["path"] == "/v2/time_entries/not-an-id"
    assert r.code == 1
    assert r.err.startswith("ERR")
    assert "404" in r.err
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


def _list_routes(pages: list[dict]):
    """Route `/time_entries` as `pages`, chaining `next_page` the way Harvest does."""
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
# A raw HTTP server, for the one response shape FakeServer cannot express
# ======================================================================================

@contextlib.contextmanager
def _raw_http(status: int, raw: bytes):
    """Serve one fixed byte string to every request; yield the base URL.

    `support.FakeServer` renders its payload with `json.dumps`, which has no output for
    "no body at all" — `None` becomes the four bytes `null`. Only a handler writing
    `Content-Length: 0` produces the empty response Harvest sends for a DELETE.
    """
    class _H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _run(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        do_GET = do_POST = do_PATCH = do_DELETE = _run

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _H)
    thread = threading.Thread(target=srv.serve_forever,
                              kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
