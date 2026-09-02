"""Guards on the route out of a hand-installed copy.

Before the plugin there was one way in: clone the repo, run `install_skill.ps1`, and get an
unprefixed `daily-timesheet` directory under the harness's own skills folder. That path is
gone. The people who took it are still on it, and the instruction they were given — update
by re-running the installer — now regenerates the shared-directory export and leaves their
copy exactly where it was, stale and still activating.

So the migration is not a paragraph that would be nice to have; it is the only thing
standing between an existing user and a copy that quietly stops being current. What these
tests hold is that it exists, that it is reachable from the heading a stale reader looks
under, and that every setting the old copy carried is accounted for in it. That last one is
the promise worth a test: a migration that loses somebody's screenshot directory or their
Dataverse profile costs them an afternoon of finding out which.

The prose is not asserted. What a section *says* should stay free to change; what it must
not do is go silent about a key that still exists in someone's `.env`.
"""

import re

import pytest

from shipped import REPO

README = REPO / "README.md"

# Where the retired installer put the skill. Named here rather than guarded against,
# because the migration section is the one document that has to spell it out — it is what
# a reader matches their own machine against.
OLD_INSTALL = ".claude/skills/daily-timesheet"


def readme() -> str:
    return README.read_text(encoding="utf-8")


def updating() -> str:
    """The `## Updating` section, whole. Empty if the heading is gone."""
    text = readme()
    if "\n## Updating" not in text:
        return ""
    return text.split("\n## Updating", 1)[1].split("\n## ", 1)[0]


def migration() -> str:
    """The subsection of `## Updating` covering a hand-installed copy.

    Found by its content rather than its exact wording: it is the `###` block that names
    the old install location. A heading is a phrasing decision; naming the directory
    someone has to recognise on their own machine is not.
    """
    blocks = re.split(r"^### ", updating(), flags=re.M)[1:]
    for block in blocks:
        if OLD_INSTALL in block.replace("\\", "/"):
            return block
    return ""


def test_the_readme_documents_a_migration_path():
    assert migration(), (
        "no subsection of README.md's `## Updating` names "
        f"`~/{OLD_INSTALL}` — an existing user has nothing to follow"
    )


def test_the_migration_lives_under_the_old_update_heading():
    """The instruction being replaced said "update by re-running the installer", under
    `## Updating`. Someone on a stale copy goes looking there, so that is where the
    replacement has to be — a migration filed anywhere else is deleted as far as they are
    concerned."""
    assert "\n## Updating" in readme(), (
        "README.md has no `## Updating` heading, so the old update instruction points "
        "nowhere at all"
    )
    assert migration(), "`## Updating` says nothing about a hand-installed copy"


def test_the_migration_route_is_the_plugin():
    """Not a re-run of the installer, which is what the old instruction said and what now
    regenerates a different artifact entirely."""
    body = migration()
    assert "/plugin install billables" in body, (
        "the migration never says to install the plugin:\n" + body)
    assert "/plugin configure billables" in body, (
        "the migration never says where the settings go now:\n" + body)


def test_the_migration_says_the_users_own_files_survive():
    """The whole question an existing user has. Their clients, colleagues and billing
    conventions are in `Timesheets/.context.md`, and their audit files are beside it —
    none of it inside the skill folder, all of it invisible from there."""
    body = migration()
    assert ".context.md" in body, (
        "the migration never mentions `.context.md`, which is the file an existing user "
        "is most afraid of losing:\n" + body)
    assert "Timesheets" in body, (
        "the migration never mentions the workspace their timesheets live in:\n" + body)


# Every setting the retired copy could be carrying, whatever vintage it is. Which ones came
# from the `.env` is not fixed: the released hand install had five keys and no
# `TIMESHEET_SCREENSHOTS_DIR` — a custom capture directory lived on the scheduled task's
# `-ScreenshotsDir` argument — while later copies read it through the same resolver as the
# rest. The migration has to account for the setting either way, which is why this list is
# of settings rather than of file contents.
#
# The timezone is the one that changes shape rather than moving: an offset is not an IANA
# name, and nothing can convert one to the other without knowing where the user is.
OLD_SETTINGS = [
    "HARVEST_ACCOUNT_ID",
    "HARVEST_API_KEY",
    "TIMESHEET_WORKSPACE",
    "TIMESHEET_SCREENSHOTS_DIR",
    "DATAVERSE_URL",
    "PAC_AUTH_PROFILE",
    "--utc-offset",
]


@pytest.mark.parametrize("setting", OLD_SETTINGS)
def test_the_migration_accounts_for_every_setting_the_old_copy_held(setting):
    """A key left out of the table is a setting the user silently loses, and finds out
    about on the first run that needs it — which for `DATAVERSE_URL` is a catalog refresh
    weeks later, not the migration itself."""
    assert setting in migration(), (
        f"`{setting}` was in the old install and the migration never says where it goes"
    )


def test_the_migration_says_to_remove_the_old_copy():
    """Two copies both activate. Leaving the old one in place is the failure the whole
    ticket is about — someone current on the plugin and still being answered by a skill
    folder from months ago."""
    body = migration().replace("\\", "/")
    assert re.search(r"\bdelete\b|\bremove\b", body, re.I), (
        "the migration never tells the user to delete the old copy, so both keep "
        "activating:\n" + body)
