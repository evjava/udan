# Vulture whitelist for false positives.
#
# Format (usage-style, NOT definitions):
#   - bare name        -> marks a module-level variable/constant as used
#   - `_.name`         -> marks a method/property/function/attribute as used
#
# Every entry must say WHY the name is not dead code. Delete entries when the
# code they cover is gone - run `make vulture-unused` to check.
#
# Entry points: pre-commit hook and `make vulture-unused` both run
# `vulture src/ .vulture-whitelist.py`; the threshold and decorator ignores
# live in [tool.vulture] in pyproject.toml.

_

# =============================================================================
# Dynamic plugin module contract (scanned via getattr, never imported directly)
# =============================================================================
CONFIG  # plugin config declaration, read by impl_plugins into the plugins snapshot
SUBSCRIBE  # event subscriptions: {event_type: service_type}, wired by UdanContext
PROVIDER  # plugin container contribution, read by impl_plugins, composed by create_udan_container
PLUGIN  # plugin container contribution and its verbs, read by impl_plugins, attached by create_udan_container

# =============================================================================
# Pydantic / pydantic-settings internals
# =============================================================================
model_config  # model configuration, consumed by pydantic
settings_customise_sources  # pydantic-settings settings-source hook

# =============================================================================
# Pydantic model / dataclass fields (data schema, read dynamically)
# =============================================================================
source_operator  # Node provenance: which operator created the node
source_path  # Node provenance: original file path for write-back
hunk_header  # DiffHunk field, part of the git diff schema
author  # GitCommit field, part of the git log schema
short_hash  # GitCommit field, read through the commit-info dict it is built from
from_supported  # RenderDescriptor field, set via model_copy(update={"from_supported": True})
value_old  # simple-setter signature parameter, unused by some setters but fixed by the convention
covered_lines  # coverage output dataclasses, rendered into results
grade  # FunctionComplexity field, set via keyword at construction
calories  # demo vegetables: attribute fields, addressed by name in queries
color
ftype
quantity

# =============================================================================
# Type aliases used in annotations (udan/operator/impl_operator_engine)
# =============================================================================
InserterFn
FilterFn
ExtenderFn
GrouperFn
SorterFn
MapperFn
ReplacerFn

# =============================================================================
# Constants that are part of external/config surface
# =============================================================================
TYPE_ANY  # type vocabulary member; metadata references it as the string "any"
UDAN_DIR_SRC  # path constant

# =============================================================================
# Framework callbacks
# =============================================================================
_.handle_starttag  # HTMLParser overrides
_.handle_endtag
_.handle_data
_.__signature__  # refined signature exposed for FastMCP/pydantic introspection

# =============================================================================
# The plugin framework (src/udan/decompof): the loader's mount/detach are called
# by host applications (the FastAPI decomposition); the rest is udan's own
# container and plugin base, exercised by tests/test_decompof_*
# =============================================================================
mount_plugins  # the loader's entry point: load and attach every named plugin
detach_plugin  # the loader's inverse, for a host that unloads

# =============================================================================
# The boot's shutdown half (impl_ioc): detach_udan_plugins' caller is a host's
# shutdown path, which this repo holds none of - the CLI and the test fixtures
# end their processes without one
# =============================================================================
_._detach_udan_plugins  # detaches the boot's plugins in reverse package order; a host's shutdown calls it

# =============================================================================
# API surface with no caller in src/ (exercised by udan's tests where noted)
# =============================================================================
_.has_variant  # RenderEngineAPI: the frontend-variant read over the render kind's variant axis (tests exercise it)
_.create_exec_context  # UdanContextAPI: the per-query exec context, built beside the engine's own (tests exercise it)
_.prepare_query_state  # UdanContextAPI: the prepared-state flow (resolve, apply, render; no error contract)
_.execute_query_split_debug  # QueryProcessorAPI: execute_query with the debug text split out (tests exercise it)
_.execute_query_state  # QueryProcessorAPI: the state-level execute entry
_.execution_debug_text  # UdanContextAPI: the debug text the split entry returns
_.served_by  # decompof Injector: which container serves the injector, read through the contract
_.get_shared_providers
annotated_dependency  # api_annotated: the registry provider decorator, declared by packages that
                      # keep a provider registry-side; src has none since
                      # history's storages moved into its container contribution
_.unregister_applicator  # OperatorsEngineAPI: the detach of an operator kind's applicator

# =============================================================================
# Package API surface from the 2026-11-06 plugin extraction
# =============================================================================
ATTRIBUTE_TYPE_COMPOSITE  # api_attributes: the attribute_type vocabulary declared whole; the composite kind has no runtime in src yet
fallback  # output_engine_with_renders replaces the core output engine - the seam's original answer is deliberately unused ("replaced, not wrapped")

# =============================================================================
# Deprecated compatibility shims / re-export aliases
# =============================================================================
_.identity  # ToolDescriptor.identity -> .name deprecation shim
extract_injected_args  # backward-compat alias for _extract_injected_args
patch_operator_parameters  # backward-compat alias for _patch_operator_parameters
strip_hidden_args_from_doc  # backward-compat alias for _strip_hidden_args_from_doc

# =============================================================================
# Injector: marker attribute read via getattr, never by literal name
# =============================================================================
_._injector_wrapped  # set on wrapped callables, probed via _INJECTOR_WRAPPED

# =============================================================================
# utils_tables: unwired helper kept for the table-editing feature
# =============================================================================
_._rows_to_tree_pairs  # groups table rows into (depth, item) tree pairs; not yet wired

# =============================================================================
# API implemented for tests / test-suite setup helpers
# (called from tests/conftest.py and test_*.py only)
# =============================================================================
_.get_for_attribute  # exercised by tests
_._size  # attribute cache size, asserted in tests
_._has  # config registry lookup, exercised by tests
_._core_dump  # config registry dump, exercised by tests
_._get_providers_for_plugins  # dependency registry introspection for tests
_._register_dependency_providers_from_module  # UdanContext by-name registration, used by tests
_._set_injectable_types  # loader setup used by tests
_._with_plugins  # UdanContext test-builder used by conftest
_._register_metadata  # UdanContext test-builder used by conftest
_._register_many_metadatas  # UdanContext test-builder used by conftest
_._get_variable  # UdanContext variable access, exercised by tests
_._clear_variables  # UdanContext test cleanup used by tests
_._list_variables  # UdanContext introspection used by tests
_.split_and_normalize  # utils_str helper, exercised by tests
_.flatten  # utils_str helper, exercised by tests (the registry's scan was its last caller)
_.delete  # saved queries API, exercised by tests and tools/delete_saved.py
_.update_tags  # SavedQueriesAPI: the storage contract's retag-by-history-id, exercised by tests
_.update_tags_by_pattern  # SavedQueriesAPI: the storage contract's retag-by-pattern, exercised by tests
_.delete_by_history_id  # SavedQueriesAPI: the storage contract's removal-by-history-id, exercised by tests
_.clear_cache  # attribute cache reset: resolved from the container, called by tests
_.register_parser_extra  # QueryParserAPI: registers a parser extra, applied before the parse; plugin-facing
_.unregister_parser_extra  # QueryParserAPI: removes a registered parser extra; plugin-facing
