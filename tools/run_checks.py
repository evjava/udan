#!/usr/bin/env python3
"""Run hooks from .pre-commit-config.yaml without the pre-commit framework.

`make pre` used to call `pre-commit run --all-files`, which resolves its file
list through git and therefore requires a .git directory (it breaks in git
worktrees, exported trees and other gitless checkouts). This script reads the
same config and works directly on the filesystem, so the checks run anywhere.

Only the parts of pre-commit this repo actually uses are emulated:
- language=system hooks (with or without pass_filenames)
- language=pygrep hooks (fail when the pattern is found in a line)
- files/exclude/types_or file selection over the pruned filesystem walk
- always_run, fail_fast and the pre-commit stage filter
- extra args appended to a selected system hook's entry (--arg, explicit ids required)
- --fail-fast=0|1 overrides the config's fail_fast (`make pre failfast=0` runs every hook)
- --filter regex runs only the hooks whose id matches (`make pre filter=ruff`)

A hook prints nothing beyond its `[run ( Ns)]` line, which appears as the hook
finishes and carries the seconds it took; a failing hook's full output is shown
too (`-v` streams every hook's output live instead).

Anything outside that subset is rejected loudly instead of silently skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / ".pre-commit-config.yaml"

# Directories never scanned for hook input files (venvs, caches, build output)
PRUNE_DIRS = frozenset(
    {
        ".git",
        ".idea",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".udan_cache",
        ".venv",
        "__pycache__",
        "_build",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "venv",
    }
)

# pre-commit `types_or` tags (identify library) -> file suffixes
TYPE_SUFFIXES = {
    "python": {".py"},
    "markdown": {".md"},
    "yaml": {".yaml", ".yml"},
}


def load_hooks() -> tuple[list[dict], bool]:
    """Load the hook list and fail_fast flag from .pre-commit-config.yaml."""
    config = yaml.safe_load(CONFIG_PATH.read_text())
    hooks = config["hooks"]
    return hooks, bool(config.get("fail_fast", False))


def collect_files() -> list[str]:
    """Return all repo files as relative POSIX paths, pruning cache/venv dirs."""
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(name for name in dirnames if name not in PRUNE_DIRS)
        for filename in sorted(filenames):
            relative = Path(dirpath, filename).relative_to(ROOT)
            files.append(relative.as_posix())
    return sorted(files)


def type_suffixes(hook: dict) -> set[str] | None:
    """Map a hook's types_or tag list to file suffixes; None means all files."""
    tags = hook.get("types_or")
    if tags is None:
        return None
    unknown = [tag for tag in tags if tag not in TYPE_SUFFIXES]
    if unknown:
        known = ", ".join(sorted(TYPE_SUFFIXES))
        raise UnsupportedHook(hook, f"unsupported types_or tags {unknown} (known: {known})")
    return set().union(*(TYPE_SUFFIXES[tag] for tag in tags))


def select_files(files: list[str], hook: dict) -> list[str]:
    """Select the files a hook runs on, mirroring pre-commit's --all-files."""
    suffixes = type_suffixes(hook)
    files_re = re.compile(hook["files"]) if hook.get("files") else None
    exclude_re = re.compile(hook["exclude"]) if hook.get("exclude") else None
    selected = []
    for path in files:
        if suffixes is not None and Path(path).suffix not in suffixes:
            continue
        if files_re is not None and not files_re.search(path):
            continue
        if exclude_re is not None and exclude_re.search(path):
            continue
        selected.append(path)
    return selected


class UnsupportedHook(Exception):
    """Raised for hook declarations the runner cannot emulate."""

    def __init__(self, hook: dict, reason: str) -> None:
        super().__init__(f"hook {hook.get('id')}: {reason}")


def check_supported(hook: dict) -> None:
    """Reject hook declarations outside the emulated pre-commit subset."""
    language = hook.get("language")
    if language == "system":
        return
    if language == "pygrep":
        if hook.get("args"):
            raise UnsupportedHook(hook, "pygrep args are not supported")
        return
    raise UnsupportedHook(hook, f"unsupported language {language!r}")


def stage_matches(hook: dict) -> bool:
    """Check the hook fires for the pre-commit stage (absent stages = all)."""
    stages = hook.get("stages")
    return stages is None or "pre-commit" in stages


def run_pygrep(pattern: str, paths: list[str]) -> bool:
    """Run a pygrep hook: fail when the pattern matches any line of any file."""
    regex = re.compile(pattern)
    found = False
    for path in paths:
        text = (ROOT / path).read_text(errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                print(f"{path}:{lineno}: {line.strip()}")
                found = True
    return not found


def run_hook(hook: dict, paths: list[str], verbose: bool, extra_args: Sequence[str] = ()) -> tuple[bool, str, str]:
    """Run one hook, returning (passed, captured stdout, captured stderr).

    Stdout is captured and only reported on failure, so passing hooks stay
    quiet. Stderr is advisory - a passing hook has something to say there (a
    check degrading because a tree it wants to scan is absent) - so it is shown
    either way. With verbose=True the output streams live and is not captured.
    Extra args are appended to the entry before the file names, mirroring
    pre-commit's entry + args + filenames order.
    """
    check_supported(hook)
    if hook["language"] == "pygrep":
        return run_pygrep(hook["entry"], paths), "", ""
    entry = hook["entry"]
    if extra_args:
        entry = f"{entry} {shlex.join(extra_args)}"
    if hook.get("pass_filenames", True):
        entry = f"{entry} {shlex.join(paths)}"
    if verbose:
        result = subprocess.run(entry, shell=True, cwd=ROOT)
        return result.returncode == 0, "", ""
    result = subprocess.run(
        entry,
        shell=True,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    return result.returncode == 0, result.stdout, result.stderr


def plan_hooks(
    hooks: list[dict],
    ids: list[str],
    skip: re.Pattern[str] | None,
    keep: re.Pattern[str] | None = None,
) -> list[dict]:
    """Filter hooks by explicit ids, the --filter regex and the --skip regex."""
    planned = []
    for hook in hooks:
        if ids and hook["id"] not in ids:
            continue
        if keep is not None and not keep.search(hook["id"]):
            continue
        if skip is not None and skip.search(hook["id"]):
            continue
        planned.append(hook)
    missing = sorted(set(ids) - {hook["id"] for hook in planned})
    if missing:
        known = ", ".join(hook["id"] for hook in hooks)
        raise SystemExit(f"unknown hook id(s): {', '.join(missing)} (known: {known})")
    return planned


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*", help="only run hooks with these ids (default: all)")
    parser.add_argument(
        "--arg",
        action="append",
        metavar="ARG",
        help="extra argument appended to each selected hook's entry, before file names; requires explicit hook ids",
    )
    parser.add_argument("--filter", help="regex: only run hooks whose id matches")
    parser.add_argument("--skip", help="regex: skip hooks whose id matches")
    parser.add_argument(
        "--fail-fast",
        choices=("0", "1"),
        help="override the config's fail_fast: 0 runs every hook and reports all failures, 1 stops at the first",
    )
    parser.add_argument("--list", action="store_true", help="print the plan without running anything")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="stream hook output live (default: show it only on failure)"
    )
    args = parser.parse_args(argv)
    if args.arg and not args.ids:
        parser.error("--arg requires explicit hook ids")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    hooks, config_fail_fast = load_hooks()
    fail_fast = config_fail_fast if args.fail_fast is None else args.fail_fast == "1"
    skip = re.compile(args.skip) if args.skip else None
    keep = re.compile(args.filter) if args.filter else None
    planned = plan_hooks(hooks, args.ids, skip, keep)
    if args.arg:
        pygrep_ids = [hook["id"] for hook in planned if hook["language"] == "pygrep"]
        if pygrep_ids:
            raise SystemExit(f"--arg is not supported for pygrep hook(s): {', '.join(pygrep_ids)}")
    files = collect_files()

    failures: list[str] = []
    started = time.perf_counter()
    for hook in planned:
        reason = None
        if not stage_matches(hook):
            reason = "stage"
        paths = [] if reason else select_files(files, hook)
        if not reason and not paths and not hook.get("always_run", False):
            reason = "no matching files"

        label = f"{hook['id']}: {hook.get('name', '')}"
        if reason:
            print(f"[skip] {label} ({reason})", flush=True)
            continue
        if args.list:
            print(f"[run] {label} ({len(paths)} files)", flush=True)
            continue
        hook_started = time.perf_counter()
        passed, out, err = run_hook(hook, paths, args.verbose, args.arg)
        seconds = round(time.perf_counter() - hook_started)
        print(f"[run {seconds:2d}s] {label} ({len(paths)} files)", flush=True)
        if passed:
            if err.strip():
                print(err.rstrip())
            continue
        output = out + err
        if output.strip():
            print(output.rstrip())
        print(f"[fail] {label}", flush=True)
        failures.append(hook["id"])
        if fail_fast:
            break

    if args.list:
        return 0
    duration = time.perf_counter() - started
    if failures:
        print(f"FAILED: {', '.join(failures)} ({duration:.2f} seconds)")
        return 1
    print(f"All hooks passed ({duration:.2f} seconds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
