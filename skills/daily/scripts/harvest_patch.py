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

Use SINGLE quotes around --notes values to avoid shell $variable interpolation
mangling money references and other dollar-prefixed substrings.

Success: prints `OK <entry_id>` and exits 0.
Preview: prints `WOULD PATCH <entry_id> <body>` and exits 0 — nothing changed.
Failure: prints `ERR <status> <body[:200]>` to stderr and exits 1.
"""
import sys

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


def main() -> None:
    use_utf8()
    entry_id, body, confirmed = parse_args(sys.argv)

    # The guard runs before the gate is consulted, so an unconfirmed reversed range fails
    # here and is never previewed. Only when both sides are given: one alone is Harvest
    # recomputing against the unchanged side, which the docstring warns about and allows.
    if "started_time" in body and "ended_time" in body:
        harvest_write.ordered_minutes(body["started_time"], body["ended_time"],
                                      "--start", "--end")

    harvest_write.perform(harvest_write.update(entry_id, body), confirmed)


if __name__ == "__main__":
    main()
