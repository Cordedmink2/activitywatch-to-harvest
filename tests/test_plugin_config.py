"""Guards on the configuration surface the manifest declares, and on the bridge to it.

A fresh install asks the user for their own facts once. The manifest's `userConfig` block
is where that question is written down: what is asked, what is optional, and what the
harness must keep out of a file. Getting it wrong fails in ways no script-level test can
see — a required field left optional means an install that completes and a run that
doesn't; a credential not marked sensitive means a token written into `settings.json` in
plaintext; a default baked into the timezone means someone else's day silently dated in
New Zealand.

The other half is the bridge. The harness injects the declared values as
`CLAUDE_PLUGIN_OPTION_<KEY>` into *hook* processes only, so `hooks/publish_plugin_config.py`
republishes them through `$CLAUDE_ENV_FILE` — which reaches the scripts the model runs
through the **Bash** tool, and no others. The assertions below are on the shapes that make
that round-trip exact and the quoting that makes it safe; the platform's own behaviour was
verified empirically against the installed CLI rather than asserted from a reading of it,
including the scope: a fragment published by a hook was read back as set in a Bash tool
call and unset in a PowerShell one, in the same session.

Nothing here can hold that scope — it is the harness's behaviour, not this repo's. What
the repo holds instead is the skills directing every read of a configured value through
Bash, and `skill_config.note_for_an_unreached_shell()` naming the shell when a command
gets through regardless; `skills/daily/TESTING.md` § "Two ways the configuration does not
arrive" carries the evidence and the rejected alternatives.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = REPO / ".claude-plugin" / "plugin.json"
HOOKS = REPO / "hooks"

# What must be asked for, because nothing can run without it.
REQUIRED = {"HARVEST_ACCOUNT_ID", "HARVEST_API_KEY", "TIMESHEET_TIMEZONE"}
# What the harness must keep out of `settings.json` and out of the plugin folder.
SENSITIVE = {"HARVEST_ACCOUNT_ID", "HARVEST_API_KEY"}
# What a user can leave blank and still complete a run.
OPTIONAL = {"TIMESHEET_ACTIVITY_URL", "TIMESHEET_SCREENSHOTS_DIR", "TIMESHEET_WORKSPACE"}


def user_config() -> dict:
    return json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))["userConfig"]


def load_publisher():
    """`hooks/publish_plugin_config.py`, imported by path.

    It is a hook script, not a package member — the harness runs it by path and nothing
    imports it — so there is no module to import by name.
    """
    path = HOOKS / "publish_plugin_config.py"
    spec = importlib.util.spec_from_file_location("publish_plugin_config", path)
    assert spec and spec.loader, f"{path} is not importable as a module"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publisher = load_publisher()


# --------------------------------------------------------------------------------------
# What the install asks for
# --------------------------------------------------------------------------------------

def test_the_declared_surface_is_exactly_the_settings_the_scripts_resolve():
    """The manifest is the single declaration. An option nobody reads is a question asked
    for nothing; a setting nobody declares is a question never asked, and the user meets it
    as a failed run instead."""
    assert set(user_config()) == REQUIRED | OPTIONAL


def test_every_value_without_which_nothing_runs_is_required():
    """`required` is what makes the install *prompt*. Left off, the install completes and
    the first run is the thing that fails — at which point the user has no dialog to go
    back to, only an error naming a key."""
    asked = {k for k, opt in user_config().items() if opt.get("required")}
    assert asked == REQUIRED


def test_everything_else_is_skipped_at_install_time():
    """AC: "a user who sets nothing optional can still complete a run". Each of these has a
    working fallback in the scripts — localhost, `~/Pictures/WorkScreenshots`, the current
    directory — so asking for it would be asking a new user to answer a question they have
    no basis to answer yet."""
    for key in OPTIONAL:
        assert not user_config()[key].get("required"), f"{key} is asked for but need not be"


def test_the_credentials_are_the_sensitive_fields_and_nothing_else_is():
    """`sensitive` is what keeps a value out of `settings.json`.

    Verified empirically against the installed CLI: a non-sensitive option lands in
    `~/.claude/settings.json` under `pluginConfigs`, a sensitive one does not appear there
    at all — it goes to the harness's own credential store (the OS keychain on macOS,
    `~/.claude/.credentials.json` elsewhere; the docs say which, because this plugin is
    Windows-first and a flat "keychain" would be wrong for most of its users).

    So this flag is the whole of AC "provider credentials are stored by the harness, not
    written to a file in the plugin" — there is no second mechanism to also set.

    Asserting equality, not containment: marking a path or a URL sensitive would hide it
    from the user's own `settings.json` for no benefit, and make a wrong value unreadable
    at exactly the moment they are trying to see what they typed.
    """
    marked = {k for k, opt in user_config().items() if opt.get("sensitive")}
    assert marked == SENSITIVE


def test_no_option_carries_a_default():
    """AC: "no New Zealand default is silently applied to a new user's data".

    Two reasons, and the second is the load-bearing one. A timezone default would date
    another user's timesheet in the wrong day. And a manifest `default` is only a *dialog
    pre-fill* — verified empirically: an optional option the user never set is not injected
    into the hook environment at all, default or no default. So a default here would not
    even reach the scripts; it would only put a value in front of a user as though it were
    the considered answer for them. The real fallbacks live in the scripts, at the
    `setting(..., default=...)` call that documents each one.
    """
    with_defaults = {k for k, opt in user_config().items() if "default" in opt}
    assert not with_defaults, f"a default is declared for: {sorted(with_defaults)}"


@pytest.mark.parametrize("key", sorted(REQUIRED | OPTIONAL))
def test_every_option_says_what_it_is_and_where_to_get_it(key):
    """The dialog shows the title and description and nothing else. A user filling in
    `HARVEST_ACCOUNT_ID` needs the URL it is printed at, not a restatement of the key."""
    opt = user_config()[key]
    assert opt.get("title"), f"{key} has no title"
    assert len(opt.get("description", "")) > 30, f"{key}'s description does not say enough"


def test_the_two_directories_are_declared_as_directories():
    """`type: "directory"` gives the dialog a picker. It does *not* validate that the path
    exists — verified empirically: `C:/does/not/exist/at/all` was accepted and stored. So
    the type is for the user's convenience, and every consumer of these two still has to
    handle a path that isn't there."""
    cfg = user_config()
    assert cfg["TIMESHEET_SCREENSHOTS_DIR"]["type"] == "directory"
    assert cfg["TIMESHEET_WORKSPACE"]["type"] == "directory"


# --------------------------------------------------------------------------------------
# The round-trip to the scripts
# --------------------------------------------------------------------------------------

IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_]*$")


@pytest.mark.parametrize("key", sorted(REQUIRED | OPTIONAL))
def test_every_option_key_survives_the_round_trip_to_a_variable_name(key):
    """The option key *is* the setting key the scripts ask `setting()` for.

    The harness derives the injected variable name by upper-casing the key and replacing
    anything outside `[A-Za-z0-9_]` with `_`. That is lossy: a key declared as
    `harvest.api-key` arrives as `HARVEST_API_KEY`, and stripping the prefix back would
    recover a name no script resolves — silently, with the value simply absent. Declaring
    every key as an already-upper-case identifier makes the derivation the identity.
    """
    assert IDENTIFIER.match(key), f"{key} would not round-trip through the harness's naming"


def test_a_session_start_hook_publishes_the_configuration():
    """Without this the declared values reach hook processes and stop there. The manifest
    entry and the two files it names are one mechanism; a missing file is a session that
    starts fine and a skill that behaves as though nothing was ever configured."""
    manifest = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    commands = [h["command"]
                for group in manifest["hooks"]["SessionStart"]
                for h in group["hooks"]]
    assert any("publish_plugin_config.sh" in c for c in commands), commands
    assert (HOOKS / "publish_plugin_config.sh").is_file()
    assert (HOOKS / "publish_plugin_config.py").is_file()


def test_only_the_injected_options_are_published():
    """The bridge publishes what the harness injected and nothing else. It must not carry
    the rest of a hook process's environment into every command in the session."""
    got = publisher.option_values({
        "CLAUDE_PLUGIN_OPTION_TIMESHEET_TIMEZONE": "Europe/London",
        "PATH": "/usr/bin",
        "HARVEST_API_KEY": "not-ours-to-republish",
    })
    assert got == {"TIMESHEET_TIMEZONE": "Europe/London"}


def test_another_plugins_secret_is_never_republished():
    """The `CLAUDE_PLUGIN_OPTION_` prefix is the *harness's* namespace, not this plugin's.

    If a hook process is ever handed every enabled plugin's options, filtering on the
    prefix alone would export another plugin's sensitive value into the environment of
    every shell command for the rest of the session — where any subprocess, any `env`, and
    anything that logs its environment can read it. Intersecting against this manifest's
    declared keys makes the question moot rather than something to find out from a leak.
    """
    assert publisher.option_values({
        "CLAUDE_PLUGIN_OPTION_TIMESHEET_TIMEZONE": "Europe/London",
        "CLAUDE_PLUGIN_OPTION_SOME_OTHER_PLUGIN_TOKEN": "not-ours-to-republish",
    }) == {"TIMESHEET_TIMEZONE": "Europe/London"}


def test_the_declared_keys_are_read_from_the_manifest_beside_the_hook():
    """Read, not listed — so the filter cannot drift from the surface it filters against."""
    assert publisher.declared_keys() == REQUIRED | OPTIONAL


def test_an_unreadable_manifest_publishes_nothing_rather_than_everything(monkeypatch):
    """The safe direction. A manifest that cannot be read is not a licence to export
    whatever else happens to be in this process's environment."""
    monkeypatch.setattr(publisher, "MANIFEST", "no-such-manifest.json")
    assert publisher.declared_keys() == set()
    assert publisher.option_values(
        {"CLAUDE_PLUGIN_OPTION_TIMESHEET_TIMEZONE": "Europe/London"}) == {}


def test_a_blank_option_is_dropped_rather_than_published_as_empty():
    """`skill_config.has_value()` already treats blank as unset at every layer. Publishing
    `KEY=` would put an empty variable in front of that rule, and every later reader would
    have to know to ignore it."""
    assert publisher.option_values({
        "CLAUDE_PLUGIN_OPTION_TIMESHEET_ACTIVITY_URL": "",
        "CLAUDE_PLUGIN_OPTION_TIMESHEET_WORKSPACE": "   ",
    }) == {}


def test_a_value_with_a_quote_or_a_dollar_sign_arrives_unchanged():
    """These are a user's tokens and paths, and the fragment is sourced by a shell. An
    unescaped `$` or backtick would be expanded — a token silently truncated to whatever
    survived expansion, authenticating as nobody and failing with a 401 that names the
    wrong problem."""
    fragment = publisher.render({"HARVEST_API_KEY": "pt.$who`s`_it's-me"})
    assert fragment == "export HARVEST_API_KEY='pt.$who`s`_it'\\''s-me'\n"


def test_the_fragment_is_ordered_so_a_diff_of_it_means_a_value_changed():
    fragment = publisher.render({"B_KEY": "2", "A_KEY": "1"})
    assert fragment == "export A_KEY='1'\nexport B_KEY='2'\n"


def test_publishing_appends_to_the_file_the_harness_named(tmp_path, monkeypatch):
    """Appended, not truncated: the fragment is shared with every other hook publishing to
    this session, and a truncating write would take theirs out."""
    env_file = tmp_path / "sessionstart-hook-0.sh"
    env_file.write_bytes(b"export SOMETHING_ELSE='kept'\n")
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_TIMESHEET_TIMEZONE", "Pacific/Auckland")

    assert publisher.main() == 0
    # Bytes, not text: `read_text` translates CRLF back to `\n`, so it cannot tell a shell
    # fragment from a Windows text file — which is exactly the mistake being pinned. The
    # shell that sources this strips a stray CR, but anything that *reads* the file rather
    # than sourcing it would carry the CR into the value.
    assert env_file.read_bytes() == (
        b"export SOMETHING_ELSE='kept'\n"
        b"export TIMESHEET_TIMEZONE='Pacific/Auckland'\n")


def test_a_hook_event_given_no_env_file_is_not_a_failure(monkeypatch):
    """Not every event is handed one. A non-zero exit from a SessionStart hook is noise in
    front of a user who has done nothing wrong."""
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_TIMESHEET_TIMEZONE", "Pacific/Auckland")
    assert publisher.main() == 0


def test_nothing_configured_writes_nothing(tmp_path, monkeypatch):
    """A user who has configured nothing yet should not have an empty fragment appended to
    a file every session start."""
    env_file = tmp_path / "sessionstart-hook-0.sh"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    for name in list(publisher.os.environ):
        if name.startswith(publisher.PREFIX):
            monkeypatch.delenv(name, raising=False)
    assert publisher.main() == 0
    assert not env_file.exists()
