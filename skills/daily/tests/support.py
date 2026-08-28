"""Test support for the billables `daily` scripts: fake servers, a day-builder DSL,
and an in-process CLI runner.

Three jobs, in order of how much trouble they save:

1. **Fake ActivityWatch and Harvest servers.** The scripts hit `http://localhost:5600`
   and `https://api.harvestapp.com` through module-level base URLs. Repointing those
   constants at a local `http.server` gives real end-to-end coverage of `main()` —
   URL construction, bucket discovery, JSON parsing, error paths — without a single
   mock of the code under test.

2. **A day-builder DSL.** AW event streams are the input to every interesting
   calculation, and hand-writing UTC timestamps for a realistic day is both tedious
   and where test bugs come from. `day()` takes local `HH:MM` strings and emits the
   UTC events AW would.

3. **`run_cli()`** — invoke a script's `main()` in-process with a patched `sys.argv`,
   capturing stdout / stderr / exit code. Deliberately NOT `subprocess`: a subprocess
   ignores every fixture in `conftest.py`, so it would read the user's real AW data and
   post to their real Harvest account. See the hermeticity fixture there.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import sys
import threading
import urllib.parse

# Every key the scripts resolve through `skill_config.setting()`. One list, because two
# tests want it for opposite reasons and a key in one but not the other is a silent hole:
# `conftest._hermetic` clears each from the process environment so a developer's own shell
# can't leak into an assertion about defaults, and `test_config_seam` asserts that any
# script naming one of them goes through the seam.
SETTING_KEYS = (
    "HARVEST_ACCOUNT_ID", "HARVEST_API_KEY", "TIMESHEET_WORKSPACE",
    "TIMESHEET_SCREENSHOTS_DIR", "DATAVERSE_URL", "PAC_AUTH_PROFILE",
)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, NamedTuple

# --------------------------------------------------------------------------------------
# Local-time DSL
# --------------------------------------------------------------------------------------

DEFAULT_DATE = dt.date(2026, 5, 28)
DEFAULT_OFFSET = 12.0          # NZST, the skill's default
DEFAULT_HOST = "TESTHOST"


def parse_local(s: str) -> dt.timedelta:
    """`'HH:MM'` / `'HH:MM:SS'` as an offset from local midnight.

    Hours are not capped at 23: `'25:30'` means 01:30 the next morning, which is how
    an overnight session is written without juggling two dates. A leading `-` reaches
    back into the previous evening (`'-00:45'` = 23:15 yesterday).
    """
    neg = s.startswith("-")
    parts = [int(p) for p in s.lstrip("-").split(":")]
    while len(parts) < 3:
        parts.append(0)
    h, m, sec = parts
    delta = dt.timedelta(hours=h, minutes=m, seconds=sec)
    return -delta if neg else delta


def _fmt(delta: dt.timedelta) -> str:
    """Inverse of `parse_local`. Hours past 24 are kept, not wrapped, so a generated
    overnight span round-trips."""
    total = int(delta.total_seconds())
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def local_midnight_utc(date: dt.date, offset: float) -> dt.datetime:
    return (dt.datetime.combine(date, dt.time(0, 0), tzinfo=dt.timezone.utc)
            - dt.timedelta(hours=offset))


def iso_z(moment: dt.datetime) -> str:
    """AW's own wire format: UTC with a `Z` suffix and no sub-second part."""
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Day:
    """A synthetic workday, written in local time, rendered as AW event streams.

    Every `add_*` returns self, so a day reads top-to-bottom in the order it happened:

        day().afk("07:00", "08:15").active("08:15", "10:57").afk("10:57", "11:45")
    """

    def __init__(self, date: dt.date = DEFAULT_DATE, offset: float = DEFAULT_OFFSET,
                 host: str = DEFAULT_HOST):
        self.date = date
        self.offset = offset
        self.host = host
        self._afk: list[tuple[str, str, str]] = []
        self._window: list[tuple[str, str, str, str]] = []
        self._web: list[tuple[str, str, str, str, str]] = []   # browser, start, end, title, url
        self.classes: list[dict] = []

    # -- absolute time helpers ---------------------------------------------------------

    def at(self, local: str) -> dt.datetime:
        """The UTC instant of a local `HH:MM` on this day — for asserting against spans."""
        return local_midnight_utc(self.date, self.offset) + parse_local(local)

    # -- building ----------------------------------------------------------------------

    def afk(self, start: str, end: str) -> "Day":
        self._afk.append((start, end, "afk"))
        return self

    def active(self, start: str, end: str) -> "Day":
        self._afk.append((start, end, "not-afk"))
        return self

    def thin(self, start: str, end: str, active_min: float = 6.0,
             idle_min: float = 4.0) -> "Day":
        """Alternating short active / short idle — what supervising a background agent
        looks like to the AFK watcher.

        No single idle reaches the break threshold, so `afk_blocks` reports no break and
        the stretch stays inside one active span; only `active_ratio` reveals it is thin.
        That combination is the skill's hardest judgement call, so scenarios need to be
        able to write it in one line.
        """
        t, stop = parse_local(start), parse_local(end)
        step_a, step_i = dt.timedelta(minutes=active_min), dt.timedelta(minutes=idle_min)
        while t < stop:
            nxt = min(t + step_a, stop)
            self.active(_fmt(t), _fmt(nxt))
            t = nxt
            if t >= stop:
                break
            nxt = min(t + step_i, stop)
            self.afk(_fmt(t), _fmt(nxt))
            t = nxt
        return self

    def locked(self, start: str, end: str, chunk_min: float = 14.0) -> "Day":
        """A screen lock, as AW actually records it: the AFK run arrives fragmented into
        chunks that each fall *under* the break threshold.

        The consequence is the documented quirk in `references/activitywatch.md` —
        `afk_blocks` reports `breaks: (none)` for a stretch that was plainly a break, and
        it surfaces only as a sub-0.4 `active_ratio` window.
        """
        t, stop = parse_local(start), parse_local(end)
        step = dt.timedelta(minutes=chunk_min)
        while t < stop:
            nxt = min(t + step, stop)
            self.afk(_fmt(t), _fmt(nxt))
            t = nxt
        return self

    def window(self, start: str, end: str, app: str, title: str) -> "Day":
        self._window.append((start, end, app, title))
        return self

    def web(self, start: str, end: str, title: str, url: str, browser: str = "firefox") -> "Day":
        self._web.append((browser, start, end, title, url))
        return self

    def classify(self, label: str, regex: str, ignore_case: bool = True) -> "Day":
        """Add an AW category rule, the way the AW settings endpoint returns them."""
        self.classes.append({"name": label.split(">"),
                             "rule": {"type": "regex", "regex": regex, "ignore_case": ignore_case}})
        return self

    # -- rendering ---------------------------------------------------------------------

    def _events(self, rows, data_for) -> list[dict]:
        out = []
        for row in rows:
            start, end = self.at(row[0]), self.at(row[1])
            out.append({"timestamp": iso_z(start),
                        "duration": (end - start).total_seconds(),
                        "data": data_for(row)})
        return out

    def afk_events(self) -> list[dict]:
        return self._events(self._afk, lambda r: {"status": r[2]})

    def window_events(self) -> list[dict]:
        return self._events(self._window, lambda r: {"app": r[2], "title": r[3]})

    def web_events(self, browser: str) -> list[dict]:
        rows = [r for r in self._web if r[0] == browser]
        return self._events([(r[1], r[2], r[3], r[4]) for r in rows],
                            lambda r: {"title": r[2], "url": r[3]})

    def buckets(self) -> dict[str, list[dict]]:
        """The bucket -> events mapping a fake AW server serves for this day."""
        out = {
            f"aw-watcher-afk_{self.host}": self.afk_events(),
            f"aw-watcher-window_{self.host}": self.window_events(),
        }
        for browser in ("firefox", "chrome"):
            evs = self.web_events(browser)
            if evs:
                out[f"aw-watcher-web-{browser}_{self.host}"] = evs
        return out

    def settings(self) -> dict:
        return {"classes": self.classes}

    def date_str(self) -> str:
        return self.date.isoformat()


def day(date: dt.date = DEFAULT_DATE, offset: float = DEFAULT_OFFSET,
        host: str = DEFAULT_HOST) -> Day:
    return Day(date, offset, host)


def with_heartbeats(events: list[dict], steps: int = 3) -> list[dict]:
    """Re-emit each event the way AW does while it is still running: same timestamp,
    progressively longer duration. `dedupe_heartbeats` has to collapse these back.

    The partial copies are appended *after* the full-length one so a consumer that
    took the last-seen duration rather than the longest would read short.
    """
    out = []
    for e in events:
        out.append(e)
        for i in range(1, steps):
            out.append({**e, "duration": e["duration"] * i / steps})
    return out


# --------------------------------------------------------------------------------------
# Fake HTTP servers
# --------------------------------------------------------------------------------------

Handler = Callable[[str, str, dict, dict | None], tuple[int, object]]


class FakeServer:
    """A throwaway localhost HTTP server driven by one `handler(method, path, query, body)`
    callable returning `(status, json_serialisable)`.

    Used as a context manager; `.base` is the URL prefix to patch into the script under
    test. Every request is recorded in `.requests` so a test can assert on the *body sent*
    (which is how the "never post a bare `hours` field" invariant is pinned).
    """

    def __init__(self, handler: Handler):
        self.handler = handler
        self.requests: list[dict] = []
        outer = self

        class _H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):        # keep pytest output clean
                pass

            def _run(self, method):
                parsed = urllib.parse.urlparse(self.path)
                query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                outer.requests.append({"method": method, "path": parsed.path, "query": query,
                                       "body": body, "headers": dict(self.headers)})
                try:
                    status, payload = outer.handler(method, parsed.path, query, body)
                except Exception as exc:      # a broken fake must not hang the client
                    status, payload = 500, {"error": repr(exc)}
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._run("GET")

            def do_POST(self):
                self._run("POST")

            def do_PATCH(self):
                self._run("PATCH")

            def do_DELETE(self):
                self._run("DELETE")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _H)
        self.port = self._server.server_address[1]
        # poll_interval is how long shutdown() blocks; the 0.5s default made every
        # server-using test pay half a second of teardown.
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.01}, daemon=True)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "FakeServer":
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        return False

    # -- assertion helpers -------------------------------------------------------------

    def sent(self, method: str, path_contains: str = "") -> list[dict]:
        return [r for r in self.requests
                if r["method"] == method and path_contains in r["path"]]


def _overlaps(event: dict, start: str | None, end: str | None) -> bool:
    """AW returns events overlapping the range, not just those starting inside it."""
    if not start or not end:
        return True
    s = dt.datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
    e = s + dt.timedelta(seconds=event["duration"])
    lo = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    hi = dt.datetime.fromisoformat(end.replace("Z", "+00:00"))
    return e > lo and s < hi


def aw_server(buckets: dict[str, list[dict]], settings: dict | None = None,
              last_updated: dict[str, str] | None = None,
              settings_status: int = 200) -> FakeServer:
    """A fake ActivityWatch exposing `/api/0/buckets/`, `.../events` and `/api/0/settings`.

    `settings_status` != 200 simulates an AW build whose settings endpoint is absent,
    which is the real-world reason `load_classes()` has to survive an exception.
    """
    settings = settings if settings is not None else {"classes": []}
    last_updated = last_updated or {}

    def handler(method, path, query, body):
        if path == "/api/0/buckets/":
            return 200, {bid: {"id": bid,
                               "last_updated": last_updated.get(bid, "2026-05-28T12:00:00+00:00")}
                         for bid in buckets}
        if path == "/api/0/settings":
            if settings_status != 200:
                return settings_status, {"error": "not found"}
            return 200, settings
        if path.startswith("/api/0/buckets/") and path.endswith("/events"):
            bid = path[len("/api/0/buckets/"):-len("/events")]
            if bid not in buckets:
                return 404, {"error": "no such bucket"}
            evs = [e for e in buckets[bid] if _overlaps(e, query.get("start"), query.get("end"))]
            # AW hands back newest-first; the scripts must not assume chronological order.
            return 200, sorted(evs, key=lambda e: e["timestamp"], reverse=True)
        return 404, {"error": f"unrouted {path}"}

    return FakeServer(handler)


def harvest_server(routes: dict[tuple[str, str], object] | None = None,
                   handler: Handler | None = None) -> FakeServer:
    """A fake Harvest API. Either give a `(method, path)` -> payload map for the simple
    case, or a full handler for tests that need paging or per-call failures.

    Paths are matched exactly against the part after `/v2`, e.g. `("GET", "/users/me")`.
    """
    routes = routes or {}

    def default_handler(method, path, query, body):
        key = (method, path[len("/v2"):] if path.startswith("/v2") else path)
        if key not in routes:
            return 404, {"error": f"unrouted {method} {path}"}
        payload = routes[key]
        if callable(payload):                       # a function gets query + body
            return payload(query, body)
        if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[0], int):
            return payload                          # an explicit (status, body) pair
        return 200, payload                         # a bare body means 200

    return FakeServer(handler or default_handler)


# --------------------------------------------------------------------------------------
# In-process CLI runner
# --------------------------------------------------------------------------------------

class CliResult(NamedTuple):
    code: int
    out: str
    err: str

    @property
    def lines(self) -> list[str]:
        return [ln for ln in self.out.splitlines() if ln.strip()]

    def json(self):
        return json.loads(self.out)


def run_cli(module, args: list) -> CliResult:
    """Run `module.main()` with `args` as its command line, in this process.

    Handles both `main()` conventions in the skill: `afk_blocks` / `activity_timeline`
    *return* an exit code, while `harvest_post` / `harvest_patch` / `harvest_list` call
    `sys.exit()`. A `sys.exit("message")` is folded back into stderr with code 1, which
    is what the shell would show.
    """
    out, err = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    sys.argv = [getattr(module, "__file__", "script")] + [str(a) for a in args]
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            returned = module.main()
        code = 0 if returned is None else int(returned)
    except SystemExit as e:
        if e.code is None:
            code = 0
        elif isinstance(e.code, int):
            code = e.code
        else:
            err.write(str(e.code) + "\n")
            code = 1
    finally:
        sys.argv = old_argv
    return CliResult(code, out.getvalue(), err.getvalue())


