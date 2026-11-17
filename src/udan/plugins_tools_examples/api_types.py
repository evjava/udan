"""The source-analysis item type.

``ASTChunk`` is the item type the code extractors answer with: a function,
class or other code element parsed out of a source file. It lives in this
package because the core families consume it: ``plugins_dev`` extracts it
from Python sources with tree-sitter queries, and ``plugins_org`` /
``plugins_markdown`` render it.
"""

from dataclasses import dataclass
from functools import total_ordering


@total_ordering
@dataclass(frozen=True)
class ASTChunk:
    """A chunk of code extracted from AST.

    Represents a function, class, or other code element extracted from
    Python source code via AST parsing.
    """

    name: str
    type: str  # "function", "class", "method", etc.
    docstring: str
    source_file: str
    line_start_number: int
    line_end_number: int  # inclusive
    full_code: str

    def __lt__(self, other):
        if not isinstance(other, ASTChunk):
            return NotImplemented
        return (self.source_file, self.line_start_number) < (other.source_file, other.line_start_number)
