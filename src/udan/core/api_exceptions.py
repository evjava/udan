from udan.core.api_forests import ForestBuilder


class ExceptionWithAdvice(Exception):
    def __init__(self, advice):
        self.advice = advice


class OverrideForestException(Exception):
    """Exception raised when introspection should override the normal output flow.

    This exception is used to short-circuit the execution flow when introspection
    tools (help, introspect_tool) are used. Instead of continuing
    through the normal execution pipeline, the exception carries the introspection
    result (forest) directly to the top-level handler for display.

    Attributes:
        forest: The Forest containing introspection results to display
    """

    def __init__(self, forest):
        """Initialize the exception with a forest.

        Args:
            forest: Forest containing introspection results
        """
        self.forest = forest
        super().__init__("Introspection output - see forest attribute")


class TypeCombinationError(OverrideForestException):
    """Exception raised when a tool cannot be combined with the current forest types.

    Raised by TypeSystem.combine when the tool's contract does not fit
    the forest types built so far - a level-creating tool with no data
    source in the chain, where the forest would be empty and the level it
    creates could never exist, or a declared input type no level of the chain
    can provide.

    Extends OverrideForestException so the top-level handler renders the forest
    instead of failing with a traceback. The forest stays flat: the brief type
    conflict and the explanation on the first lines, then each suggestion
    section heading with its entries one level under it.

    Attributes:
        forest: Forest with the type info and the suggestions
        _message: Brief description of the conflicting types
        suggestions: Suggestion sections, heading -> display name -> brief description
    """

    def __init__(
        self, message: str, explanation: str = "", suggestions: dict[str, dict[str, str]] | None = None
    ) -> None:
        """Initialize with the type info and the suggestions that could fix the chain.

        Args:
            message: Brief description of the conflicting types - the first line
            explanation: What to do about it - the second line, before the suggestions
            suggestions: Sections rendered under the explanation,
                heading -> display name -> brief description; empty sections are skipped
        """
        self._message = message
        self.suggestions = suggestions or {}
        builder = ForestBuilder()
        builder.add(message, depth=0)
        if explanation:
            builder.add(explanation, depth=0)
        for heading, entries in self.suggestions.items():
            if not entries:
                continue
            builder.add(heading, depth=0)
            for name, description in entries.items():
                builder.add({"name": name, "description": description}, depth=1)
        super().__init__(builder.build_forest())

    def __str__(self) -> str:
        """Return the type conflict; the explanation and the suggestions live in the forest attribute.

        Returns:
            Brief description of the conflicting types
        """
        return self._message
