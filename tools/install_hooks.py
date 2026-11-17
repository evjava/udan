#!/usr/bin/env python3
"""Install the git pre-commit hook that runs tools/run_checks.py.

The hook runs all checks from .pre-commit-config.yaml on every commit.
The pre-commit framework (which resolves files through git and therefore needs
a .git directory) is no longer involved - the runner works on the filesystem.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MARKER = "# Installed by tools/install_hooks.py"
HOOK = f"""\
#!/bin/sh
{MARKER}: run all hooks from .pre-commit-config.yaml.
set -e
top="$(git rev-parse --show-toplevel)"
cd "$top"
exec uv run python tools/run_checks.py
"""


def hooks_dir() -> Path:
    """Return the directory git runs hooks from (honors worktrees and core.hooksPath)."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    try:
        hook_path = hooks_dir() / "pre-commit"
    except FileNotFoundError, subprocess.CalledProcessError:
        print("Not a git repository - nothing to install (make pre works without git).")
        return 1

    if hook_path.exists() and MARKER not in hook_path.read_text():
        print(f"Replacing existing hook: {hook_path}")
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(HOOK)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Installed pre-commit hook: {hook_path}")
    print("It runs all hooks from .pre-commit-config.yaml via tools/run_checks.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
