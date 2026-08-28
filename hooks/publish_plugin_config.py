"""Publish the declared plugin configuration into the session environment.

The manifest's `userConfig` block is where a user's machine and account facts are
declared, and the harness stores them for them — non-sensitive values in `settings.json`,
sensitive ones in its own credential store. It hands them back as `CLAUDE_PLUGIN_OPTION_<KEY>`
environment variables, but only to *hook* processes. The skill's scripts are run by the
model through the shell, in a process that never sees a hook's environment.

`$CLAUDE_ENV_FILE` is the bridge. On SessionStart the harness passes the path of a shell
fragment it will apply to every later command in the session; anything exported there
arrives at the scripts as an ordinary environment variable. So the values land in the
layer `skill_config` already documents as "the process environment, which is where a
harness injects values" — no new precedence, no second reader, nothing for the scripts to
know about the harness.

The option key *is* the setting key. The harness derives the variable name by upper-casing
the declared key and replacing anything outside `[A-Za-z0-9_]` with `_`; every key this
plugin declares is already an upper-case identifier, so stripping the prefix recovers the
name the scripts ask `setting()` for, exactly. `tests/test_plugin_config.py` pins that,
because a key declared as `harvest.api-key` would round-trip to something else silently.

Nothing here *lists* the options: the set to publish is read back out of the manifest
beside this file, so the manifest stays the single declaration of the surface and the two
cannot drift. Reading it rather than trusting the `CLAUDE_PLUGIN_OPTION_` prefix is
deliberate — see `option_values()`.

No third-party deps — stdlib only, like every other script in this plugin.
"""
import json
import os
import sys

PREFIX = "CLAUDE_PLUGIN_OPTION_"
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.pardir, ".claude-plugin", "plugin.json")


def declared_keys() -> set:
    """The option names this plugin declares, read from the manifest beside this file.

    Reading them rather than listing them keeps the manifest the single declaration — the
    two cannot drift. Returning an empty set on any failure means "publish nothing", which
    is the safe direction: a missing or unreadable manifest is not a reason to start
    exporting whatever else is in this process's environment.
    """
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            return set(json.load(fh).get("userConfig") or {})
    except Exception:
        return set()


def option_values(environ, declared=None) -> dict:
    """The injected options, keyed by the setting name the scripts resolve.

    Restricted to the keys this plugin declares. The prefix alone is not a safe filter:
    it is the harness's namespace, not this plugin's, so if a hook process is ever handed
    another enabled plugin's options too, filtering on the prefix would export that
    plugin's *sensitive* values into the environment of every shell command for the rest
    of the session — visible to any subprocess, any `env`, anything that logs its
    environment. Whether the harness scopes the injection was not something to find out
    from a leak, and intersecting costs one `json.load`.

    A blank value is dropped rather than published. `skill_config.has_value()` already
    treats blank as unset at every layer, and publishing `KEY=` would mean an option the
    user deliberately left empty writes an empty variable that a later reader has to know
    to ignore.
    """
    declared = declared_keys() if declared is None else declared
    out = {}
    for name, value in environ.items():
        if not name.startswith(PREFIX) or not value.strip():
            continue
        key = name[len(PREFIX):]
        if key in declared:
            out[key] = value
    return out


def render(options: dict) -> str:
    """The shell fragment exporting `options`, POSIX-quoted.

    Single quotes, with an embedded quote written as `'\\''`: the values are a user's
    tokens and paths, and a token containing `$` or a backtick must not be expanded by
    the shell that sources this. Sorted so the fragment is stable across sessions and a
    diff of it means a value actually changed.
    """
    lines = []
    for key in sorted(options):
        quoted = options[key].replace("'", "'\\''")
        lines.append(f"export {key}='{quoted}'")
    return "".join(line + "\n" for line in lines)


def main() -> int:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        # Not every hook event is given one. Nothing to publish is not a failure.
        return 0
    fragment = render(option_values(os.environ))
    if not fragment:
        return 0
    # Appended in one write, and appended rather than truncated: the file is shared with
    # every other hook that publishes to this session, and a partial write would leave a
    # half-quoted line that breaks every command in the session rather than one setting.
    # `newline="\n"` because this is a shell fragment, not a text document: on Windows the
    # default translation would write CRLF, and while the shell that sources it strips the
    # CR, anything that reads the file rather than sourcing it would carry a stray CR into
    # the value.
    with open(env_file, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(fragment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
