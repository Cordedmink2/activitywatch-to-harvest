"""Guards on the artifact that actually gets installed.

This repo is a marketplace whose single plugin is the repo root, so what a stranger
installs is not the code these tests import — it is two manifests plus `skills/`. Those
fail in ways no script-level test can see: a manifest that won't parse, a skill whose
declared name disagrees with its directory, a version that drifted from the changelog.
Nothing here reaches into the code that produced the artifact; every assertion is on
something a consumer can read.

The platform's own validator carries most of it. It is not vendored — asserting our idea
of the schema would be asserting our idea of the schema — so the tests that need it skip
when the `claude` CLI isn't on PATH, and the structural assertions below stand on their own
without it.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST_DIR = REPO / ".claude-plugin"
PLUGIN_MANIFEST = MANIFEST_DIR / "plugin.json"
MARKETPLACE_MANIFEST = MANIFEST_DIR / "marketplace.json"
SKILLS = REPO / "skills"

PLUGIN_NAME = "billables"
MARKETPLACE_NAME = "activity-to-timesheet"

CLAUDE = shutil.which("claude")
requires_claude = pytest.mark.skipif(not CLAUDE, reason="the claude CLI is not on PATH")


def validate(target: Path):
    """`claude plugin validate --strict <target>` — returncode plus combined output."""
    return subprocess.run([CLAUDE, "plugin", "validate", "--strict", str(target)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def validator_warnings(output: str) -> set[str]:
    """The `❯ <text>` lines the validator reports, one per warning."""
    return {m.group(1).strip() for m in re.finditer(r"^\s*❯ (.+)$", output, re.M)}


def manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_dirs() -> list[Path]:
    return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def frontmatter(skill_md: Path) -> dict[str, str]:
    """The top-level `key: value` pairs of the YAML frontmatter, or {} if there is none.

    Deliberately not a YAML parser: the fields asserted on here are the flat scalars the
    spec defines, and a dependency-free reader keeps these tests runnable anywhere the
    plugin is.
    """
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    head = text.split("---", 2)[1]
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^([A-Za-z][\w-]*):[ \t]*(.*)$", head, re.M)}


def frontmatter_name(skill_md: Path) -> str | None:
    """The `name:` from the YAML frontmatter, or None if there is no frontmatter."""
    return frontmatter(skill_md).get("name")


# --------------------------------------------------------------------------------------
# The platform's validator
# --------------------------------------------------------------------------------------

@requires_claude
def test_the_marketplace_manifest_validates_strictly():
    """What `/plugin marketplace add` reads first. A stranger's install stops here."""
    res = validate(REPO)
    assert res.returncode == 0, res.stdout + res.stderr


@requires_claude
def test_the_shipped_skills_validate_strictly():
    """Frontmatter the harness rejects makes a skill silently absent, not broken."""
    res = validate(SKILLS)
    assert res.returncode == 0, res.stdout + res.stderr


# The plugin root is the repo root, so the repo's own `CLAUDE.md` is a file the plugin
# carries and does not use. Deleting it is not the fix: checked on 2026-08-28, a fresh
# Claude Code session in this repo with `CLAUDE.md` moved aside loads no project
# instructions at all — not `AGENTS.md`, which `CLAUDE.md` exists to import. So the
# warning is accepted, and pinned here rather than left to be rediscovered.
CLAUDE_MD_AT_PLUGIN_ROOT = re.compile(r"CLAUDE\.md at the plugin root")


@requires_claude
def test_the_plugin_manifest_carries_no_warning_but_the_accepted_one():
    """Pinned, not suppressed: a *second* warning fails this, which is the point.

    Asserting the set rather than the exit code is what keeps the accepted exception from
    turning into a blanket "warnings are fine here" — the next one has to be looked at.
    """
    res = validate(PLUGIN_MANIFEST)
    unexpected = {w for w in validator_warnings(res.stdout + res.stderr)
                  if not CLAUDE_MD_AT_PLUGIN_ROOT.search(w)}
    assert not unexpected, (
        "the plugin manifest has a warning nobody has decided about:\n  "
        + "\n  ".join(sorted(unexpected)))


# --------------------------------------------------------------------------------------
# Structure, without the CLI
# --------------------------------------------------------------------------------------

def test_the_plugin_is_the_repo_root():
    """The single-plugin-repo layout: manifests in `.claude-plugin/`, components beside it.

    Components nested inside `.claude-plugin/` are not discovered, and the failure is
    silence — the plugin installs and has nothing in it.
    """
    assert PLUGIN_MANIFEST.is_file() and MARKETPLACE_MANIFEST.is_file()
    assert SKILLS.is_dir(), "skills/ is not at the plugin root"
    assert not (MANIFEST_DIR / "skills").exists(), "skills/ nested where nothing reads it"


def test_the_plugin_name_is_the_one_that_prefixes_every_skill():
    """`/billables:daily`. The name prefixes every skill, so changing it breaks installs —
    it is treated as permanent, and this is what says so."""
    assert manifest(PLUGIN_MANIFEST)["name"] == PLUGIN_NAME


def test_the_marketplace_offers_this_repo_as_the_plugin():
    mkt = manifest(MARKETPLACE_MANIFEST)
    assert mkt["name"] == MARKETPLACE_NAME
    entries = [p for p in mkt["plugins"] if p["name"] == PLUGIN_NAME]
    assert len(entries) == 1, f"{PLUGIN_NAME} is not offered exactly once: {mkt['plugins']}"
    assert entries[0]["source"] == "./", "the plugin source is not the repo root"


def test_at_least_one_skill_ships():
    assert skill_dirs(), "the plugin ships no skills"


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_each_declared_skill_name_matches_its_directory(skill):
    """The directory is what a user types; the frontmatter is what a consumer reads. When
    they disagree there is no single answer to "what is this skill called", and the shared
    Agent Skills directory — flat and unnamespaced — has only the declared name to go on."""
    assert frontmatter_name(skill / "SKILL.md") == skill.name


# The `owner/repo` a user types into `/plugin marketplace add`. It is not the marketplace
# name and not the plugin name, so nothing else in here pins it — which is how the docs
# came to name a slug that returned 404 for a day.
SLUG = "Cordedmink2/activity-to-timesheet"
SLUG_DOCS = [REPO / "README.md",
             SKILLS / "daily" / "references" / "reporting-issues.md"]


@pytest.mark.parametrize("doc", SLUG_DOCS, ids=lambda p: p.name)
def test_every_documented_repo_slug_is_the_same_one(doc):
    """One slug across the install commands, the manifest and the issue-filing command.

    `reporting-issues.md` matters most: it is the only route an installee has for a defect
    report, and a stale `-R owner/repo` there fails at the moment they are already annoyed.
    """
    found = set(re.findall(r"Cordedmink2/[A-Za-z0-9._-]+", doc.read_text(encoding="utf-8")))
    assert found <= {SLUG}, f"{doc.name} names another repo slug: {sorted(found - {SLUG})}"


def test_the_manifest_points_at_the_same_repo():
    mf = manifest(PLUGIN_MANIFEST)
    for field in ("homepage", "repository"):
        assert SLUG in mf[field], f"plugin.json {field} does not name {SLUG}: {mf[field]}"


GH = shutil.which("gh")


@pytest.mark.skipif(not GH, reason="the gh CLI is not on PATH")
def test_the_documented_slug_resolves_on_github():
    """The check that a doc sweep cannot do for itself.

    Renaming the repo leaves the docs naming a slug that 404s, and every local assertion
    still passes because they are all internally consistent. Only GitHub knows. Skipped
    rather than failed when the network or `gh` auth is unavailable, so it is evidence when
    it runs and never a false alarm when it can't.
    """
    res = subprocess.run([GH, "repo", "view", SLUG, "--json", "nameWithOwner"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        stderr = res.stderr.lower()
        if "not found" in stderr or "could not resolve" in stderr:
            pytest.fail(f"{SLUG} does not resolve on GitHub — the install commands 404")
        pytest.skip(f"cannot reach GitHub: {res.stderr.strip()[:120]}")
    assert json.loads(res.stdout)["nameWithOwner"] == SLUG


def test_every_version_marker_agrees():
    """Two markers, and the manifest is the one that owns the number — it is what a
    marketplace displays and what the export prints. The changelog is the only other
    place a version is written down, and a heading that disagrees with what shipped is
    worse than no heading at all.
    """
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
    assert released, "no released version heading in CHANGELOG.md"
    markers = {
        "plugin.json": manifest(PLUGIN_MANIFEST)["version"],
        "CHANGELOG.md": released.group(1),
    }
    assert len(set(markers.values())) == 1, f"version markers disagree: {markers}"


# --------------------------------------------------------------------------------------
# The retired install path
# --------------------------------------------------------------------------------------
#
# There was a second way in: clone the repo and have an agent follow `llms.txt`, a
# hand-maintained runbook, with a `VERSION` file and a publish script keeping the copies
# in step. Two install paths drift — that is the failure the plugin exists to remove — so
# the runbook, the second version marker and the release ritual are gone, and this is what
# says they stay gone. See `docs/adr/0005-the-setup-skill-replaces-llms-txt.md`.

RETIRED_FILES = ["llms.txt", "skills/daily/VERSION"]


def instruction_docs() -> list[Path]:
    """Everything scanned below: what a reader is *told to do*, as opposed to what happened.

    An enumeration rather than "the tree minus some exclusions", so read it as the scope
    and not as a claim about the rest of the repo. `CHANGELOG.md`, `docs/RECOVERY.md`,
    `docs/adr/` and `skills/daily/TESTING.md` are deliberately outside it — they record the
    past, and naming a retired thing accurately is their job — but so is everything else
    not listed, including `tests/`, which has to be able to write these names down in order
    to assert on them.

    `scripts/` is in scope because that is where the evidence was: retiring the runbook had
    to correct a comment in `harvest_list.py` and another in the SessionStart hook. A
    docstring naming a file that no longer exists sends a reader looking for it just as a
    markdown line does.
    """
    docs = [REPO / "README.md", REPO / "AGENTS.md", REPO / "CLAUDE.md",
            REPO / "CONTEXT.md", REPO / "INTENT.md"]
    docs += sorted((REPO / ".github").rglob("*.yml"))
    docs += sorted((REPO / "docs" / "agents").glob("*.md"))
    docs += sorted((REPO / "hooks").iterdir()) + sorted((REPO / "install").iterdir())
    for skill in skill_dirs():
        docs += [skill / "SKILL.md", *sorted((skill / "references").glob("*.md")),
                 *sorted((skill / "scripts").glob("*"))]
    return [p for p in docs if p.is_file()]


# `runbook` bare, not just the filename: the surviving references this ticket had to fix
# called it "the setup runbook" without ever naming `llms.txt`, so a pattern that only
# matched the filename would have found neither.
RETIRED_NAMES = re.compile(r"llms\.txt|publish\.ps1|daily-timesheet-release|runbook")


@pytest.mark.parametrize("path", RETIRED_FILES)
def test_the_retired_install_path_is_gone(path):
    assert not (REPO / path).exists(), f"{path} is still here — the second install path survives"


@pytest.mark.parametrize("doc", instruction_docs(),
                         ids=lambda p: p.relative_to(REPO).as_posix())
def test_no_instruction_names_the_retired_install_path(doc):
    """An instruction naming a file that no longer exists is worse than a missing one: the
    reader follows it, finds nothing, and cannot tell whether their install is broken."""
    offenders = [line.strip() for line in doc.read_text(encoding="utf-8").splitlines()
                 if RETIRED_NAMES.search(line)]
    assert not offenders, (
        f"{doc.relative_to(REPO).as_posix()} still sends a reader to the retired install "
        "path:\n  " + "\n  ".join(offenders))


# --------------------------------------------------------------------------------------
# The shared Agent Skills export
# --------------------------------------------------------------------------------------
#
# The second artifact this repo ships. `~/.agents/skills/` is where every harness that
# isn't Claude Code looks, and it is flat and unnamespaced — one directory per skill, no
# plugin above it to say whose `daily` this is. So the export is prefixed, and the
# declared name is rewritten to match, because the spec requires the two to agree and the
# declared name is all a consumer has to go on.
#
# It is generated, never hand-edited, which is only true if regenerating it is worth
# nothing: hence the idempotence assertion below.

EXPORT_SCRIPT = REPO / "install" / "export_agent_skills.py"

# The spec's `name`: 1-64 characters, lowercase alphanumerics and hyphens, no leading,
# trailing or consecutive hyphen.
LEGAL_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def generate_export(dest: Path):
    res = subprocess.run([sys.executable, str(EXPORT_SCRIPT), str(dest)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert res.returncode == 0, f"the export failed:\n{res.stdout}{res.stderr}"
    return res


def file_tree(root: Path) -> dict:
    """Every file under `root`, keyed by its relative path, with its bytes."""
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def exported(tmp_path_factory) -> Path:
    """One generated export, shared by the assertions below.

    Written to a directory named `skills`, as `~/.agents/skills` is: that name is what
    tells the platform validator it is looking at components rather than a plugin root.
    """
    dest = tmp_path_factory.mktemp("agents") / "skills"
    generate_export(dest)
    return dest


def exported_dirs(dest: Path) -> list[Path]:
    return sorted(p for p in dest.iterdir() if p.is_dir())


def test_the_export_holds_one_prefixed_directory_per_shipped_skill(exported):
    """`billables-daily`, not `daily`. A bare `daily` sitting among a user's other skills
    says nothing about where it came from, and collides with anyone else's."""
    assert [p.name for p in exported_dirs(exported)] == \
        [f"{PLUGIN_NAME}-{s.name}" for s in skill_dirs()]


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_each_exported_skill_declares_the_name_of_its_directory(exported, skill):
    """The rename has to reach the frontmatter too. A directory the spec-valid consumers
    read as `billables-daily` whose `name:` still says `daily` is invalid, and the failure
    is a skill that never activates rather than one that errors."""
    exported_skill = exported / f"{PLUGIN_NAME}-{skill.name}"
    assert frontmatter_name(exported_skill / "SKILL.md") == exported_skill.name


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_every_exported_name_is_a_legal_skill_name(exported, skill):
    name = (exported / f"{PLUGIN_NAME}-{skill.name}").name
    assert len(name) <= 64 and LEGAL_SKILL_NAME.match(name), \
        f"{name} is not a legal Agent Skills name"


def test_the_export_carries_no_secrets_and_no_scratch(exported):
    """A maintainer's own `.env` in the working tree must never leave with the export, and
    test scratch shipped into a user's skills directory is noise they didn't ask for."""
    offenders = [path for path in file_tree(exported)
                 if Path(path).name == ".env"
                 or {"__pycache__", ".pytest_cache"} & set(Path(path).parts)]
    assert not offenders, f"the export carries files it should not: {offenders}"


def test_regenerating_the_export_changes_nothing(exported):
    """Idempotence is what makes this an artifact rather than a second source of truth:
    a user can re-run it at any time and a maintainer never has to reason about which of
    two copies is current."""
    before = file_tree(exported)
    generate_export(exported)
    assert file_tree(exported) == before


@pytest.mark.parametrize("skill", skill_dirs(), ids=lambda p: p.name)
def test_every_shipped_skill_says_what_it_needs_in_order_to_run(skill):
    """`compatibility` is where the spec puts environment requirements, and a harness that
    isn't Claude Code has no plugin manifest to read them from — the frontmatter is all it
    gets. Someone on Codex should learn about the interpreter and the activity source
    before starting a run, not from a script failing halfway through one."""
    fields = frontmatter(skill / "SKILL.md")
    stated = fields.get("compatibility", "")
    assert stated, f"{skill.name} declares no compatibility"
    assert len(stated) <= 500, f"{skill.name} compatibility exceeds the spec's 500 characters"


@requires_claude
def test_the_generated_export_validates_strictly(exported):
    """The same validator the shipped skills go through, over the generated copy — the
    rewrite is exactly the kind of edit that produces frontmatter nothing will load."""
    res = validate(exported)
    assert res.returncode == 0, res.stdout + res.stderr
