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
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
RECONCILE = SKILLS / "reconcile"
RECONCILE_MD = RECONCILE / "SKILL.md"
DAILY_SCRIPTS = SKILLS / "daily" / "scripts"


def skill_text() -> str:
    """Empty when the skill is absent, so that reads as one failed test rather than a
    collection error that takes the rest of this module down with it."""
    return RECONCILE_MD.read_text(encoding="utf-8") if RECONCILE_MD.is_file() else ""


def shipped_text() -> str:
    """SKILL.md plus every reference, joined — the whole of what a run can read.

    The ticket defers the reporting and month-close material to later references; which
    file a given sentence ends up in is an editorial decision that should stay free to
    change.
    """
    parts = [skill_text()]
    parts += [p.read_text(encoding="utf-8") for p in sorted(RECONCILE.rglob("*.md"))
              if p != RECONCILE_MD]
    return "\n".join(parts)


def headings() -> list[str]:
    return re.findall(r"^## (.+)$", skill_text(), re.M)


def frontmatter() -> dict[str, str]:
    text = skill_text()
    if not text.startswith("---"):
        return {}
    head = text.split("---", 2)[1]
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^([A-Za-z][\w-]*):[ \t]*(.*)$", head, re.M)}


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


# The skill runs the `daily` skill's scripts, so it has to resolve a sibling directory.
# Both names are real: a plugin install keeps the directory name, and the shared Agent
# Skills export prefixes it, because that directory is flat.
@pytest.mark.parametrize("sibling", ["daily", "billables-daily"])
def test_it_can_find_its_sibling_skill_on_either_install_shape(sibling):
    assert re.search(rf"(?<![\w-]){re.escape(sibling)}(?![\w-])", shipped_text()), (
        f"the skill never mentions a sibling directory named {sibling}, so one of the two "
        "install shapes cannot resolve the scripts it runs")


def test_every_script_it_names_is_one_the_sibling_skill_actually_ships():
    """Pinned across the skill boundary, which is the only place this can go stale: the
    scripts belong to `daily` and nothing in that skill's own tests knows this one reads
    them. A renamed script leaves an instruction that fails as a missing file."""
    shipped = {p.name for p in DAILY_SCRIPTS.iterdir() if p.is_file()}
    named = set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", shipped_text()))
    missing = sorted(named - shipped)
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
    """
    text = (REPO / "CONTEXT.md").read_text(encoding="utf-8")
    section = text.split("## Words to avoid", 1)[1]
    found = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        found += [q for q in re.findall(r'"([^"]+)"', cells[0]) if " " in q]
    assert found, "the glossary's avoid-list parsed to nothing — the check has nothing to read"
    return found


def test_it_uses_the_glossarys_terms():
    """The vocabulary is what keeps a second provider an adapter rather than a rewrite, and
    a new skill is where drift gets in — it is written against one account's habits by
    whoever happens to be looking at that account that week.

    The distinction this skill leans on hardest is the glossary's load-bearing one: a
    **block** is proposed and local, an **entry** has been billed and is out in the world.
    Reconciliation is entirely about the second, and every synonym below blurs them.
    """
    text = shipped_text()
    offenders = [phrase for phrase in words_to_avoid() if phrase.lower() in text.lower()]
    assert not offenders, (
        f"the reconcile skill uses words CONTEXT.md replaces: {offenders}.\n"
        "The glossary's table gives the term to use instead.")
