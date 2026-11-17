"""Public API for type checking and classification.

This module defines the public API interface for checking item types.
"""

from __future__ import annotations


class TypesRegistryAPI:
    """API interface for item classification.

    The one classification every reader shares: is a forest item data, or a chain
    item (a tool descriptor of some kind). Which kinds of chain item there
    are is the kinds' business, and the consumers that tell them apart import the
    descriptor types they apply.
    """

    def is_chain_item(self, item: object) -> bool:
        """Check if an item is a tool descriptor: a chain item, not data.

        The classification the chain sequencing is built on: a resolved forest child
        is either a chain item of some kind (a tool descriptor, an
        descriptor of the chain) or data - a literal, a spliced
        item, a group. A chain item that reaches a consumer that applies only its own
        kinds (a variable expanded as a value) is not data and must be skipped there.

        Args:
            item: Item to classify

        Returns:
            True if the item is a tool descriptor
        """
        raise NotImplementedError
