"""Create a Harvest time entry. Compact output for low token cost.

Usage:
  python harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' [--confirm]

**`--confirm` is the confirmation gate.** Without it nothing is written: the
script prints the exact body it would have sent and exits 0, so a forgotten flag
yields a preview rather than an error. SKILL.md Step 8 is where the user's yes is
obtained; TESTING.md § "The confirmation gate" is why the gate is here as well as
there.

Times accept either 24h ("08:15") or 12h ("8:15am") — Harvest accepts both.
Always sends started_time + ended_time so accounts in start/end-time mode get
a fixed-duration entry (not a running timer). See SKILL.md Step 9 for context.

Harvest derives the duration from those two clock times, which is wrong by an
hour for an entry worked straight through the autumn change — so this needs
`TIMESHEET_TIMEZONE` to know when that is, and refuses such an entry rather
than billing it short. See `refusal_for_a_straddled_change()` below.

Use SINGLE quotes around notes in bash/PowerShell to avoid $variable
interpolation mangling money references like "$5k" or token-shaped substrings.

Success: prints `OK <entry_id>` and exits 0.
Preview: prints `WOULD POST <body>` and exits 0 — no entry exists.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import datetime as dt
import json
import sys

import aw_client
from harvest_client import parse_time_to_minutes, request, use_utf8

CONFIRM_FLAG = "--confirm"

USAGE = ("Usage: harvest_post.py PROJECT_ID TASK_ID YYYY-MM-DD HH:MM HH:MM 'notes' "
         f"[{CONFIRM_FLAG}]\n"
         f"Without {CONFIRM_FLAG} the entry is previewed, not created.")


def clock(minutes: int) -> str:
    """Minutes-since-midnight as the plain `HH:MM` this script's own arguments are in.

    Deliberately not an echo of what the user typed: `8:15am` and `08:15` are the same
    entry, and a refusal below has to name times the user did *not* type, so all four
    times in that message are written one way or they cannot be compared by eye.
    """
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _minutes(t: dt.time) -> int:
    """A clock reading as minutes since midnight, the unit every time here is compared in."""
    return t.hour * 60 + t.minute


def hours(minutes: int) -> str:
    """Minutes as the decimal hours Harvest bills them in — 165 -> `2.75`.

    Two decimals, then trailing zeros trimmed to one: `3.0` rather than `3`, which is the
    shape `references/output-format.md` writes hours in and the shape Harvest shows them
    back in. A stretch that is not a whole number of minutes' worth of quarter-hours reads
    rounded, e.g. 100 minutes as `1.67` — the times above it are exact, and they are what
    the entry is actually posted from.
    """
    text = f"{minutes / 60:.2f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def refusal_for_a_straddled_change(spent, start_min, end_min, zone) -> str | None:
    """Why this entry cannot be posted as one, or None if it can.

    Harvest stores two clock times and bills their difference. On the day the clocks go
    back, an entry worked straight through the change is short by exactly the repeated
    hour: `01:30`-`04:15` in `Pacific/Auckland` on 2026-04-05 bills 2.75 hrs for 3.75 hrs
    of work. Nothing raises — the entry is well-formed, and it reads correctly in every
    listing afterwards, so there is no later moment at which anyone finds out.

    **It refuses only the entry that is unambiguously wrong**, which is the one whose
    clock interval contains the whole repeated hour. The tempting rule — "the clock
    interval and the elapsed time disagree" — refuses the two replacements this message
    recommends, because `01:30`-`03:00` also spans 1.5 clock hours and 2.5 real ones if
    its end is read as the unambiguous `03:00` an hour after the change. Inside the
    repeated hour the script cannot know which pass a bare `02:30` means, and both
    readings bill correctly for their own pass, so anything short of containment is left
    alone. `references/output-format.md` keeps the hand-split guidance for those.

    It refuses rather than splitting. Two entries out of one approval would put a body on
    the wire the user never previewed, which is the property the confirmation gate exists
    to hold.
    """
    change = aw_client.transition_clocks(spent, zone)
    if change is None:
        return None
    if not change.repeats:
        # A spring-forward. The clock skips rather than repeating, so an entry across it
        # is over-billed rather than short, and its two pieces would be separated by a gap
        # where these two abut — a different message, and #23 put it out of scope. The
        # `TESTING.md` Open gaps entry for the skipped hour carries it.
        return None
    repeat_open = _minutes(change.once_passed)
    repeat_close = _minutes(change.as_reached)
    if repeat_open >= repeat_close:
        # The repeated span crosses midnight, as it does in `America/Santiago`, where the
        # clocks go back at 00:00 to 23:00. No entry this script would accept can contain
        # it — the reversed-time check above has already refused everything that starts
        # before midnight and ends after it — so there is nothing here to catch.
        return None
    if not (start_min < repeat_open and end_min > repeat_close):
        return None

    first, second = repeat_close - start_min, end_min - repeat_open
    return (
        f"ERR {clock(start_min)}-{clock(end_min)} on {spent} runs straight through the "
        f"daylight-saving change in {aw_client.zone_label(zone)}.\n"
        f"  Harvest bills the difference between the two clock times, so this entry would "
        f"record {hours(end_min - start_min)} hrs against the {hours(first + second)} hrs "
        f"that really passed. Post two entries instead:\n"
        f"      {clock(start_min)} {clock(repeat_close)}   ({hours(first)} hrs)\n"
        f"      {clock(repeat_open)} {clock(end_min)}   ({hours(second)} hrs)\n"
        f"  Those two look like they overlap by an hour and do not — they abut. The clocks "
        f"go back at one instant, and that instant reads {clock(repeat_close)} as you "
        f"reach it and {clock(repeat_open)} once it has passed, so the first entry ends "
        f"and the second begins at the same moment. Closing the apparent overlap is what "
        f"loses the repeated hour, which is why this is refused rather than split for you. "
        f"Say in the day's notes that the clocks changed — the overlap is the first thing "
        f"a reviewer will query.")


def main() -> None:
    use_utf8()
    # The flag is removed wherever it appears, so it can be typed before or after the
    # positionals. Notes spelled exactly `--confirm` would be eaten too — and the argument
    # count then falls short, which is a usage error rather than a silent post.
    args = [a for a in sys.argv[1:] if a != CONFIRM_FLAG]
    confirmed = len(args) != len(sys.argv) - 1
    if len(args) != 6:
        sys.exit(USAGE)
    project_id, task_id, spent_date, started, ended, notes = args

    try:
        start_min = parse_time_to_minutes(started)
        end_min = parse_time_to_minutes(ended)
    except ValueError as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
    if end_min <= start_min:
        print(
            f"ERR start ({started}) must be before end ({ended}). "
            "Harvest otherwise silently stores reversed times as 23h entries "
            "and zero-duration as 0h — the script blocks both.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        project_id_n, task_id_n = int(project_id), int(task_id)
    except ValueError:
        print(
            f"ERR project_id and task_id must be numeric Harvest ids, got "
            f"{project_id!r} and {task_id!r}. A project *code* like 'ACM-CR202' is not "
            "an id — run harvest_lookup.py to resolve it.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        spent = dt.date.fromisoformat(spent_date)
    except ValueError:
        # Read rather than passed through because the guard below needs the date to know
        # whether the clocks changed on it. Harvest answers a malformed one with a 422 and
        # its own wording; saying so here costs a round trip less and names the format.
        print(f"ERR spent_date must be YYYY-MM-DD, got {spent_date!r}.", file=sys.stderr)
        sys.exit(1)

    # Last of the checks, and the only one that reads configuration: a plain typo in the
    # arguments should be answered as a typo, not as a missing setting. The zone is asked
    # for without an offset flag: this script has none to offer — see `resolve_zone`.
    refusal = refusal_for_a_straddled_change(
        spent, start_min, end_min,
        aw_client.resolve_zone(None, offers_offset_flag=False))
    if refusal:
        # Before the preview as well as before the post. The preview is what the user says
        # yes to, so an entry that must not be created must not be offered either.
        print(refusal, file=sys.stderr)
        sys.exit(1)

    body = {
        "project_id": project_id_n,
        "task_id": task_id_n,
        "spent_date": spent_date,
        "started_time": started,
        "ended_time": ended,
        "notes": notes,
    }
    if not confirmed:
        # The body itself, not a rendering of it: a preview that describes the entry in
        # its own words is a second description that can drift from the first, and the
        # user would then be approving the paraphrase rather than the entry.
        print(f"WOULD POST {json.dumps(body, ensure_ascii=False)}")
        print(f"Nothing was posted. Re-run with {CONFIRM_FLAG} to create this entry.")
        return
    try:
        resp = request("POST", "/time_entries", body=body)
    except RuntimeError as e:
        print(f"ERR {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK {resp['id']}")


if __name__ == "__main__":
    main()
