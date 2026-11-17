#!/usr/bin/env python3
"""Pre-commit hook to require all Python files in src/udan/ to be tracked by git.

This ensures that new Python files are not left untracked, which could lead to
incomplete commits and broken builds for other developers.
"""

import subprocess
import sys


def get_untracked_python_files(src_dir: str = "src/udan") -> list[str]:
    """Get list of untracked .py files in src_dir.

    Args:
        src_dir: Source directory to check (default: src/udan)

    Returns:
        List of untracked .py file paths
    """
    try:
        # Get list of untracked files in src/udan/
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", src_dir],
            capture_output=True,
            text=True,
            check=True,
        )
        untracked_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        # Filter for .py files only
        return [f for f in untracked_files if f.endswith(".py")]
    except subprocess.CalledProcessError:
        return []


def main() -> int:
    """Main entry point."""
    src_dir = "src/udan"

    untracked_py_files = get_untracked_python_files(src_dir)

    if untracked_py_files:
        print(f"❌ Found {len(untracked_py_files)} untracked Python file(s) in {src_dir}/")
        print()
        print("The following Python files are not tracked by git:")
        for file_path in sorted(untracked_py_files):
            print(f"  - {file_path}")
        print()
        print("Please add these files to git:")
        print("  git add " + " ".join(untracked_py_files))
        print()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
