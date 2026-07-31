"""List Harvest time entries for a date range. One compact line per entry.

Usage:
  python harvest_list.py YYYY-MM-DD [YYYY-MM-DD]

If only one date is given, it's used as both `from` and `to`.

Output (sorted by date, then start time, 24h):
  <id>  <date>  <HH:MM>-<HH:MM>  <h>h  <project_code>  <task[:25]>  <notes[:60]>
"""
import os
import sys

from harvest_client import parse_time_to_minutes, request

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


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


def main() -> None:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        sys.exit("Usage: harvest_list.py YYYY-MM-DD [YYYY-MM-DD]")
    from_date = sys.argv[1]
    to_date = sys.argv[2] if len(sys.argv) == 3 else from_date

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

    all_entries.sort(key=sort_key)
    for e in all_entries:
        eid = e["id"]
        d = e["spent_date"]
        st = to_24h(e.get("started_time"))
        en = to_24h(e.get("ended_time"))
        h = e.get("hours", 0)
        code = (e.get("project") or {}).get("code") or "?"
        task = ((e.get("task") or {}).get("name") or "?")[:25]
        notes_raw = (e.get("notes") or "").replace("\n", " ").replace("\r", " ")
        notes = notes_raw if len(notes_raw) <= 60 else notes_raw[:59] + "…"
        print(f"{eid:<10}  {d}  {st}-{en}  {h:>5.2f}h  {code:<11}  {task:<25}  {notes}")


if __name__ == "__main__":
    main()
