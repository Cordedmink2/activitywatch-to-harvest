"""A guard that keeps one provider's vocabulary out of the shipped rules.

The rules used to map a block's activity straight onto the literal task names of one
Harvest account — `Gen - Development/Configuration`, `Gen - Meeting`, and the rest. Any
other user's account names its tasks differently, so those strings were never generic:
they were one workspace's facts shipped as everybody's defaults. The rules now decide a
**work kind** instead, and the user's own `.context.md` maps work kind → the task their
provider actually offers.

Unlike the redacted names in `test_redaction.py`, these strings are not sensitive, so
they are spelled out here. The scan covers the shipped instruction surface of **every**
skill — `SKILL.md`, `references/*.md`, `scripts/*.py` under each of them — because a new
skill is exactly where the drift gets back in: it is written against whichever account
its author happened to be looking at, and the rules that were cleaned up don't govern it.
Test fixtures are deliberately out of scope: the provider adapter's tests have to feed it
the provider's real shapes, and a fake API response is not a rule.

The second test is the positive half. A denylist only says what the rules stopped
saying; it cannot tell whether what they say now is the shared vocabulary. So the work
kinds the rules name are checked against the glossary in `CONTEXT.md`, which is what
makes the glossary load-bearing rather than decorative.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
SKILL = SKILLS / "daily"

# The literal task names of the one account the rules used to be written against.
PROVIDER_TASK_NAMES = (
    "Gen - Development/Configuration",
    "Gen - Development",
    "Gen - Meeting",
    "Gen - Documentation",
    "Gen - Project Management",
    "Gen - Testing",
    "Gen - Investigation",
    "Gen - Issue Resolution",
    "Gen - General Consulting",
    "Meeting - Standup Meetings",
    "No Display",
)

FIX = """
Those are one Harvest account's task names. The shipped rules decide a work kind from
`CONTEXT.md`'s glossary; the provider's own string for it comes from the user's
`.context.md` (see its "Work kinds" table) or from declared plugin configuration.
Name the work kind, not the task.
"""


def shipped_rules():
    """The instruction surface a user reads and follows — not the tests behind it.

    Every shipped skill, discovered rather than listed: a skill added to the plugin and
    left out of this walk would be the one place the old vocabulary could come back.
    """
    for skill in sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()):
        yield skill / "SKILL.md"
        yield from sorted((skill / "references").glob("*.md"))
        yield from sorted((skill / "scripts").glob("*.py"))


def test_no_provider_task_name_appears_in_the_shipped_rules():
    offenders = []
    for path in shipped_rules():
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for name in PROVIDER_TASK_NAMES:
                if name in line:
                    rel = path.relative_to(REPO).as_posix()
                    offenders.append(f"  {rel}:{lineno}: {name}")
                    break
    assert not offenders, "provider task names in the shipped rules:\n" + "\n".join(
        offenders) + "\n" + FIX


# --- the work kinds the rules name are the ones the glossary defines --------------------

CODE = re.compile(r"`([^`]+)`")


def table_cells(text: str, header: str, column: int) -> list[str]:
    """Every backticked cell in one column of the markdown table whose header row is
    `header`. Keyed on the header text rather than a line number so either document can
    be re-ordered without silently emptying the check."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == header:
            break
    else:
        raise AssertionError(f"no table headed {header!r} — the check has nothing to read")
    found = []
    for line in lines[i + 2:]:                       # skip the `|---|---|` separator
        if not line.strip().startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if column < len(cells):
            found += CODE.findall(cells[column])
    assert found, f"the table headed {header!r} parsed to nothing"
    return found


def glossary_work_kinds() -> list[str]:
    return table_cells((REPO / "CONTEXT.md").read_text(encoding="utf-8"),
                       "| Work kind | The block was |", 0)


def test_the_rules_only_name_work_kinds_the_glossary_defines():
    rules = table_cells(
        (SKILL / "references" / "classification-rules.md").read_text(encoding="utf-8"),
        "| Dominant block activity | Work kind |", 1)
    unknown = sorted(set(rules) - set(glossary_work_kinds()))
    assert not unknown, (
        f"the classification rules name work kinds the glossary does not define: {unknown}.\n"
        f"Either use the glossary's term or add the new one to CONTEXT.md — the point of "
        f"the table is that both documents mean the same seven things.")


def test_the_workspace_template_spells_the_work_kinds_exactly_as_the_rules_do():
    """The third copy, and the one that decides a real run.

    A run reads its work kind out of the rubric and looks that string up in the user's
    `.context.md` § "Work kinds". If the template's left column drifts by so much as a
    capital — `Project Management` for `Project management` — every lookup misses, every
    block silently falls through to the default task, and nothing else in this repo
    notices. The two documents the previous test compares would still agree.
    """
    template = table_cells(
        (SKILL / "references" / "context.md.example").read_text(encoding="utf-8"),
        "| Work kind | Your task |", 0)
    assert template == glossary_work_kinds(), (
        "the .context.md template's work kinds have drifted from CONTEXT.md.\n"
        f"  template: {template}\n"
        f"  glossary: {glossary_work_kinds()}\n"
        "A run looks the rubric's string up in this table verbatim, so these have to match "
        "exactly — same spelling, same order, same seven.")


def test_every_work_kind_the_glossary_defines_is_reachable_from_the_rules():
    """The other direction: a glossary term no rule ever produces is vocabulary nobody
    speaks, and the next writer will invent a synonym for it instead."""
    rules = (SKILL / "references" / "classification-rules.md").read_text(encoding="utf-8")
    unused = sorted(kind for kind in glossary_work_kinds() if f"`{kind}`" not in rules)
    assert not unused, f"work kinds defined but never assigned by any rule: {unused}"
