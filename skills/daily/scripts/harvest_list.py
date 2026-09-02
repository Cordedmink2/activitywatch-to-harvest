"""List Harvest time entries for a date range. One compact line per entry.

Usage:
  python harvest_list.py YYYY-MM-DD [YYYY-MM-DD] [--by-day]

If only one date is given, it's used as both `from` and `to`.

Output (sorted by date, then start time, 24h):
  <id>  <date>  <HH:MM>-<HH:MM>  <h>h  <project_code>  <task[:25]>  <notes[:60]>

`--by-day` collapses that to one row per *date* instead — the month sweep the
`reconcile` skill runs:
  <date>  <Day>  <total>h  <n> entries  <project codes>

Every date in the range gets a row, including the ones holding nothing. A day
with no entries is absent from the per-entry listing, and absent is precisely
what an unbilled day looks like — so reading gaps off that listing means
reasoning about what was never printed. The totals are arithmetic, and
arithmetic done by eye over a hundred rows is wrong quietly.
"""
import datetime as dt
import sys

from harvest_client import parse_time_to_minutes, request, use_utf8


def to_24h(t: str | None) -> str:
    """Normalize Harvest time strings ('8:15am', '12:21pm', '08:15') to 'HH:MM' (24h).

    Returns '--:--' for missing input, or the original string if unparseable.
    Parsing itself is harvest_client.parse_time_to_minutes — one source of truth.
    """
    if not t:
        return "--:--"
    try:
        minutes = parse_time_to_minutes(t)
    except ValueError:
        return t
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def sort_key(entry: dict) -> tuple:
    norm = to_24h(entry.get("started_time"))
    return (entry["spent_date"], norm, entry["id"])


def dates_in(from_date: str, to_date: str) -> list[str]:
    """Every date from `from_date` to `to_date` inclusive, as ISO strings.

    Both bounds are parsed here rather than passed straight to the API: `--by-day` walks
    the range itself, and a bound the API would merely have rejected is a crash once
    something iterates on it. A range that ends before it starts yields nothing at all,
    which reads exactly like a month with no gaps in it — so it is refused rather than
    printed as an empty sweep.
    """
    try:
        start = dt.date.fromisoformat(from_date)
        end = dt.date.fromisoformat(to_date)
    except ValueError as e:
        sys.exit(f"not a date (expected YYYY-MM-DD): {e}")
    if end < start:
        sys.exit(f"the range ends before it starts: {from_date} to {to_date}")
    return [(start + dt.timedelta(days=n)).isoformat()
            for n in range((end - start).days + 1)]


def print_by_day(entries: list[dict], dates: list[str]) -> None:
    """One row per date in `dates`: weekday, billed total, entry count, project codes."""
    totals: dict[str, float] = {d: 0.0 for d in dates}
    counts: dict[str, int] = {d: 0 for d in dates}
    codes: dict[str, list[str]] = {d: [] for d in dates}
    unplaced: list = []
    for e in entries:
        # `.get`, not `[...]`: this mode reads a whole month, and one entry missing the
        # field it is grouped by would take the sweep down before a single row printed.
        d = e.get("spent_date")
        if d not in totals:                  # outside the range, or carrying no date at all
            unplaced.append(e.get("id", "?"))
            continue
        totals[d] += e.get("hours") or 0.0
        counts[d] += 1
        code = (e.get("project") or {}).get("code") or "?"
        if code not in codes[d]:
            codes[d].append(code)
    for d in dates:
        weekday = dt.date.fromisoformat(d).strftime("%a")
        shown = ", ".join(codes[d]) or "-"
        # Padded to the width of "entries" so the codes column stays aligned on the one
        # date that reads "1 entry".
        unit = "entry  " if counts[d] == 1 else "entries"
        print(f"{d}  {weekday}  {totals[d]:>6.2f}h  {counts[d]:>2} {unit}  {shown}")
    if unplaced:
        # On stderr, beside the "(no time entries…)" notice, and never silent: a dropped
        # entry subtracts from a date's total, and a date whose total reads 0.00h is read
        # downstream as a day nobody billed. Being told to bill a day twice is the cost.
        print(f"(skipped {len(unplaced)} with no date inside the range: "
              f"{', '.join(str(i) for i in unplaced)})", file=sys.stderr)


def main() -> None:
    use_utf8()
    args = [a for a in sys.argv[1:] if a != "--by-day"]
    by_day = len(args) < len(sys.argv) - 1
    if len(args) < 1 or len(args) > 2:
        sys.exit("Usage: harvest_list.py YYYY-MM-DD [YYYY-MM-DD] [--by-day]")
    from_date = args[0]
    to_date = args[1] if len(args) == 2 else from_date
    dates = dates_in(from_date, to_date) if by_day else []

    try:
        me = request("GET", "/users/me")
        user_id = me["id"]
    except RuntimeError as e:
        print(f"ERR (users/me) {e}", file=sys.stderr)
        sys.exit(1)

    all_entries: list[dict] = []
    page = 1
    while True:
        try:
            resp = request(
                "GET",
                "/time_entries",
                query={
                    "user_id": user_id,
                    "from": from_date,
                    "to": to_date,
                    "per_page": 100,
                    "page": page,
                },
            )
        except RuntimeError as e:
            print(f"ERR (time_entries page {page}) {e}", file=sys.stderr)
            sys.exit(1)
        all_entries.extend(resp.get("time_entries", []))
        if not resp.get("next_page"):
            break
        page += 1

    if not all_entries:
        # To stderr so stdout stays machine-readable: a day with no entries and a run
        # that silently did nothing look identical otherwise, and the credential check in
        # `references/setup.md` reads exactly this case.
        print(f"(no time entries from {from_date} to {to_date})", file=sys.stderr)
    if by_day:
        # Sorted deliberately not at all: the rows are grouped by date, so order is
        # decided by `dates`. The sort key reads `spent_date` and `id` without a
        # fallback, and this is the mode that reads a whole month — one malformed entry
        # would take down the sweep before a single row printed.
        print_by_day(all_entries, dates)
        return
    all_entries.sort(key=sort_key)
    for e in all_entries:
        eid = e["id"]
        d = e["spent_date"]
        st = to_24h(e.get("started_time"))
        en = to_24h(e.get("ended_time"))
        h = e.get("hours") or 0    # present-but-null is a float format error, not a zero
        code = (e.get("project") or {}).get("code") or "?"
        task = ((e.get("task") or {}).get("name") or "?")[:25]
        notes_raw = (e.get("notes") or "").replace("\n", " ").replace("\r", " ")
        notes = notes_raw if len(notes_raw) <= 60 else notes_raw[:59] + "…"
        print(f"{eid:<10}  {d}  {st}-{en}  {h:>5.2f}h  {code:<11}  {task:<25}  {notes}")


if __name__ == "__main__":
    main()
