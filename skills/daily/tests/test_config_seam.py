"""The one seam every script reads its configuration through.

Settings used to arrive from three places with no stated rule about which won: the skill
`.env`, the process environment, and a per-command flag. Each script merged whichever
subset it cared about in its own way — `load_creds()` re-implemented the `.env`/OS-env
walk that `config()` already did, `screenshot_capture` layered `argv[0]` on top by hand,
`harvest_lookup` layered `--mcp-dir` on top a different way. Three readers, three chances
for the rule to drift.

`skill_config` is now the reader, and its module docstring carries the precedence rule;
`references/self-development.md` § "Rules with more than one copy" registers where that
rule is restated. These tests hold the shape: the precedence itself, the error contract a
missing required value has to honour, and the structural guards that stop a second reader
growing back somewhere else in `scripts/`.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import harvest_client as hc            # noqa: E402
import skill_config                    # noqa: E402
from support import SETTING_KEYS, bundled_script_names  # noqa: E402


@pytest.fixture
def isolated(env_file, tmp_path, monkeypatch):
    """`env_file`, plus the other two sources `find_workspace()` consults.

    A test whose precondition is "nothing resolves" has to neutralise every source the
    resolver reads: the walk up from `SKILL_ROOT` found a real workspace when the suite
    ran from one checkout and not from another — `TESTING.md` § "A test's result depended on where the checkout sat". Returns the `.env` path for a
    test to write settings into.
    """
    monkeypatch.setattr(skill_config, "SKILL_ROOT", tmp_path / "skills" / "daily")
    monkeypatch.chdir(tmp_path)
    return env_file


# --------------------------------------------------------------------------------------
# The precedence, in the order the docstring states it
# --------------------------------------------------------------------------------------

def test_a_flag_beats_the_env_file(isolated, monkeypatch):
    """A flag overrides a single run, which is the whole reason the scripts offer them."""
    isolated.write_text("TIMESHEET_WORKSPACE=/from-file\n", encoding="utf-8")
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert skill_config.setting("TIMESHEET_WORKSPACE", flag="/from-flag") == "/from-flag"


def test_the_env_file_beats_the_process_environment(isolated, monkeypatch):
    isolated.write_text("TIMESHEET_WORKSPACE=/from-file\n", encoding="utf-8")
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert skill_config.setting("TIMESHEET_WORKSPACE") == "/from-file"


def test_the_process_environment_beats_the_default(isolated, monkeypatch):
    monkeypatch.setenv("TIMESHEET_WORKSPACE", "/from-os")
    assert skill_config.setting("TIMESHEET_WORKSPACE", default="/fallback") == "/from-os"


def test_the_default_is_the_last_resort(isolated):
    assert skill_config.setting("TIMESHEET_WORKSPACE", default="/fallback") == "/fallback"


def test_an_unset_setting_with_no_default_is_none(isolated):
    """Callers decide whether that is fatal — the seam never invents a value."""
    assert skill_config.setting("DATAVERSE_URL") is None


# --------------------------------------------------------------------------------------
# Blank means unset, at every layer
# --------------------------------------------------------------------------------------

def test_a_blank_flag_does_not_win(isolated):
    """Task Scheduler passes an empty string through when its argument is blank, and a
    blank that wins is worse than no flag at all: it silently discards the configured
    value in favour of nothing."""
    isolated.write_text("TIMESHEET_SCREENSHOTS_DIR=D:\\FromDotEnv\n", encoding="utf-8")
    assert skill_config.setting("TIMESHEET_SCREENSHOTS_DIR", flag="  ") == r"D:\FromDotEnv"


def test_a_blank_env_file_value_does_not_win(isolated, monkeypatch):
    """`DATAVERSE_URL=` left in a copied `.env.example` is a user saying "not this",
    not a user configuring an empty org."""
    isolated.write_text("DATAVERSE_URL=   \n", encoding="utf-8")
    monkeypatch.setenv("DATAVERSE_URL", "https://example.invalid/")
    assert skill_config.setting("DATAVERSE_URL") == "https://example.invalid/"


# --------------------------------------------------------------------------------------
# find_workspace(): the one derived setting, resolved the same way for reader and writer
# --------------------------------------------------------------------------------------

def test_find_workspace_honours_the_env_file(isolated, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    isolated.write_text(f"TIMESHEET_WORKSPACE={ws}\n", encoding="utf-8")
    assert skill_config.find_workspace() == ws


def test_find_workspace_uses_cwd_when_it_looks_like_a_workspace(isolated, tmp_path):
    (tmp_path / ".mcp").mkdir()
    assert skill_config.find_workspace() == tmp_path


def test_find_workspace_returns_none_rather_than_guessing(isolated):
    # No override, and nothing nearby looks like a workspace. Callers must be told
    # so they can fail loudly instead of writing catalogs to an invented path.
    assert skill_config.find_workspace() is None


def test_find_workspace_uses_the_directory_the_skill_is_installed_under(isolated, tmp_path,
                                                                       monkeypatch):
    """`<workspace>/skills/<name>` — the shape a workspace-local install has."""
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", ws / "skills" / "daily")
    assert skill_config.find_workspace() == ws


def test_find_workspace_does_not_climb_past_the_skills_directory(isolated, tmp_path,
                                                                monkeypatch):
    """Anchored on the install shape, so an unrelated ancestor is not a candidate at all.

    Reasoning and the record: `TESTING.md` § "Workspace resolution is anchored on the
    install shape, not on a depth".
    """
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", ws / "checkout" / "skills" / "daily")
    assert skill_config.find_workspace() is None


def test_find_workspace_reads_a_shared_agent_skills_install(isolated, tmp_path, monkeypatch):
    """`<workspace>/.agents/skills/<name>` — the shape the generated export has.

    `~/.agents/skills/` is where every harness that isn't Claude Code looks, and like
    `.claude/` it sits one level below the directory a workspace-local install would put
    the skill in. Without the second name here, a Codex user's workspace resolves to
    nothing and their catalogs have nowhere to go.
    """
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT",
                        ws / ".agents" / "skills" / "billables-daily")
    assert skill_config.find_workspace() == ws


def test_a_plugin_install_never_resolves_to_a_workspace_around_it(isolated, tmp_path,
                                                                 monkeypatch):
    """`<plugin>/skills/<name>` matches the workspace-local shape exactly, and must not
    resolve: the plugin holds no user data, so nothing around it is this user's workspace.
    `.claude-plugin/` beside the skills directory is what says so.

    Pinned rather than left to a green suite because the wrong answer is silent and
    delayed — the refresh reports success and the staleness surfaces days later.
    Reasoning: `TESTING.md` § "Workspace resolution is anchored on the install shape, not
    on a depth".
    """
    ws = tmp_path / "Admin"
    (ws / "Timesheets").mkdir(parents=True)
    plugin = ws / "activity-to-timesheet"
    (plugin / ".claude-plugin").mkdir(parents=True)
    monkeypatch.setattr(skill_config, "SKILL_ROOT", plugin / "skills" / "daily")
    assert skill_config.find_workspace() is None


# --------------------------------------------------------------------------------------
# The error contract for a required value that isn't there
# --------------------------------------------------------------------------------------

def test_a_missing_required_value_is_an_error_line_and_a_non_zero_exit():
    """The scripts are read by a model. A traceback reads as "the tool is broken" and
    sends it debugging the script instead of filling in the setting."""
    with pytest.raises(SystemExit) as exc:
        skill_config.fail_missing("Harvest credentials not found.")
    assert str(exc.value).startswith("ERROR: ")
    assert exc.value.code != 0


def test_missing_credentials_name_both_ways_to_supply_them(isolated):
    """The message a first-run user actually sees.

    Plugin route first — it is the one that keeps the token out of a file — and the
    exported install's `.env` second, because that install has no harness to ask and its
    user would otherwise be told to run a command that does not exist for them.
    """
    hc._CREDS_CACHE = None
    with pytest.raises(SystemExit) as exc:
        hc.load_creds()
    message = str(exc.value)
    assert message.startswith("ERROR: Harvest credentials not found.")
    assert "/plugin configure" in message
    assert ".env.example" in message
    assert "HARVEST_ACCOUNT_ID" in message and "HARVEST_API_KEY" in message


# --------------------------------------------------------------------------------------
# Structural: no second reader grows back
# --------------------------------------------------------------------------------------

# A read of the process environment. `os.environ["PYTHONIOENCODING"] = "utf-8"` is a
# write — several scripts set it before reconfiguring their streams — so the subscript
# form only counts when it is not the target of an assignment.
ENV_READ = re.compile(r"os\.environ\.get\(|os\.getenv\(|os\.environ\[(?![^\]]*\]\s*=)")


def scripts():
    return sorted(p for p in SCRIPTS.glob("*.py") if p.name != "skill_config.py")


def test_only_the_seam_reads_the_process_environment():
    offenders = [f"{p.name}:{n}" for p in scripts()
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if ENV_READ.search(line)]
    assert not offenders, (
        "these read the environment directly instead of through skill_config.setting(), "
        "which is how the .env layer got skipped before:\n  " + "\n  ".join(offenders))


def test_only_the_seam_parses_the_env_file():
    definers = [p.name for p in SCRIPTS.glob("*.py")
                if "def _parse_env_file" in p.read_text(encoding="utf-8")]
    assert definers == ["skill_config.py"]


def seam_readers() -> set[str]:
    """Modules in `scripts/` that go through the seam themselves.

    Naming a setting is allowed at one remove: `afk_blocks` documents
    `TIMESHEET_TIMEZONE` in its `--utc-offset` help and never resolves it, because
    `aw_client.resolve_zone` does — through `skill_config`, like everything else.
    Requiring the literal import in *every* script that mentions a key would push the two
    scripts back to resolving the zone apiece, which is the duplication `aw_client` exists
    to prevent.

    Derived rather than listed: a hand-maintained allowlist is a place to quietly add the
    next offender.

    Be honest about the strength of what this buys. It checks "this script imports a module
    that mentions the seam", not "this script's use of *this key* reaches the seam" — a
    script could import `aw_client` and separately grow its own read of a different key and
    stay green. What holds that line is the sibling guard below,
    `test_only_the_seam_reads_the_process_environment`, which forbids the read itself in
    every script. This one is the weaker half of a pair, and only the pair is a guarantee.
    """
    return {p.stem for p in SCRIPTS.glob("*.py")
            if "skill_config" in p.read_text(encoding="utf-8")}


def test_every_script_naming_a_setting_resolves_it_through_the_seam():
    delegates = seam_readers()
    offenders = []
    for p in scripts():
        text = p.read_text(encoding="utf-8")
        if not any(k in text for k in SETTING_KEYS):
            continue
        reaches = [d for d in delegates
                   if d != p.stem and re.search(rf"\b(?:import|from) {d}\b", text)]
        if "skill_config" not in text and not reaches:
            offenders.append(p.name)
    assert not offenders, (
        "these name a setting with no path to skill_config:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("name", ["config", "find_workspace", "ENV_PATH", "_parse_env_file"])
def test_the_api_client_no_longer_doubles_as_the_config_reader(name):
    """`harvest_client` held the settings reader by accident of history. Leaving an alias
    behind would put the seam back to two names — and two things to patch, which is how a
    hermetic fixture ends up guarding the wrong one and a test suite reads the real `.env`.
    """
    assert not hasattr(hc, name)


def test_the_precedence_is_stated_where_it_is_implemented():
    """One statement of the rule, next to the only code that applies it."""
    doc = skill_config.__doc__ or ""
    assert "Precedence" in doc
    for source in ("flag", ".env", "environment", "default"):
        assert source in doc, f"the precedence docstring never mentions the {source} layer"


# --------------------------------------------------------------------------------------
# Structural: nothing is resolved, read or written by an import
# --------------------------------------------------------------------------------------

# Importing a module has to be free. It is not, today: `refresh_catalogs` resolves the
# workspace at module scope and `sys.exit()`s when nothing answers, and `aw_client` freezes
# the activity-source address into `AW_BASE` the same way. Both are invisible from the
# outside and expensive from the inside — the suite pays for the first with a fixture
# duplicated across two files whose only job is to stage the import, and for the second
# with a conftest that has to reach in and reassign a module global to keep tests off the
# developer's real ActivityWatch.
#
# So these are the tests the prefactor is for. They say what "no side effect" means in
# three checkable parts, and each part is red against the tree as it stands.


# A literal assignment into the process environment. Derived from the sources rather than
# listed, for the reason below: the fixture has to know which keys to park a sentinel on,
# and a hand-kept list would silently stop covering the next one.
ENV_WRITE = re.compile(r"os\.environ\[[\"']([A-Z_]+)[\"']\]\s*=")


def keys_a_script_assigns() -> set[str]:
    return {key for p in SCRIPTS.glob("*.py")
            for key in ENV_WRITE.findall(p.read_text(encoding="utf-8"))}


class ImportRecord(NamedTuple):
    resolved: list[str]          # seam calls made while the module was loading
    env_delta: dict[str, str]    # process-environment keys the import added or changed


@pytest.fixture
def import_record(monkeypatch):
    """Import a bundled script from scratch and report what it did on the way in.

    The seam is wrapped rather than replaced, so the module loads exactly as it would in
    production and the recording cannot itself change the outcome — a stub returning None
    would send `aw_client` into `None.rstrip()` and prove nothing about the real path.

    `refresh_catalogs` imports its helpers with `from skill_config import ...`, which binds
    at import, so the wrappers have to be in place first; that is why this is a fixture
    around the import and not an assertion after it.

    `sys.modules` is restored by hand to whatever it held before — present *or* absent.
    Half of this suite has already imported these modules, and `conftest` holds references
    to three of them; leaving a second copy of `aw_client` behind would quietly detach the
    hermeticity fixture from the module the rest of the session uses.
    """
    def _record(name: str) -> ImportRecord:
        resolved: list[str] = []
        for fname in ("setting", "find_workspace"):
            real = getattr(skill_config, fname)

            def spy(*args, _real=real, _name=fname, **kwargs):
                resolved.append(_name)
                return _real(*args, **kwargs)

            monkeypatch.setattr(skill_config, fname, spy)

        # A write is only a *delta* if the key does not already hold the value being
        # written, and by the time any test runs, collection has imported most of these
        # modules — so `PYTHONIOENCODING` is already `utf-8` and the assignment under test
        # is invisible. Park a value no script writes on each key first, and it shows.
        for key in keys_a_script_assigns():
            monkeypatch.setenv(key, "unset-by-the-import-side-effect-test")

        before = dict(os.environ)
        cached: ModuleType | None = sys.modules.get(name)
        sys.modules.pop(name, None)
        try:
            importlib.import_module(name)
        except SystemExit as exc:
            pytest.fail(
                f"importing {name} ended the process: {exc}\n"
                "A module that exits as it loads cannot be imported by a caller, a test, "
                "or a `--help`.")
        finally:
            sys.modules.pop(name, None)
            if cached is not None:
                sys.modules[name] = cached
        after = dict(os.environ)
        return ImportRecord(
            resolved=resolved,
            env_delta={k: v for k, v in after.items() if before.get(k) != v})

    return _record


@pytest.mark.parametrize("name", bundled_script_names())
def test_importing_a_bundled_script_resolves_no_configuration(name, import_record):
    """Configuration is resolved where it is used, not where a module is loaded.

    Resolution at import is what makes a value un-redirectable: by the time any caller
    exists, the answer is already frozen into a module global, and the only way past it is
    to reassign that global — which is what `conftest` had to do to `aw_client.AW_BASE` to
    keep the suite off a real ActivityWatch, and what `test_edge_catalogs` carried a
    fixture and a paragraph headed IMPORT HAZARD to work around for `refresh_catalogs`.
    Both are gone; this is what stops them coming back.

    It is also what turns a missing setting into an import-time crash. A missing setting
    should be one `ERROR:` line at the moment the value is wanted; resolved at import it
    is instead a `SystemExit` from a bare `import`, which aborts collection for anything
    that so much as names the module.
    """
    record = import_record(name)
    assert not record.resolved, (
        f"{name} resolves configuration while it is being imported "
        f"({', '.join(sorted(set(record.resolved)))}) — so the value is fixed before any "
        "caller exists, and a missing one is an import-time exit rather than an error "
        "where it is needed")


@pytest.mark.parametrize("name", bundled_script_names())
def test_importing_a_bundled_script_writes_nothing_to_the_environment(name, import_record):
    """The other half of "no side effect", and the cheaper half to overlook.

    Four scripts set `PYTHONIOENCODING` at module scope, to fix the encoding of the child
    processes they later spawn. That is a real need with a wrong home: an import mutates
    the environment of everything else in the interpreter, including a caller that only
    wanted to read the module's argument parser. It belongs in `main()`, next to the
    subprocess it exists for.
    """
    record = import_record(name)
    assert not record.env_delta, (
        f"importing {name} changed the process environment ({sorted(record.env_delta)}) — "
        "an import is not the place to mutate state every other module can see")
