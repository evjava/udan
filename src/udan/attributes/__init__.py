"""udan.attributes: the attribute domain.

The attribute contracts live beside their implementations here
(api_attribute_contexts, api_attribute_runtime, api_attribute_storage,
api_attribute_cache): the context the walk hands the chain handlers, and the
runtime/storage/cache interfaces. The vocabulary of the kind and its descriptors
stay in the core (udan.core.api_attributes). The package holds the feature surface:
the runtime that computes attributes (the chain step that computes at their chain
position and the whole-forest pass for the rest), the storage the values land in,
the disk cache, the aggregates (plugins_aggregates_attribute) and the
attribute-taking operators. Its container contribution hands the runtime to the
chain routing, the walk's context factory and the injector through decorations.

The package is part of udan, so Plugins discovers it on every boot the way it
discovers udan.operator*: the attribute kind is always in the vocabulary and the
runtime is always in the container. A container built without this package's
provider - a bare IOC() in a test - keeps the core's seams: the walk's context
factory falls back to the store-only dummy, so a chain that names an attribute
fails the walk with "no service handles it", and every other chain - static
structure, operator kinds and renders - runs.
"""
