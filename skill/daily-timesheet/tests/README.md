# The script test suite

Covers `scripts/`. It does **not** cover `SKILL.md`'s behavioural claims — those need a
fresh agent and a control arm, and the method for that lives in `../TESTING.md`.

```powershell
python -m pytest                    # everything except benchmarks (~4s)
python -m pytest --bench -s         # add the timing tripwires, with their numbers
python -m pytest tests/test_scenarios.py --regen-golden    # after an intended change
```

Run it from the skill root. `pytest.ini` there sets `testpaths` and the markers, so a
bare `pytest` does the right thing.

## Read this before writing a test

**Never invoke a script with `subprocess`.**

Two live systems are running on the machine this suite runs on: ActivityWatch on
`localhost:5600`, and Harvest — reachable with the real credentials sitting in `.env` at
the skill root. `conftest.py` has an autouse fixture that repoints both base URLs at an
unroutable address and blanks the credential sources, so an un-stubbed call fails loudly
instead of reading the user's real day or **creating a real time entry on a client's
timesheet**.

A subprocess inherits none of that. It reads the real `.env` and talks to the real API.
Use `support.run_cli(module, args)`, which runs `main()` in this process with a patched
`sys.argv` and captures stdout, stderr and the exit code. One test used to shell out;
it was quietly paging 180 days of real Harvest history on every run.

## The three layers

**Unit** — the pure functions, called directly with hand-built spans. Fastest, and where
a boundary condition belongs.

**Contract** — `test_cli_contracts.py`: what every CLI promises about bad input. A model
reads these scripts' stdout, so a traceback where an `ERR` line belongs sends it
debugging the tool instead of fixing its own argument.

**Scenario** — `scenarios.py` builds whole synthetic days; `test_scenarios.py` runs both
AW scripts over each and diffs the complete output against `golden/`. Each scenario is a
shape the skill has actually had to reason about — a fragmented screen lock, an
end-of-day flicker, two clients in one day, work past midnight.

Scenario tests come in pairs, deliberately. The **golden file** catches change; the
**named assertions** under it state intent. A golden alone would happily record a bug,
so a regeneration that bakes one in still fails the assertions. Keep both.

## Writing a day

`support.Day` takes local `HH:MM` strings and emits the UTC events ActivityWatch would:

```python
d = (day(dt.date(2026, 8, 12))
     .classify("ACME", r"ACME|example-uat")
     .afk("00:00", "08:12")
     .active("08:12", "10:57")
     .locked("10:57", "11:45")                    # lock: sub-threshold AFK fragments
     .thin("11:45", "13:26", active_min=6, idle_min=4)   # supervising an agent
     .window("08:30", "10:57", "Code.exe", "sharepoint-access-sync"))
live_aw(d)
```

Hours past 24 mean the next morning (`"25:30"` is 01:30), so an overnight session needs
no second date. `.locked()` and `.thin()` exist because those two shapes — a lock the
break detector cannot see, and real work whose ratio reads idle — are what the skill gets
wrong, and they should cost one line to write.

## Adding a scenario

Define it in `scenarios.py`, run `pytest --regen-golden`, then **read the generated
golden** and confirm it says what you meant. Commit both. A golden nobody read is a
record of whatever the code happened to do.

## Fakes

`support.aw_server` and `support.harvest_server` are real `http.server` instances on
localhost, not mocks of the code under test — so `main()` gets exercised end to end,
including URL construction, bucket discovery and the unreachable-server path. Both record
every request, which is how the "`harvest_post` must never send a bare `hours` field"
invariant is pinned: assert on the body that was sent, not on what the script printed.

## Marking a defect

Found a real bug while writing a test? Keep the test, mark it
`@pytest.mark.xfail(strict=True, reason="DEFECT: …")`, and leave the script alone until
the fix is a deliberate change with its own red/green. `strict=True` means the xfail
turns red the moment someone fixes it, which is the reminder to delete the marker.
