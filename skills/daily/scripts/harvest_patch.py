"""Update an existing Harvest time entry. PATCH semantics — only passed fields change.

WARNING: --hours is a footgun on start/end-time accounts.
If the account stores entries as started_time + ended_time (most accounts,
including the typical consultancy setup), patching with just --hours leaves the
entry inconsistent or converts it to a running timer. Always prefer
--start HH:MM --end HH:MM to change duration. --hours is retained for
duration-mode accounts only.

Same shape of trap with --start or --end on their own: if you pass --start
without --end (or vice versa), Harvest recomputes hours from the unchanged
side, which is rarely what you meant. To shift a block, pass BOTH --start
and --end. Only pass one alone if you genuinely want Harvest to grow/shrink
the entry by holding the other side fixed.

Usage:
  python harvest_patch.py ENTRY_ID [--start HH:MM] [--end HH:MM]
                                   [--notes '...'] [--hours N]
                                   [--project-id N] [--task-id N]
                                   [--date YYYY-MM-DD] [--confirm]

At least one field flag must be provided.

**`--confirm` is the confirmation gate**, and is not a field: without it nothing
is written, and the script prints the entry id and the exact body it would have
sent, then exits 0. It may be typed before or after the entry id, as in
`harvest_post.py` — the gate, the preview and the `OK` / `ERR` contract are one
implementation in `harvest_write.py`, shared by both. The gate matters more here
than on a create: a patch overwrites a line that has already been reviewed and
may already have been invoiced, and Harvest has no undo. See `harvest_write.py`
for why the gate lives in the invocation rather than only in SKILL.md's prose.

Harvest recomputes an entry's duration from its two clock times on a patch exactly as it
does on a create, so a patch can arrive at the entry `harvest_post.py` refuses — one worked
straight through the autumn change, billed short by the span that happened twice. This
needs `TIMESHEET_TIMEZONE` to know when that is, and it reads the entry to know what the
patch would leave behind: see `refuse_a_result_that_straddles_the_change()` below. That
read happens on the preview too — what must not be applied must not be offered — so
previewing a change to a time or a date now needs the provider to answer.

Use SINGLE quotes around --notes values to avoid shell $variable interpolation
mangling money references and other dollar-prefixed substrings.

Success: prints `OK <entry_id>` and exits 0.
Preview: prints `WOULD PATCH <entry_id> <body>` and exits 0 — nothing changed.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import datetime as dt
import sys

import aw_client
import harvest_client
import harvest_post
import harvest_write
from harvest_client import use_utf8

FLAGS = {
    "--start": ("started_time", str),
    "--end": ("ended_time", str),
    "--notes": ("notes", str),
    "--hours": ("hours", float),  # footgun on start/end-time accounts — see module docstring
    "--project-id": ("project_id", int),
    "--task-id": ("task_id", int),
    "--date": ("spent_date", str),
}

USAGE = (
    "Usage: harvest_patch.py ENTRY_ID "
    "[--start HH:MM] [--end HH:MM] [--notes '...'] "
    f"[--hours N] [--project-id N] [--task-id N] [--date YYYY-MM-DD] "
    f"[{harvest_write.CONFIRM_FLAG}]\n"
    f"Without {harvest_write.CONFIRM_FLAG} the change is previewed, not applied."
)


def parse_args(argv: list[str]) -> tuple[str, dict, bool]:
    # `take_gate` says why it runs before the entry id is read. The gate is not a field, so
    # it is exempt from the repeated-flag guard below: a repeated value flag silently
    # last-wins, a repeated boolean says the same thing twice.
    args, confirmed = harvest_write.take_gate(argv[1:])
    if not args:
        sys.exit(USAGE)
    entry_id = args[0]
    body: dict = {}
    i = 1
    while i < len(args):
        flag = args[i]
        if flag not in FLAGS:
            sys.exit(f"Unknown flag: {flag}\n{USAGE}")
        if i + 1 >= len(args):
            sys.exit(f"Missing value for {flag}")
        key, caster = FLAGS[flag]
        if key in body:
            # Last-wins would send the second value and exit 0, so the caller believes
            # both landed. A repeated flag is never deliberate — it is a command
            # assembled twice — and every other guard here blocks before the request.
            sys.exit(f"{flag} given more than once; pass it once with the final value")
        raw = args[i + 1]
        try:
            body[key] = caster(raw)
        except ValueError:
            harvest_write.err(f"{flag} expects a {caster.__name__}, got {raw!r}")
        i += 2
    if not body:
        sys.exit("Provide at least one field to update.")
    return entry_id, body, confirmed


def current_entry(entry_id: str) -> dict:
    """The entry as Harvest holds it now — the only read this script makes.

    A patch carries only what it changes, so what the change *results in* is the body laid
    over this. `refuse_a_result_that_straddles_the_change()` decides whether the question
    is worth a request before asking one. A failure here is the same `ERR <status>` line a
    failed write gives: a wrong entry id now fails on the read rather than on the write,
    and the contract must not depend on which.
    """
    try:
        return harvest_client.request("GET", f"/time_entries/{entry_id}")
    except RuntimeError as e:
        harvest_write.err(str(e))


def refuse_a_result_that_straddles_the_change(entry_id: str, body: dict) -> None:
    """Refuse a patch whose *result* runs straight through the autumn change.

    `harvest_post.py`'s `refusal_for_a_straddled_change()` says why such an entry cannot be
    posted, and prints the same message here: Harvest bills the difference between the two
    clock times, so an entry worked through the change is short by the span that happened
    twice, and nothing raises. One message with one owner — `references/self-development.md`
    § "Rules with more than one copy" registers it as that function's, and its arithmetic
    has already been wrong in prose once.

    Three things make this more than that one call, and each is a decision:

    - **A patch carries only what it changes**, so `--start` alone, `--end` alone and
      `--date` alone are each a whole straddling entry once laid over the one already
      there. The guard is on the result, and reading the rest of it costs a GET. Not paid
      for where nothing in the body could move a clock, where a `--date` names a day with
      no repeated span, or where the body already says all three.
    - **`--hours` states a duration the clock cannot**, which is the only way to correct
      such an entry on a duration-mode account. It is not refused, and it ends the
      question before the read — but only where it is the whole answer. Passed *with*
      times it settles nothing: Harvest recomputes hours from `started_time` /
      `ended_time` whenever they are there, so a body carrying both would land the
      straddle with a duration in it that changed nothing. See the module docstring for
      what `--hours` alone does to a start/end-time account, which is the usual one.
    - **The result may hold no clock interval at all.** A duration-mode entry comes back
      with `started_time` null, and the guard refuses only what it can read: inventing an
      interval would block the accounts `--hours` exists for.

    Like every guard here it runs before the gate is consulted. The preview is what the
    user says yes to, and its own last line says to re-run with the flag, so a change that
    must not be applied must not be offered either.
    """
    if "hours" in body and not {"started_time", "ended_time"} & body.keys():
        return
    if not {"started_time", "ended_time", "spent_date"} & body.keys():
        return

    # Last of the checks and the only one that reads configuration, as on the create,
    # so that an argument this script can answer for itself is answered as an argument
    # rather than as a missing setting. No offset flag is offered because this script has
    # none — see `resolve_zone`. What it can answer for itself is narrow: a one-sided time
    # is not read until below, and reaches Harvest's own 422 if it is not a time at all.
    zone = aw_client.resolve_zone(None, offers_offset_flag=False)
    # Already parsed and normalised by `main()`, which is why this one is not guarded.
    dated = body.get("spent_date")
    if dated and harvest_post.repeated_span(dt.date.fromisoformat(dated), zone) is None:
        return

    fields = ("spent_date", "started_time", "ended_time")
    result = {k: body[k] for k in fields if k in body}
    if len(result) < len(fields):
        result = {**current_entry(entry_id), **result}
    if not all(result.get(k) for k in fields):
        return

    try:
        spent = dt.date.fromisoformat(result["spent_date"])
        start_min = harvest_client.parse_time_to_minutes(result["started_time"])
        end_min = harvest_client.parse_time_to_minutes(result["ended_time"])
    except ValueError:
        # Whatever the entry holds, this script did not put it there and cannot read it.
        # Refusing on that would block a patch over a shape Harvest accepted, so the
        # guard stands down: it refuses what it can measure, and nothing else.
        return

    refusal = harvest_post.refusal_for_a_straddled_change(spent, start_min, end_min, zone)
    if refusal:
        print(refusal, file=sys.stderr)
        sys.exit(1)


def main() -> None:
    use_utf8()
    entry_id, body, confirmed = parse_args(sys.argv)

    # The guard runs before the gate is consulted, so an unconfirmed reversed range fails
    # here and is never previewed. Only when both sides are given: one alone is Harvest
    # recomputing against the unchanged side, which the docstring warns about and allows.
    if "started_time" in body and "ended_time" in body:
        harvest_write.ordered_minutes(body["started_time"], body["ended_time"],
                                      "--start", "--end")

    if "spent_date" in body:
        try:
            spent = dt.date.fromisoformat(body["spent_date"])
        except ValueError:
            # Read rather than passed through because the guard below needs the date to
            # know whether the clocks changed on it. Harvest answers a malformed one with
            # a 422 and its own wording; saying so here costs a round trip less.
            harvest_write.err(f"--date must be YYYY-MM-DD, got {body['spent_date']!r}.")
        # The parsed date, not the string it came from, for the reason `harvest_post.py`
        # spells out at its own body: `date.fromisoformat` widened on 3.11, so on a new
        # enough interpreter the check above admits spellings its message says are not
        # allowed. Sending what was parsed makes the wire body the same on 3.10.
        body["spent_date"] = spent.isoformat()

    refuse_a_result_that_straddles_the_change(entry_id, body)

    harvest_write.perform(harvest_write.update(entry_id, body), confirmed)


if __name__ == "__main__":
    main()
