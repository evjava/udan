"""Simple org-mode file parser.

Parses org files into items with title, date, tags, and content.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

datetime.strptime("2024-01-01", "%Y-%m-%d")  # warmup: https://github.com/pyexcel/pyexcel/issues/180


@dataclass
class OrgItem:
    """An item from an org-mode file."""

    title: str
    date: str
    tags: list[str]
    content: str
    level: int


def parse_date(date_str: str) -> datetime | None:
    """Parse a date string in format DD.MM.YY-HH:MM:SS."""
    try:
        return datetime.strptime(date_str, "%d.%m.%y-%H:%M:%S")
    except ValueError, TypeError:
        return None


def parse_org_file(file_path: str) -> list[OrgItem]:
    """Parse an org-mode file and return a list of items.

    Args:
        file_path: Path to the org file

    Returns:
        List of OrgItem objects
    """
    path = Path(file_path).expanduser()
    if not path.exists():
        return []

    items = []
    current_item = None

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")

            # Check for headline
            if line.startswith("**") or line.startswith("***"):
                # Save previous item
                if current_item:
                    items.append(current_item)

                # Parse level
                level = line.count("*")

                # Parse title (after stars and space)
                title = line.lstrip("*").strip()

                # Initialize new item
                current_item = OrgItem(title=title, date="", tags=[], content="", level=level)

            # Check for properties
            elif line.startswith("date:") and current_item:
                current_item.date = line.split(":", 1)[1].strip()

            elif line.startswith("tags:") and current_item:
                tags_str = line.split(":", 1)[1].strip()
                current_item.tags = [t.strip() for t in tags_str.split(",") if t.strip()]

            # Content line
            elif current_item:
                if current_item.content:
                    current_item.content += "\n" + line
                else:
                    current_item.content = line

    # Save last item
    if current_item:
        items.append(current_item)

    return items
