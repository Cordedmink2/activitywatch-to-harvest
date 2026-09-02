"""The shipped plugin, as the repo-level suite sees it.

Every module in `tests/` asks the same handful of questions of the artifact this repo
ships: where the repo root is, which directories under `skills/` are skills, what a run of
one of them can read, what a markdown table in `CONTEXT.md` names, which version the
changelog declares. Answered separately in each file those answers drift, and the drift is
silent — `test_distribution.py` and `test_reconcile_skill.py` each grew their own
frontmatter reader, so a correction to one was a correction to one. A helper that stops
finding what it looks for does not raise; it returns nothing, and an assertion over
nothing passes.

Named `shipped` rather than `support` because `skills/daily/tests/` already has a module
called `support` and puts its own directory on `sys.path`. Both suites are collected in a
single pytest run under prepend import mode, so a second `support` would resolve to
whichever of the two was imported first — a collision whose symptom is an unrelated suite
failing on a missing attribute.

Importing this reads no configuration and sets no environment variable. It is paths and
functions only, so nothing about the order the suite imports its modules in can change
what a test sees.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"
CONTEXT_MD = REPO / "CONTEXT.md"
CHANGELOG = REPO / "CHANGELOG.md"


# --------------------------------------------------------------------------------------
# What ships
# --------------------------------------------------------------------------------------

def skill_dirs() -> list[Path]:
    """Every skill directory the plugin ships.

    Discovered rather than listed, because a hand-maintained list leaves the next skill
    added silently unguarded while the suite still reports green.
    """
    return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def skill_md_text(skill: Path) -> str:
    """A skill's `SKILL.md`, or the empty string when the skill is not there.

    Empty rather than an error so a missing skill reads as one failed test rather than a
    collection error that takes the rest of that module's assertions down with it.
    """
    skill_md = skill / "SKILL.md"
    return skill_md.read_text(encoding="utf-8") if skill_md.is_file() else ""


def shipped_text(skill: Path) -> str:
    """`SKILL.md` plus every other markdown file under the skill, joined — the whole of
    what a run of it can read.

    Which file a given sentence ends up in is an editorial decision that should stay free
    to change; that it is somewhere in the skill is the promise. A guard scoped to
    `SKILL.md` alone would go green the moment a sentence moved into a reference.
    """
    skill_md = skill / "SKILL.md"
    parts = [skill_md_text(skill)]
    parts += [p.read_text(encoding="utf-8") for p in sorted(skill.rglob("*.md"))
              if p != skill_md]
    return "\n".join(parts)


# --------------------------------------------------------------------------------------
# Frontmatter
# --------------------------------------------------------------------------------------

def frontmatter(text: str) -> dict[str, str]:
    """The top-level `key: value` pairs of a document's YAML frontmatter, or {} if there
    is none.

    Deliberately not a YAML parser: the fields asserted on here are the flat scalars the
    spec defines, and a dependency-free reader keeps these tests runnable anywhere the
    plugin is.
    """
    if not text.startswith("---"):
        return {}
    head = text.split("---", 2)[1]
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^([A-Za-z][\w-]*):[ \t]*(.*)$", head, re.M)}


def frontmatter_name(skill_md: Path) -> str | None:
    """The `name:` from the YAML frontmatter, or None if there is no frontmatter."""
    return frontmatter(skill_md.read_text(encoding="utf-8")).get("name")


# --------------------------------------------------------------------------------------
# The tables the documents pin each other against
# --------------------------------------------------------------------------------------

# How a document sets a term apart from the prose around it. The glossary and the
# classification rules backtick their work kinds; the "Words to avoid" table quotes its
# phrases. Reading the delimiter rather than the whole cell is what keeps a check pinned
# to the terms and not to whatever explanation shares the cell with them.
BACKTICKED = re.compile(r"`([^`]+)`")
QUOTED = re.compile(r'"([^"]+)"')


def table_cells(text: str, header: str, column: int,
                marker: re.Pattern[str] = BACKTICKED) -> list[str]:
    """Every `marker`-delimited term in one column of the markdown table whose header row
    is `header`. Keyed on the header text rather than a line number so either document can
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
            found += marker.findall(cells[column])
    assert found, f"the table headed {header!r} parsed to nothing"
    return found


# --------------------------------------------------------------------------------------
# The version that shipped
# --------------------------------------------------------------------------------------

def released_version() -> str:
    """The newest released version the changelog declares.

    `## [Unreleased]` sits above the first versioned heading and is skipped, which the
    digit groups do on their own: what the manifest has to agree with, and what an
    installer prints, is a number that shipped. A looser match would return "Unreleased"
    and compare it against a real version for as long as that heading stood.
    """
    match = re.search(r"^## \[(\d+\.\d+\.\d+)\]", CHANGELOG.read_text(encoding="utf-8"), re.M)
    assert match, "no released version heading in CHANGELOG.md"
    return match.group(1)
