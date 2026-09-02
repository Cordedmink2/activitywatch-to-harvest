"""Guards on the `reconcile` skill — the month-end sweep for days never billed.

Three things about this skill are load-bearing and none of them are visible in a run that
looks fine.

**It must not bill.** Reconciliation reads a month and proposes a worklist; the writing is
the `daily` skill's, behind the confirmation gate that skill carries. A reconcile run that
posts is a run that bills a client off evidence nobody reviewed, and it would look like a
helpful shortcut right up to the invoice.

**The subtraction has to come first.** Dropping the already-billed days before anything is
dispatched is what makes the shape affordable — two to five investigations instead of
twenty-two. Reversed, it still produces the right answer, at ten times the cost, which is
the kind of regression a green suite never notices.

**It runs the `daily` skill's scripts**, which sit in a sibling directory whose name
differs between a plugin install and the shared export. A wrong prefix fails as "file not
found", which reads like a broken install rather than a wrong path.

The assertions are on the shape of the walkthrough rather than its prose, and each is
pinned to something that lives somewhere else in the tree — the scripts the skill names,
the glossary's own table — so an edit over there is what fails here.
"""

import re

import pytest

import shipped
from shipped import CONTEXT_MD, QUOTED, SKILLS, table_cells

RECONCILE = SKILLS / "reconcile"
RECONCILE_MD = RECONCILE / "SKILL.md"
DAILY_SCRIPTS = SKILLS / "daily" / "scripts"


def skill_text() -> str:
    """This skill's own `SKILL.md`."""
    return shipped.skill_md_text(RECONCILE)


def shipped_text() -> str:
    """SKILL.md plus every reference, joined — the whole of what a run can read.

    The ticket defers the reporting and month-close material to later references; which
    file a given sentence ends up in is an editorial decision that should stay free to
    change.
    """
    return shipped.shipped_text(RECONCILE)


def headings() -> list[str]:
    return re.findall(r"^## (.+)$", skill_text(), re.M)


def frontmatter() -> dict[str, str]:
    """This skill's declared frontmatter, {} when the skill is absent."""
    return shipped.frontmatter(skill_text())


def test_the_reconcile_skill_ships():
    assert RECONCILE_MD.is_file(), "there is no reconcile skill"


def test_a_model_cannot_start_a_month_sweep_on_its_own():
    """The same frontmatter field the billing skill carries, for a related reason: this one
    fans a month out across subagents, so an unprompted run is a bill the user never asked
    for in tokens rather than in dollars."""
    assert frontmatter().get("disable-model-invocation") == "true"


# --- it reads and proposes; it does not bill -------------------------------------------

# Named as bare tokens rather than whole commands: the interpreter is whatever the machine
# resolved it to, so matching a command line would let the same instruction through under
# another spelling.
WRITE_TOKENS = ("harvest_post", "harvest_patch", "--confirm", "WOULD POST", "WOULD PATCH")


@pytest.mark.parametrize("token", WRITE_TOKENS)
def test_nothing_in_it_reaches_a_script_that_writes_to_the_provider(token):
    """Not even to forbid it. A prohibition that spells the command is a command in the
    context window, and the honest instruction is shorter anyway: nothing here writes, and
    billing is the `daily` skill's, behind its confirmation gate."""
    assert token not in shipped_text(), (
        f"the reconcile skill names {token!r}. Reconciliation reads a month and proposes a "
        "worklist — a day it finds is handed to the `daily` skill, which owns the write and "
        "the gate in front of it.")


def test_it_hands_a_gap_day_to_the_skill_that_owns_billing():
    """The other half of the same rule. A worklist that names days and no next action ends
    with the user re-deriving the route to billing them."""
    assert "/billables:daily" in shipped_text(), (
        "the worklist never names the skill that bills a day it found")


# --- the shape that makes it cheap ------------------------------------------------------

def test_the_days_already_billed_are_dropped_before_anything_is_dispatched():
    """Asserted as an ordering over sections, the way the run actually happens.

    A month holds twenty-two working days and two to five gaps. Subtracting first is what
    makes the investigation proportional to the gaps rather than to the month — and the
    reversed order returns the same worklist, so nothing but this notices.
    """
    found = headings()
    billed = next((i for i, h in enumerate(found)
                   if re.search(r"already billed", h, re.I)), None)
    dispatch = next((i for i, h in enumerate(found)
                     if re.search(r"subagent|dispatch", h, re.I)), None)
    assert billed is not None, f"no section that drops the billed days: {found}"
    assert dispatch is not None, f"no section that dispatches the investigation: {found}"
    assert billed < dispatch, (
        "the investigation is dispatched before the billed days are dropped, which "
        "investigates the whole month to find the two days that needed it")


# Resolving the `daily` sibling on either install shape is guarded in `test_install_shapes.py`.


def test_no_command_leaves_a_script_path_to_resolve_against_the_workspace():
    """`python scripts/afk_blocks.py` is the spelling the `daily` skill defines as relative
    to *its own folder*, and the session's working directory is the workspace, where those
    scripts are not.

    It is a live defect here rather than a hypothetical: the brief handed to a per-day
    subagent is all that subagent gets, so a bare path in it is a missing-file error on
    every gap day, and a worklist that comes back empty for what looks like a broken
    install. The resolved form — `python "<daily>/scripts/…"` — is what has to travel.
    """
    bare = re.findall(r"^.*[\w.\-]+\s+scripts/[A-Za-z0-9_]+\.py.*$", shipped_text(), re.M)
    unresolved = [ln.strip() for ln in bare if not re.search(r'["<]\s*[^"\n]*scripts/', ln)]
    assert not unresolved, (
        "a command names a script by a path that resolves against the workspace:\n  "
        + "\n  ".join(unresolved))


def test_the_screenshot_index_is_read_from_the_configured_directory():
    """The literal `~/Pictures/WorkScreenshots` is the default, not the path.

    A machine with `TIMESHEET_SCREENSHOTS_DIR` set has an empty folder at the literal one,
    and an empty index is not an error — it is a month in which nothing looks worked. The
    sweep would report one dead capture task over a healthy install and investigate none of
    the real gaps.
    """
    blocks = re.findall(r"```[a-z]*\n(.*?)```", shipped_text(), re.S)
    literal = [b.strip() for b in blocks if "Pictures" in b]
    assert not literal, f"a command hardcodes the default screenshot path: {literal}"
    assert "TIMESHEET_SCREENSHOTS_DIR" in shipped_text(), (
        "the skill never names the setting the screenshot directory actually comes from")


def test_the_short_day_floor_is_a_preference_the_user_can_set():
    """Pinned to the workspace template, which is the file a user edits.

    "Billed short" is a judgement about someone's working day, so a number shipped in a
    skill is one user's habits imposed on everyone. The skill may name a default; what it
    may not do is be the only place the number exists.
    """
    template = (SKILLS / "daily" / "references" / "context.md.example").read_text(
        encoding="utf-8")
    assert re.search(r"Short-day floor", template), (
        "the workspace template offers no way to set the floor the sweep triages on")
    assert re.search(r"short-day floor", shipped_text(), re.I), (
        "the skill never names the floor it triages on")


def test_today_is_not_swept_as_a_gap():
    """A day still being worked is not a day billed short, and the `daily` skill says so in
    as many words ("Today is always 'in progress' on a no-date run"). A sweep that puts
    today in the table sends the user to bill a day that is not over."""
    assert re.search(r"today is in progress|today — in progress|in progress",
                     shipped_text(), re.I), (
        "nothing in the skill says today is in progress rather than unbilled")


def test_every_script_it_names_is_one_the_sibling_skill_actually_ships():
    """Pinned across the skill boundary, which is the only place this can go stale: the
    scripts belong to `daily` and nothing in that skill's own tests knows this one reads
    them. A renamed script leaves an instruction that fails as a missing file."""
    ships = {p.name for p in DAILY_SCRIPTS.iterdir() if p.is_file()}
    named = set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", shipped_text()))
    missing = sorted(named - ships)
    assert named, "the skill names no script at all — it has nothing to investigate a day with"
    assert not missing, f"named but not shipped by the `daily` skill: {missing}"


# --- it speaks the glossary -------------------------------------------------------------

def words_to_avoid() -> list[str]:
    """The quoted phrases in the left column of `CONTEXT.md` § "Words to avoid".

    Only the multi-word ones. The single-word entries — `category`, `segment`, `slot`,
    `ticket` — are habits the glossary itself carves exceptions into ("the activity
    source's own `category` keeps that name"; "ticket" is fine where the user's backend
    calls it one), so a bare match on those would fail a document that is using them
    correctly. The phrases are unambiguous.

    Read with the same table parser the work-kind checks use, keyed on the header row: the
    two documents pin each other through these tables, and a parser that quietly returned
    nothing would leave whichever check depends on it asserting over an empty list.
    """
    found = [phrase for phrase in
             table_cells(CONTEXT_MD.read_text(encoding="utf-8"),
                         "| Don't write | Write |", 0, QUOTED)
             if " " in phrase]
    assert found, "the glossary's avoid-list parsed to nothing — the check has nothing to read"
    return found


def test_it_uses_the_glossarys_terms():
    """The vocabulary is what keeps a second provider an adapter rather than a rewrite, and
    a new skill is where drift gets in — it is written against one account's habits by
    whoever happens to be looking at that account that week.

    This is the denylist half only: it says what the skill stopped saying, not that what it
    says now is right. The distinction below is the positive half.
    """
    text = shipped_text()
    offenders = [phrase for phrase in words_to_avoid() if phrase.lower() in text.lower()]
    assert not offenders, (
        f"the reconcile skill uses words CONTEXT.md replaces: {offenders}.\n"
        "The glossary's table gives the term to use instead.")


# A block is proposed and local; an entry has been billed and is out in the world. The
# inversion is the one this skill is placed to make — it proposes all day, and the thing it
# proposes is never an entry, because an entry is by definition already recorded.
PROPOSED_ENTRY = re.compile(
    r"\b(propos\w+|draft\w*|suggest\w+|creat\w+)\s+(an?\s+|the\s+)?entr(y|ies)\b", re.I)


def test_it_does_not_propose_entries():
    """`CONTEXT.md`: "a block can be redrawn freely, an entry is out in the world". A run
    that thinks it is proposing entries is a run one step from recording one, and the
    sentence reads as harmless right up to that step."""
    found = PROPOSED_ENTRY.findall(shipped_text())
    assert not found, (
        f"the skill proposes entries: {found}. What is proposed is a block; an entry is a "
        "block that has already been recorded with the provider.")
