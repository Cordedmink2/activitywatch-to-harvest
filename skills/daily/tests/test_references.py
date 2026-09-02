"""Guards on the skill's own documentation.

SKILL.md tells the model that `python scripts/…` resolves inside the skill
folder. Any command written that way therefore has to name a script the skill
actually ships — otherwise the model runs a path that doesn't exist and reports
a missing file instead of taking the documented route.
"""

import ast
import os
import re

import pytest

from support import bundled_script_names, bundled_scripts

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(SKILL, "scripts")

# `python scripts/foo.py`, the shape SKILL.md defines as skill-relative.
SKILL_RELATIVE = re.compile(r"python\s+scripts/([A-Za-z0-9_]+\.py)")


def docs():
    yield os.path.join(SKILL, "SKILL.md")
    refs = os.path.join(SKILL, "references")
    for name in sorted(os.listdir(refs)):
        if name.endswith(".md"):
            yield os.path.join(refs, name)


def test_every_skill_relative_command_names_a_shipped_script():
    shipped = set(os.listdir(SCRIPTS))
    missing = []
    for path in docs():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for lineno, line in enumerate(text.splitlines(), 1):
            for script in SKILL_RELATIVE.findall(line):
                if script not in shipped:
                    missing.append(f"{os.path.basename(path)}:{lineno} -> scripts/{script}")
    assert not missing, (
        "documented as `python scripts/…` (skill-relative) but not shipped in the skill; "
        "qualify the path if it lives in the user's workspace:\n  " + "\n  ".join(missing)
    )


# `[--confirm]` in a list of a script's optional flags is documentation; a bare `--confirm`
# on a command line is a template someone will copy.
OPTIONAL = re.compile(r"\[[^\]]*\]")
# The interpreter is whatever the machine resolved it to — see TESTING.md § "Interpreter is
# resolved, not literal", where `python` was the Windows Store stub and the answer was `py`
# in that user's `.context.md`. Matching the literal word would let the same ready-typed
# command through under any other spelling, so the interpreter is a token here, not a name.
WRITE_COMMAND = re.compile(r"\b[\w.\-]+\s+scripts/harvest_(post|patch)\.py")


def test_no_documented_command_hands_over_the_confirmation_flag_ready_typed():
    """The write scripts do nothing without `--confirm`, and that gate is only worth
    anything while adding the flag stays a deliberate act.

    A copy-paste command with the flag already in it makes writing the default action of
    the template — so a model that skipped the Step 8 confirmation, which is the case the
    flag exists to catch, posts anyway by pasting what the doc handed it. The instructions
    say to append it after the user's yes; nothing that reads as a command may pre-empt
    that. A bracketed `[--confirm]` among a script's other optional flags is fine.
    """
    offenders = []
    for path in docs():
        with open(path, encoding="utf-8") as fh:
            for lineno, line in enumerate(fh.read().splitlines(), 1):
                match = WRITE_COMMAND.search(line)
                if not match:
                    continue
                # The command runs to the closing backtick of an inline-code span, or to
                # the end of the line inside a fenced block. Prose after it — which is
                # where the instruction to append the flag belongs — is not the command.
                command = line[match.start():].split("`")[0]
                if "--confirm" in OPTIONAL.sub("", command):
                    offenders.append(f"{os.path.basename(path)}:{lineno}: {command.strip()}")
    assert not offenders, (
        "a documented command hands over `--confirm` ready-typed, which makes posting the "
        "default action of a copied template; append it in the surrounding prose instead, "
        "or write it as an optional `[--confirm]`:\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------------------
# The "Files in this skill" inventory against the flags the scripts actually parse
#
# The inventory is the only place a run is told which flags exist. `TESTING.md` §"The
# 'Files in this skill' list is hand-maintained and had drifted" records it losing whole
# scripts once; it had since lost flags as well. Hand-maintained lists drift, so the fix is
# not to correct the entries but to compare them against the source on every run.
# --------------------------------------------------------------------------------------

INVENTORY_HEADING = "## Files in this skill"

# A flag as it is written in either place. Case is allowed through rather than filtered
# out — `pac` takes a `--xmlFile`, and a camelCase flag added to a script one day should be
# caught by the rule below that excludes another program's argv, not missed by this regex.
# An underscore for the same reason, and because leaving it out is worse than a plain miss:
# `--dry_run` would be invisible on the parsed side and read as `--dry` on the documented
# one, so documenting it correctly would fail the test naming a flag nobody wrote.
FLAG = re.compile(r"--[A-Za-z][A-Za-z0-9_-]*")
FLAG_ONLY = re.compile(FLAG.pattern + r"\Z")

# `- ` opens an entry; the filename runs up to the first em dash, and everything after it
# is prose. Names are taken from the head alone because the prose cross-references other
# scripts: the `aw_client.py` entry names `afk_blocks.py` and `activity_timeline.py` in its
# description, and reading names out of the whole entry would have `aw_client` claim their
# flags. Only the first name carries its `scripts/` prefix in an entry that lists several.
SCRIPT_NAME = re.compile(r"([A-Za-z0-9_]+)\.py")


def _subprocess_argv(tree):
    """Node ids of the string literals that make up an argv handed to another program.

    A `--flag` inside `subprocess.run([...])` is that program's flag, not this script's:
    `refresh_catalogs.py` passes `--name`, `--index`, `--environment` and `--xmlFile` to
    `pac`, and without this they would read as four flags the inventory must list.

    Both spellings of the call are matched, `subprocess.run(...)` and an imported bare
    `run(...)`, but the argv has to be a list or tuple written at the call. Build it into a
    variable first — `cmd = [pac_cmd, ...]` then `subprocess.run(cmd)`, which is how this
    code grows the moment an argument becomes conditional — and the exclusion stops
    reaching it. That failure is loud rather than silent: the flags surface as ones
    `refresh_catalogs.py` supposedly parses and the comparison fails. The assertion message
    says what to do about it, because the obvious response is the wrong one.
    """
    launchers = {"run", "Popen", "call", "check_call", "check_output"}
    skipped = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        func = node.func
        spawns = ((isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                   and func.value.id == "subprocess")
                  or (isinstance(func, ast.Name) and func.id in launchers))
        if not spawns:
            continue
        if isinstance(node.args[0], (ast.List, ast.Tuple)):
            skipped.update(id(element) for element in node.args[0].elts)
    return skipped


def flags_a_script_parses(path) -> set[str]:
    """Every flag `path` accepts, read out of its syntax tree.

    A flag counts when the source contains a string literal that is *exactly* a flag —
    which is the same thing as the script comparing an argument against it. That covers all
    three parsing shapes this skill ships without knowing which is which: argparse's
    `add_argument("--json")`, `harvest_patch.py`'s `FLAGS` table, and the bare
    `a != "--by-day"` filter in `harvest_list.py`. A flag named inside a longer string — a
    usage line, a module docstring — is documentation and does not count, so the literal has
    to match end to end.

    Read as text rather than by importing the module and inspecting its parser, which is
    what this test was first imagined as. Only four of the eleven scripts use argparse, and
    all four build the parser inside `main()`, so an import alone reaches no parser: that
    route means refactoring four scripts to expose a builder and still leaves the three
    hand-rolled parsers uncovered. The trade is that this cannot see a flag assembled at
    runtime; nothing here assembles one, and a test for the inventory being *complete* is
    worth more than one that is exact about a shape nobody uses.

    Two blind spots worth naming, since both look like holes and only one is:

    * `action=argparse.BooleanOptionalAction` on `--full` would make `--no-full` parseable
      with that string appearing nowhere in the source, so the inventory would never be
      asked for it. That is the same class as runtime assembly and a good deal likelier to
      be reached here — negating a boolean flag is the ordinary next edit to one.
    * `-h` / `--help` is accepted by every argparse script and has no literal either. That
      one is a correct omission: nobody wants `--help` in the inventory. A short option
      added beside a long one (`-j` for `--json`) is not held for the same reason, and the
      long form it accompanies still is.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skipped = _subprocess_argv(tree)
    return {node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and FLAG_ONLY.match(node.value) and id(node) not in skipped}


def inventory_entries() -> list[tuple[set[str], set[str]]]:
    """The inventory as `(script stems named, flags written)` per entry.

    Entries naming no script — `SKILL.md`, the references, `tests/` — are dropped, and so
    is the `.ps1` beside `screenshot_capture.py`: its parameters are PowerShell's and are
    not what this compares.
    """
    with open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    heading = [i for i, line in enumerate(lines) if line.strip() == INVENTORY_HEADING]
    assert len(heading) == 1, (
        f"SKILL.md has {len(heading)} sections headed {INVENTORY_HEADING!r}; this test "
        "reads that one to learn which scripts and flags the skill claims to ship. If the "
        "section was retitled, retitle INVENTORY_HEADING with it.")
    section = lines[heading[0] + 1:]
    for offset, line in enumerate(section):
        if line.startswith("## "):
            section = section[:offset]
            break

    entries = []
    fenced = False
    for line in section:
        if line.lstrip().startswith("```"):
            # A fenced example belongs to no entry. Folded in, its contents would be read
            # as that entry's flags — and an example invoking a *different* script would
            # fail the entry above it, naming flags it has nothing to do with.
            fenced = not fenced
        elif fenced:
            continue
        elif line.startswith("- "):
            entries.append(line)
        elif line.strip() and entries:
            entries[-1] += " " + line.strip()      # a wrapped entry is still one entry

    out = []
    for entry in entries:
        head = entry.split(" — ")[0]
        names = set(SCRIPT_NAME.findall(head))
        if names:
            out.append((names, set(FLAG.findall(entry))))
    return out


def entry_for(name: str) -> tuple[set[str], set[str]]:
    # Every match, not the first. An entry whose head fails to end at an em dash swallows
    # its own prose, and the prose cross-references other scripts — so `aw_client.py`'s
    # entry would claim `afk_blocks` and `activity_timeline` as well. Taking the first
    # match hides that: those two have earlier entries of their own, so they keep resolving
    # correctly until someone reorders the list, at which point two scripts are silently
    # checked against the wrong entry. Two entries claiming one script is the defect.
    found = [(names, flags) for names, flags in inventory_entries() if name in names]
    assert found, (
        f"{name}.py ships in scripts/ but has no entry under {INVENTORY_HEADING!r} in "
        "SKILL.md. That list is how a run learns the script exists at all; a script "
        "missing from it is invisible to every run that does not already know it.")
    assert len(found) == 1, (
        f"{name}.py is named by {len(found)} entries under {INVENTORY_HEADING!r}. Usually "
        "this means an entry's filenames do not end at an em dash, so its description — "
        "which names other scripts — is being read as part of its list of files.")
    return found[0]


@pytest.mark.parametrize("name", bundled_script_names())
def test_every_bundled_script_has_an_inventory_entry(name):
    """Derived from `scripts/` rather than from a list, so a twelfth script is covered the
    day it lands. This is the drift `TESTING.md` records: three scripts had been added and
    the inventory named none of them."""
    entry_for(name)


@pytest.mark.parametrize("name", bundled_script_names())
def test_the_inventory_entry_lists_exactly_the_flags_its_scripts_parse(name):
    """A flag in one and not the other fails, in whichever direction.

    Compared per *entry*, not per script, because one entry covers `harvest_post.py`,
    `harvest_patch.py` and `harvest_list.py` together — so the flags it lists are held to be
    the union of what those three parse. A flag written there is known to belong to one of
    them and not which, which is the price of the three sharing a line; nothing is missing
    and nothing is invented, which is what the list is read for.
    """
    names, documented = entry_for(name)
    parsed = set()
    for path in bundled_scripts():
        if path.stem in names:
            parsed |= flags_a_script_parses(path)
    entry = ", ".join(sorted(names))
    assert parsed == documented, (
        f"the SKILL.md entry for {entry} and the flags those scripts parse disagree.\n"
        f"  parsed, not listed: {sorted(parsed - documented) or 'none'}\n"
        f"  listed, not parsed: {sorted(documented - parsed) or 'none'}\n"
        "The inventory is the only place a run is told a flag exists, so a flag you added "
        "wants an entry. But check first that it is this script's flag: one being passed "
        "through to another program belongs to that program, and documenting it here would "
        "tell every run the skill accepts it. `_subprocess_argv` above excludes those, and "
        "only reaches an argv list written at the call — build one into a variable and it "
        "stops reaching, which is a bug in this test rather than a gap in SKILL.md.")
