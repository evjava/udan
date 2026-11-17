"""Operators engine: the walk every operator kind's operators go through.

The engine is the package's container contribution. The kind modules (plugins_operator_*)
take it as their provider's dependency and register their applicators into its dispatch at
container build, and this package decorates the chain routing to contribute the handler for an
output-overriding chain - the walk is what applies a chain whole, so the routing has
nobody to hand one to without it. The walk is core: every host composes a container with
operator application and the operator kinds in the vocabulary; what a host can still
leave out is a feature package (attributes, renders, one of the file-format families),
and the chains that need it fail with the advice saying what is missing.
"""

from __future__ import annotations

from udan.core.api_chain_routing import ChainRoutingAPI
from udan.core.api_types_registry import TypesRegistryAPI
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.decompof import Plugin, decorate, provide
from udan.operator.api_operator_engine import OperatorsEngineAPI
from udan.operator.impl_operator_engine import OperatorsEngineImpl


class OperatorsEngine(OperatorsEngineImpl):
    """The package's kind service.

    A kind service declares its KINDS where the container harvests them - a plugin
    package's plugins_*.py modules - and the KINDS themselves live on the contract
    (OperatorsEngineAPI); the walk lives on the base class. The engine declares none:
    every operator kind belongs to the package whose service owns it.
    """


class OperatorPlugin(Plugin):
    """The package's container contribution.

    Providing the engine contributes the walk every kind's applicator is registered
    into. The routing decoration is what makes a chain that overrides its output work:
    the core's chain sequencing recognizes the override through the registry and asks
    the routing to apply it whole, and the routing has this package's engine to hand
    it to only while this package is enabled.
    """

    @provide
    def operator_engine(self, registry: ToolsRegistryAPI, types_registry: TypesRegistryAPI) -> OperatorsEngineAPI:
        """Create the operator engine: the service that applies operator chain steps."""
        return OperatorsEngine(registry=registry, types_registry=types_registry)

    @decorate
    def routing_with_override_handler(self, routing: ChainRoutingAPI, engine: OperatorsEngineAPI) -> ChainRoutingAPI:
        """Hand the walk to the routing as the handler for an output-overriding chain."""
        return routing.with_override_handler(engine)


DOMAIN = "operator"
PLUGIN = OperatorPlugin
