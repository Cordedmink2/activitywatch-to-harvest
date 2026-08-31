# Billing a block to brand-new client work (no project yet)

Rare path: a block belongs to new work the timesheet provider has no project for. The user creates a work item in their backend (e.g. a Dataverse Case) that syncs to the provider as a new project (`project.code` == the work-item id).

## Creating the case

Use the tested helper rather than hand-rolling a Web API call:

```
python "<workspace>/scripts/create_incident.py" --customer "<client>" --title "<title>"
```

(dry run — confirm the resolved client + title, then re-run with `--yes`).

- **`create_incident.py` / `read_incidents.py` are NOT shipped in this skill** — they live in the user's Dataverse workspace `scripts/` (they auth via that workspace's `auth.py` + `.env`), so `<workspace>` above is `TIMESHEET_WORKSPACE`, not the skill folder every other `python scripts/…` command resolves against. If they're missing there, ask the user to sync them before offering this path.
- **Dataverse auth may not work headless.** On Windows the `dataverse` CLI keeps its refresh token in the WAM broker and the cached RT can't be silently redeemed by the Python scripts. When a run prints a device-code URL, it needs an interactive login — **ask the user to run that one command in their own terminal** and complete the sign-in once; then take the printed work-item number and do the billing yourself (posting to the provider is always headless). Do NOT loop trying to make headless silent auth work — it's a dead end on this setup, and a background run just hangs on the device code.
- **Don't pipe those runs through `head`/`grep`.** The filter buffers its own stdout, so the device-code prompt never reaches the terminal and the run reads as a silent hang. Redirect to a file, or use `grep --line-buffered`. (Observed 2026-08-21.)
- Confirm the resolved customer + title before the case is created. The **customer account determines the work-item prefix**, so you only supply client + title and the CRM assigns the number.
- For ad-hoc work-item lookups: `python "<workspace>/scripts/read_incidents.py" --customer "<client>"` (or `--ticket <code>` / `--search <text>`).

Full mechanism (auth, replica lag) is in `references/catalog-refresh.md`.

## After creating

**Don't put the same work-item reference in both the case title and `--ponumber`.** The sync appends the PO value to the project name: a case titled `… (US1240, US1242)` created with `--ponumber 'US1240, US1242'` synced as `… (US1240, US1242) US1240, US1242`. The project name is client-facing, so put the reference in one of the two, not both. Also observed on that case: the synced project came back `hourly_rate: null` with `use_default_rates: true`, so `--rate` sets the Dataverse case field and whether it reaches invoicing was not verified. (ACM2252S, 2026-08-24.)

**Post the other blocks now**, then use `refresh_catalogs.wait_for_project(<code>)` to poll for the new project (its catalog entry lags a few minutes and a single refresh isn't reliable), and bill the deferred block once it surfaces.
