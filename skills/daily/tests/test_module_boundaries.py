"""Which module in `scripts/` may import which.

Three rules, and each one had been broken by a script that read perfectly well on its own:

1. **A provider script never imports the activity-source client.** `harvest_post.py` and
   `harvest_patch.py` imported `aw_client` for timezone arithmetic — the one import edge
   that ran the wrong way, since an adapter that reaches into the activity source is not
   behind a boundary at all. ADR-0006 records it; #36 removed it.
2. **Nothing imports an entry point.** `harvest_patch.py` imported `harvest_post.py` for a
   message and a helper, which is the shape `harvest_write.py` exists to make unnecessary:
   "not a script … everything a write has in common happens here, once". A module that
   imports a script imports its command line, its usage text and whatever else it grows.
3. **The shared ground stays neutral.** `timezone.py` is imported by both halves, so an
   import of either half from inside it would put the two back in contact through it.

Read out of the syntax tree rather than by importing: an import edge is a property of the
source, and asking the question of the text answers it for a module the suite has already
loaded in some other order.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from support import bundled_script_names, bundled_scripts

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

# The one module both halves are allowed to share, and the one it may reach for itself.
SHARED_ZONE = "timezone"
SEAM = "skill_config"

# What the provider half is: the scripts that talk to the timesheet provider. A prefix
# rather than a list, so a fourth `harvest_*.py` is held to the same rule the day it lands.
PROVIDER_PREFIX = "harvest_"
ACTIVITY_CLIENT = "aw_client"


def script_path(stem: str) -> Path:
    return SCRIPTS / f"{stem}.py"


def imports(path: Path) -> set[str]:
    """The bundled modules `path` imports, however the import is spelled.

    Both `import aw_client` and `from aw_client import get` count, because either one is
    the edge. Everything outside `scripts/` is dropped — the stdlib is not what this is
    about, and naming the modules that are keeps the assertion messages short.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found & set(bundled_script_names())


def names_used(path: Path) -> set[str]:
    """Every identifier `path` actually uses — read as code, not as text.

    A cross-reference in a docstring is not a use: `harvest_client.py` mentions
    `resolve_zone()` in prose to say which absence it shares its wording with, and a text
    search cannot tell that from a call. Both spellings of a use count, the bare
    `resolve_zone(...)` and the qualified `timezone.resolve_zone(...)`.
    """
    used: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            used.update(alias.asname or alias.name for alias in node.names)
    return used


def entry_points() -> set[str]:
    """Every bundled module that is a script — one with a `__main__` guard to run.

    Derived from the guard rather than from a list of names: `harvest_write.py` and
    `timezone.py` are modules that happen to sit in `scripts/`, and the distinction that
    matters is whether a thing is invoked or imported, which the guard is exactly.

    Read as code for the same reason `names_used()` is: `"__main__" in text` would classify
    a module that merely *mentions* the guard in a docstring as a script, and this file's
    own prose is the proof that such a mention is a thing people write.
    """
    return {p.stem for p in bundled_scripts()
            if any(isinstance(node, ast.Name) and node.id == "__name__"
                   for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))))}


def provider_scripts() -> list[Path]:
    return [p for p in bundled_scripts() if p.stem.startswith(PROVIDER_PREFIX)]


@pytest.mark.parametrize("path", provider_scripts(), ids=lambda p: p.stem)
def test_no_provider_module_imports_the_activity_source_client(path):
    """The edge #36 removed. Both halves need the zone arithmetic; neither owns it."""
    assert ACTIVITY_CLIENT not in imports(path), (
        f"{path.name} imports {ACTIVITY_CLIENT} — a provider script reaching into the "
        f"activity-source client. Whatever it wants from there is either the activity "
        f"source's (in which case it does not belong in a write path) or shared, in which "
        f"case it belongs in {SHARED_ZONE}.py, which both halves import.")


@pytest.mark.parametrize("path", bundled_scripts(), ids=lambda p: p.stem)
def test_no_bundled_module_imports_an_entry_point(path):
    """Shared logic lives in a module that is not a command.

    `harvest_write.py` was created for exactly this and says so in its first line. A
    script imported for one function brings its argument parsing and its usage string
    along, and the next thing that is shared lands in whichever of the two happens to
    already import the other.
    """
    reached = imports(path) & (entry_points() - {path.stem})
    assert not reached, (
        f"{path.name} imports {', '.join(sorted(reached))} — a script, for something the "
        f"two have in common. Move what is shared into a module with no command line: "
        f"`harvest_write.py` for the write path, `{SHARED_ZONE}.py` for zone arithmetic.")


def test_the_shared_zone_module_imports_neither_half():
    """`timezone.py` is the ground both halves stand on, so it stands on neither of them.

    The seam is the one exception, and not really one: `resolve_zone()` reads a configured
    setting, and every read in this skill goes through `skill_config` — which is below both
    halves as well.
    """
    assert script_path(SHARED_ZONE).is_file(), (
        f"there is no scripts/{SHARED_ZONE}.py. The zone arithmetic both halves need lives "
        "there; without it one half owns it and the other imports that half.")
    assert imports(script_path(SHARED_ZONE)) <= {SEAM}, (
        f"{SHARED_ZONE}.py imports {sorted(imports(script_path(SHARED_ZONE)) - {SEAM})} — the "
        "shared module reaching into one of the halves it is shared by, which puts the two "
        "back in contact through it.")


def test_every_module_that_names_the_zone_resolver_imports_the_shared_one():
    """The other half of rule 1: both sides really do read the zone from one place.

    Derived from the name rather than from a list of the four scripts that resolve a zone,
    so a fifth is covered the day it is written. A module that calls `resolve_zone` and
    imports nothing that defines it either has its own copy — the duplication this module
    exists to prevent — or names a function it cannot call.
    """
    offenders = [path.name for path in bundled_scripts()
                 if path.stem != SHARED_ZONE
                 and "resolve_zone" in names_used(path)
                 and SHARED_ZONE not in imports(path)]
    assert not offenders, (
        "these call resolve_zone() without importing the module that defines it:\n  "
        + "\n  ".join(offenders))
