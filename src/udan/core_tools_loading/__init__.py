"""udan.core_tools_loading: the generic half of the tool machinery.

Everything here is host-agnostic: turning a decorated function into a registered,
cached callable with metadata. The declaration surface (@annotated and
@annotated_dependency, api_annotated), the wire format the sides speak
(api_tools, api_types, api_tool_kinds), the registry that interprets the
loaded tools against the query language (api_tools_registry,
impl_tools_registry), the plugin scanner the boot and the loader read modules
through (io_modules), the signature-to-schema
extraction (io_inspect), the loader with its joblib disk cache
(impl_tools_loader, api_tools_loader,
impl_utils_tools_loader), the kind vocabulary
(impl_tool_kinds), the generic injector that hides a function's
annotated parameters from the descriptors' signature and answers them at call
time (api_function_injector, impl_function_injector) and the small shared helpers (io_fs,
utils_str).

The package's contract is the import rule: nothing here imports udan, only
udan.core_tools_loading and the third-party packages (pydantic, joblib). The udan-specific
half of the plugin scan - the readers that name a udan type - lives in
udan.core.impl_plugins; the injector's udan sources live in
udan.core.impl_udan_injector, composed by the core's container.
"""
