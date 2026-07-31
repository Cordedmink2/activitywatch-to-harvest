# Billing a block to brand-new client work (no Harvest project yet)

Rare path: a block belongs to new work with no Harvest project. The user creates a backend ticket/case (e.g. a Dataverse Case) that syncs to Harvest as a new project (`project.code` == ticket id).

## Creating the case

Use the tested helper rather than hand-rolling a Web API call:

```
python scripts/create_incident.py --customer "<client>" --title "<title>"
```

(dry run — confirm the resolved client + title, then re-run with `--yes`).

- **`create_incident.py` / `read_incidents.py` are NOT shipped in this skill** — they live in the user's Dataverse workspace `scripts/` (they auth via that workspace's `auth.py` + `.env`). If they're missing there, ask the user to sync them before offering this path.
- **Dataverse auth may not work headless.** On Windows the `dataverse` CLI keeps its refresh token in the WAM broker and the cached RT can't be silently redeemed by the Python scripts. When a run prints a device-code URL, it needs an interactive login — **ask the user to run that one command in their own terminal** and complete the sign-in once; then take the printed ticket number and do the Harvest billing yourself (Harvest posting is always headless). Do NOT loop trying to make headless silent auth work — it's a dead end on this setup, and a background run just hangs on the device code.
- Confirm the resolved customer + title before the case is created. The **customer account determines the ticket prefix** (CON→Connexis, CNM→Cone Marshall, …), so you only supply client + title and the CRM assigns the number.
- For ad-hoc ticket lookups: `python scripts/read_incidents.py --customer "<client>"` (or `--ticket <code>` / `--search <text>`).

Full mechanism (auth, replica lag) is in `references/catalog-refresh.md`.

## After creating

**Post the other blocks now**, then use `refresh_catalogs.wait_for_project(<code>)` to poll for the new project (its catalog entry lags a few minutes and a single refresh isn't reliable), and bill the deferred block once it surfaces.
