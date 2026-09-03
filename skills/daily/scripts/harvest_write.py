"""Writing to the provider: the confirmation gate, the preview, and the `OK` / `ERR` contract.

Not a script. `harvest_post.py` and `harvest_patch.py` each *declare* the write they
would make — `create(body)` or `update(entry_id, body)` — and hand it to `perform()`, and
everything a write has in common happens here, once:

  take_gate(argv)        -> (argv without the gate, whether it was there)
  ordered_minutes(a, b)  -> both clock times as minutes, or `ERR` and exit 1
  perform(write, confirmed)
      unconfirmed: print `WOULD POST <body>` / `WOULD PATCH <id> <body>`, then a line
                   naming the flag, and exit 0 — nothing was *written*. A caller's own
                   guards may have read from the provider first; `harvest_patch.py` does
      confirmed:   send it; print `OK <id>` and exit 0, or `ERR <status> <body>` to
                   stderr and exit 1

**`--confirm` is the confirmation gate.** It is not a field and not a promise in prose:
without it nothing is written. `SKILL.md` Step 8 is where the user's yes is obtained;
`TESTING.md` § "The confirmation gate is in the invocation, not only the prose" is why the
gate is here as well as there — the frontmatter field that stops a model starting the
skill unprompted is honoured by some harnesses and dropped by others.

The gate is taken off the argument list before anything reads it positionally, so it may be
typed anywhere and no field flag left without its value can swallow it. `--notes --confirm`
once set the notes to the literal string `--confirm`, previewed that as though it were
meant, and — because the preview's own last line says to re-run with the flag — wrote it to
a client-facing timesheet on the next attempt.

The preview is the request body itself, rendered from the same `Write` the confirmed run
sends, so what the user approved and what went on the wire cannot come apart. A preview
that described the entry in its own words would be a second description free to drift
from the first, with the user approving the paraphrase.

The gate is a property of writing, not of reaching the provider, so a script that only
reads has no business here and calls `harvest_client.request()` for itself.

This existed twice — once per write script, with every fix landing twice or not at all —
until #22. It is what ADR-0006 says the provider's command contract should own, and where
that contract's design (#33) will find it.
"""
from __future__ import annotations

import json
import sys
from typing import NamedTuple, NoReturn

from harvest_client import parse_time_to_minutes, request

CONFIRM_FLAG = "--confirm"


class Write(NamedTuple):
    """One write a script would make, declared before anyone decides whether it happens.

    `method` doubles as the verb the preview prints (`WOULD POST`, `WOULD PATCH`).
    `target` is the entry id an update names in its preview, because the body alone says
    what would change and not where; a create has no id yet. `preview_footer` is the
    second preview line — what did not happen, and the flag that would make it happen.
    """
    method: str
    path: str
    body: dict
    target: str | None
    preview_footer: str


def create(body: dict) -> Write:
    """A new entry: `POST /time_entries`."""
    return Write("POST", "/time_entries", body, None,
                 f"Nothing was posted. Re-run with {CONFIRM_FLAG} to create this entry.")


def update(entry_id: str, body: dict) -> Write:
    """Changes to an existing entry: `PATCH /time_entries/<id>`, only the fields in `body`."""
    return Write("PATCH", f"/time_entries/{entry_id}", body, entry_id,
                 f"Nothing was changed. Re-run with {CONFIRM_FLAG} to apply it.")


def take_gate(argv: list[str]) -> tuple[list[str], bool]:
    """`argv` with the gate removed wherever it appears, and whether it was there.

    Call it before anything is read positionally. Removing the flag *first* is what stops
    a field flag left without its value from consuming it, and lets the flag be typed
    before or after everything else. A note spelled exactly `--confirm` is eaten too — and
    the argument count then falls short, which is a usage error rather than a silent post.
    The gate is a boolean, so a repeated one says the same thing twice and is not an error.
    """
    rest = [a for a in argv if a != CONFIRM_FLAG]
    return rest, len(rest) != len(argv)


def err(message: str) -> NoReturn:
    """The failure contract: one `ERR …` line on stderr, exit 1, never a traceback.

    A model reads these scripts' output, and a traceback reads to it as "the tool is
    broken" — which sends it debugging the script instead of fixing its own argument.
    """
    print(f"ERR {message}", file=sys.stderr)
    sys.exit(1)


def ordered_minutes(started: str, ended: str,
                    start_name: str = "start", end_name: str = "end") -> tuple[int, int]:
    """Both clock times as minutes since midnight, refusing a range that does not run forward.

    Harvest silently stores `10:00`-`09:00` as a 23-hour entry and a zero-length one as
    0h, so a typo that gets past this is a wrong line on a client invoice, with nothing
    on the provider's side to refuse it. `start_name` / `end_name` are how the caller's own arguments
    are spelled — positionals for a create, `--start` / `--end` for an update — so the
    message names what the user typed.
    """
    try:
        start_min = parse_time_to_minutes(started)
        end_min = parse_time_to_minutes(ended)
    except ValueError as e:
        err(str(e))
    if end_min <= start_min:
        err(f"{start_name} ({started}) must be before {end_name} ({ended}). "
            "Harvest otherwise silently stores reversed times as 23h entries "
            "and zero-duration as 0h — the script blocks both.")
    return start_min, end_min


def preview_line(write: Write) -> str:
    """`WOULD POST <body>` or `WOULD PATCH <id> <body>`: the body itself, not a rendering."""
    head = f"WOULD {write.method}" + (f" {write.target}" if write.target else "")
    return f"{head} {json.dumps(write.body, ensure_ascii=False)}"


def perform(write: Write, confirmed: bool) -> None:
    """Preview the write, or make it — the two outcomes a write has.

    Every guard belongs *before* this call, so an unconfirmed bad command fails on the spot:
    previewing an unpostable entry would invite a re-run with the flag, and the guard would
    then fire on the second attempt with the user having already read a preview of it.
    """
    if not confirmed:
        # A missing flag is the normal case, not a failure: exit 0, and a preview that
        # answers "what would this post?" better than any error could. It does not borrow
        # the `OK <id>` shape, which would have a run record an id for an entry nobody made.
        print(preview_line(write))
        print(write.preview_footer)
        return
    try:
        resp = request(write.method, write.path, body=write.body)
    except RuntimeError as e:
        err(str(e))
    print(f"OK {resp['id']}")
