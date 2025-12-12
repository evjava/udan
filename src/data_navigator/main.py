#!/usr/bin/env python3
"""Main script for data navigator."""

import sys
import os
from pathlib import Path


def list_directory_files(directory_path: str) -> list[str]:
    """
    List all files in a directory.
    
    Args:
        directory_path: Path to the directory
        
    Returns:
        List of file names in the directory
    """
    try:
        path = Path(directory_path)
        if not path.exists():
            raise FileNotFoundError(f"Path '{directory_path}' does not exist.")
        
        if not path.is_dir():
            raise NotADirectoryError(f"'{directory_path}' is not a directory.")
        
        # Return list of files (not directories)
        files = [item.name for item in path.iterdir() if item.is_file()]
        return sorted(files)
    
    except PermissionError:
        raise PermissionError(f"Permission denied to access '{directory_path}'.")
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        raise
    except Exception as e:
        raise RuntimeError(f"Error: {e}")


def main(query: str) -> str:
    """
    Main function that processes a query and returns a result string.
    
    Args:
        query: The query string (directory path)
        
    Returns:
        String containing the result (list of files, one per line, or error message)
    """
    # Check if query is a directory
    if not os.path.isdir(query):
        return f"Error: '{query}' is not a directory."
    
    try:
        files = list_directory_files(query)
        return "\n".join(files)
    except (FileNotFoundError, NotADirectoryError, PermissionError, RuntimeError) as e:
        return f"Error: {e}"


def main_io():
    """Main I/O function that reads arguments and prints results."""
    if len(sys.argv) < 2:
        print("Usage: python main.py <query>", file=sys.stderr)
        sys.exit(1)
    
    query = sys.argv[1]
    result = main(query)
    print(result)


if __name__ == "__main__":
    main_io()

