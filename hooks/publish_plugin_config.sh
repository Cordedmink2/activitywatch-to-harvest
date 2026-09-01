#!/bin/sh
# Hand the declared plugin configuration to the bundled scripts.
#
# The harness injects a plugin's `userConfig` values as CLAUDE_PLUGIN_OPTION_<KEY> into
# *hook* processes only. The skill's scripts are run by the model through the shell, in a
# process that never sees them. `publish_plugin_config.py` bridges the two by writing the
# values into $CLAUDE_ENV_FILE, which the harness applies to every later shell command —
# so they arrive as ordinary environment variables and `skill_config.setting()` resolves
# them through the precedence it already documents. No new configuration layer.
#
# Why this wrapper exists rather than naming an interpreter in the manifest: on Windows a
# bare `python` is frequently the Microsoft Store stub, a 0-byte executable that prints an
# install nag and exits non-zero (the `setup` skill's "Before you start" makes the same
# point about running the scripts). Trying the candidates in order is the difference
# between "configuration silently absent" and "configuration present".
#
# KNOWN LIMITATION, accepted with its reasoning in `skills/daily/TESTING.md`: Claude Code
# runs hook commands through Git Bash on Windows, and through PowerShell when Git Bash is
# not installed — where `sh` is not a command and this wrapper never starts. There is no
# single command string valid in both shells that also names a working interpreter, and
# declaring one hook entry per shell would print a spawn error at every session start on
# whichever platform is not that one. So the gap is closed by diagnosis instead: both
# "missing setting" messages the user would hit name a new session first and
# `references/setup.md` § "When the configuration does not arrive" second, which is where
# `winget install Git.Git` is.
#
# Exit 0 whatever happens. A session must not fail to start because configuration could
# not be published; the scripts report a missing setting themselves, with a message that
# names the fix.

for candidate in python3 python py; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    "$candidate" "$(dirname "$0")/publish_plugin_config.py" && exit 0
done
exit 0
