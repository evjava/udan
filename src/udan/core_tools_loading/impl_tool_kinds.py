"""Implementation of the tool kind vocabulary component.

Built filled by the IoC container: the kind services declare the kinds they own as
their `KINDS` (see the ToolKindService subclasses), and the
container registers them when it builds the vocabulary. Plugin kinds arrive through
ToolsRegistry.load_plugins.
"""

from collections.abc import Iterator

from udan.core_tools_loading.api_tool_kinds import ToolKindsRegistryAPI
from udan.core_tools_loading.api_tools import ToolKind


class ToolKindsRegistry(ToolKindsRegistryAPI):
    """The live kind vocabulary: every kind the running container knows."""

    def __init__(self) -> None:
        self._kinds: dict[str, ToolKind] = {}

    def __iter__(self) -> Iterator[str]:
        return iter(self._kinds)

    def __len__(self) -> int:
        return len(self._kinds)

    def __getitem__(self, name: str) -> ToolKind:
        kind = self._kinds.get(name)
        if kind is None:
            registered = ", ".join(self._kinds)
            raise KeyError(f"Unknown tool kind: {name!r}. Registered kinds: {registered}")
        return kind

    def __repr__(self) -> str:
        """Readable listing of the registered kind names."""
        return f"ToolKindsRegistry({', '.join(self._kinds)})"

    def default_kind(self) -> ToolKind | None:
        """The registered kind that declares itself the default, or None."""
        return next((kind for kind in self._kinds.values() if kind.is_default), None)

    def register(self, kind: ToolKind) -> ToolKind:
        """Register a kind, filling in what an earlier registration left open.

        Registration is additive: a kind already known keeps its fields and takes over
        the ones the incoming kind sets, so the same kind can be registered again (a
        second container, a plugin re-declaring a built-in) without losing anything.

        Args:
            kind: The kind to register

        Returns:
            The stored kind (the merged one when the kind was already known)

        Raises:
            ValueError: If the kind contradicts a field already set for its name
        """
        existing = self._kinds.get(kind.name)
        if existing is None:
            self._kinds[kind.name] = kind
            return kind
        merged = self._merge(existing, kind)
        self._kinds[kind.name] = merged
        return merged

    def _merge(self, base: ToolKind, extra: ToolKind) -> ToolKind:
        """Fill the fields `extra` sets that `base` left at their default.

        Args:
            base: The kind already registered under this name
            extra: The incoming kind of the same name

        Returns:
            The base kind with the incoming fields filled in

        Raises:
            ValueError: If a field both kinds set disagrees
        """
        updates: dict[str, object] = {}
        for field_name, field in ToolKind.model_fields.items():
            new_value = extra.__dict__[field_name]
            old_value = base.__dict__[field_name]
            if new_value == old_value:
                continue  # the two kinds agree on this field
            if old_value != field.default:
                raise ValueError(
                    f"Conflicting ToolKind for kind {base.name!r}: field {field_name!r} "
                    f"is already {old_value!r}, refusing {new_value!r}"
                )
            updates[field_name] = new_value
        return base.model_copy(update=updates) if updates else base
