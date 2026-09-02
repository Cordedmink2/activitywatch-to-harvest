#!/bin/sh
# Hand the declared plugin configuration to the bundled scripts.
#
# The harness injects a plugin's `userConfig` values as CLAUDE_PLUGIN_OPTION_<KEY> into
# *hook* processes only. The skill's scripts are run by the model through the shell, in a
# process that never sees them. `publish_plugin_config.py` bridges the two by writing the
# values into $CLAUDE_ENV_FILE, which the harness applies to later *Bash tool* calls — so
# they arrive as ordinary environment variables and `skill_config.setting()` resolves them
# through the precedence it already documents. No new configuration layer.
#
# Bash tool calls and no others: the fragment is POSIX shell, and Claude Code's PowerShell
# tool is given no equivalent. See the second known limitation below.
#
# Why this wrapper exists rather than naming an interpreter in the manifest: on Windows a
# bare `python` is frequently the Microsoft Store stub, a 0-byte executable that prints an
# install nag and exits non-zero (the `setup` skill's "Before you start" makes the same
# point about running the scripts). Trying the candidates in order is the difference
# between "configuration silently absent" and "configuration present".
#
# And each candidate is judged by whether the fragment *grew*, not by what it returned.
# An exit code says the command came back, not that it ran the script: `python3` in
# `WindowsApps` is a shim of exactly that shape, and one that exits 0 having done nothing
# would stop this loop at the first name on the list while publishing nothing at all —
# a session with no configuration and a hook that reported success. Judging the effect
# also covers the shim observed on 2026-09-02, which handed control to the Python install
# manager and printed fifteen lines of installer output before recovering.
# `tests/test_plugin_config.py` pins it.
#
# KNOWN LIMITATION, accepted with its reasoning in `skills/daily/TESTING.md`: Claude Code
# runs hook commands through Git Bash on Windows, and through PowerShell when Git Bash is
# not installed — where `sh` is not a command and this wrapper never starts. There is no
# single command string valid in both shells that also names a working interpreter, and
# declaring one hook entry per shell would print a spawn error at every session start on
# whichever platform is not that one. So the gap is closed by diagnosis instead: the
# "missing setting" messages the user would hit name a new session first and
# `references/setup.md` § "When the configuration does not arrive" second, which is where
# `winget install Git.Git` is.
#
# KNOWN LIMITATION, the second one and a different one: this wrapper running is not enough
# for the values to reach the *script*. The fragment is applied to Bash tool calls alone,
# so on a machine with Git Bash — where this hook ran and wrote the fragment correctly —
# anything the model chooses to run through the PowerShell tool still finds nothing
# configured. The skills direct every read of a configured value through Bash, and
# `skill_config.note_for_an_unreached_shell()` names the shell in the error when a command
# gets through regardless. Do not merge the two: `winget install Git.Git` is the fix for
# the gap above and does nothing whatever for this one.
#
# Exit 0 whatever happens. A session must not fail to start because configuration could
# not be published; the scripts report a missing setting themselves, with a message that
# names the fix.

# Nothing to publish into. Not every hook event is handed an env file, and the publisher
# says so itself by returning 0 — but without this the loop would start an interpreter
# once per candidate to be told that three times.
[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0

# Measured as a delta, because the file is shared with every other hook publishing to
# this session: "the fragment is non-empty" can be true before this hook has done
# anything, so only growth is evidence that *this* publisher ran.
size() {
    wc -c < "$CLAUDE_ENV_FILE" 2>/dev/null | tr -d ' ' || true
}
before=$(size)
[ -n "$before" ] || before=0

for candidate in python3 python py; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    "$candidate" "$(dirname "$0")/publish_plugin_config.py" || continue
    after=$(size)
    [ -n "$after" ] || after=0
    [ "$after" -gt "$before" ] && exit 0
done
exit 0
