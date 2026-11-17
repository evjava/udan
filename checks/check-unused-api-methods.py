#!/usr/bin/env python3
"""Pre-commit hook to detect API methods never called outside their implementation.

The rule: a method declared on a *API interface is part of the public contract
only if something other than the implementation itself calls it. A method
reachable only from inside the implementation is a private helper, so its entry
in the interface is dead surface and the interface misstates what the dependency
is for.

What is flagged (historical case RenderSpecHandlerAPI.get_expected_render_args,
since removed along with its module):

    src/udan/core/api_render_spec_handler.py:23: RenderSpecHandlerAPI.get_expected_render_args

    RenderSpecHandler.get_expected_render_args is only ever reached through
    `self.get_expected_render_args(...)` inside impl_render_spec_handler.py,
    plus a unit test. Nothing outside the implementation calls it, so the
    interface entry is dead.

What is not flagged (QueryProcessorAPI.resolve_query):

    impl_udan_context.py stores `self._query_processor: QueryProcessorAPI` and
    calls `self._query_processor.resolve_query(...)` - a real call through the
    interface from another module.

What is also not flagged (OperatorsEngineAPI.resolve_typed_variable_arguments):

    impl_operators_engine.py holds both the implementer (OperatorsEngine) and a
    consumer of it (OperatorImpl), and OperatorImpl calls
    `self.operator_engine.resolve_typed_variable_arguments(...)`. Sharing a file
    with the implementation does not make a call internal: the receiver is a
    separate object, reached through the interface.

So the line is drawn on the receiver, not the file. A call through `self`/`cls`
of a class implementing the interface is the implementation reaching its own
contract and does not count. A call on any other object counts.

Tests are never counted as usage: a test exercising an interface method nobody
else calls is testing dead code.

The fix: drop the entry from the interface and rename the implementation method
with a leading underscore - a method that is not in the API is protected, not
public - or call the method through the interface from somewhere real.

Receiver types are resolved from annotations so that same-named methods on
unrelated classes (`dict.get`, `Node.create`) are not mistaken for interface
calls. When a receiver's type cannot be determined the call is counted as
usage, so a method that might be alive is never flagged.

Inherited methods are credited to the interface that declares them: a caller
holding ExecContextAPI and calling `ctx.debug(...)` counts as usage of
LoggerAPI.debug. A method may be reachable only through another interface
method that is itself alive (`try_handle_render_spec` calls
`get_expected_render_args` internally) - that is reported too, because the
point at issue is the interface surface, not whether the code runs.

EXCLUSIONS_ADHOC holds methods known to be unused but not yet removed. Keys are
("Interface", "method") pairs copied from the report. They are debt to be
resolved, not permissions: shrink them, never grow them.
"""

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SRC_DIR = Path("src")  # includes udan_plugins_* packages: they call API methods too

# ("Interface", "method") pairs that are unused outside their implementation.
# Keep entries minimal and comment why the surface is intentionally kept.
EXCLUSIONS_ADHOC: set[tuple[str, str]] = {
    # cache invalidation has no production caller in src/; tests resolve the cache
    # from the container and clear it to reset state between runs. Part of the
    # cache's own contract (get_value/set_value/clear_cache), not dead surface.
    ("AttributeCacheAPI", "clear_cache"),
    # the stage-level aggregate entry: reached only through the runtime's own
    # apply_chain_step, which dispatches to it by attribute_type - the per-stage
    # counterpart of the forest-level calculate_attributes_in_forest, and the entry
    # the chain design (2026-11-04--20-09-29--computation-mechanics-refinement.md)
    # declares on the API for callers outside the runtime.
    ("AttributeRuntimeAPI", "calculate_aggregate_attributes"),
    # saved queries removal-by-pattern has no production caller in src/
    # (tools/delete_saved.py and tests use it); kept as part of the saved
    # queries storage API alongside list/add.
    ("SavedQueriesAPI", "delete"),
    # the saved-queries storage's write side (tags by history id, tags by
    # pattern, removal by history id): the storage contract beside
    # list/add/delete, exercised by the storage tests
    # (tests/udan/plugins_history/test_impl_saved.py).
    ("SavedQueriesAPI", "update_tags"),
    ("SavedQueriesAPI", "update_tags_by_pattern"),
    ("SavedQueriesAPI", "delete_by_history_id"),
    # The context's prepared-state flow (resolve, apply, render; no error
    # contract): the state-level counterpart of execute_query, taking an
    # already-parsed node.
    ("UdanContextAPI", "prepare_query_state"),
    # the context's engine half, once reached by the query pipeline the context
    # absorbed (UDAN-460, 2026-11-11): execute_query is now the composition's
    # caller in src/, and the state-level entries remain the context's public
    # contract beside it.
    ("UdanContextAPI", "apply_state"),
    ("UdanContextAPI", "run_state"),
    # the registry's non-CLI provider read: the plugins_only providers - the
    # ones that need the CLI - stay out (see get_shared_providers).
    ("DependenciesRegistryAPI", "get_shared_providers"),
    # the context's own accessor: reached only inside impl_udan_context.py; the
    # UdanContext facade is its public read.
    # attribute_runtime, once excluded alongside it, left the context with the
    # attributes-out-of-core extraction (2026-11-06).
    ("UdanContextAPI", "registry"),
    # the inverse of register_applicator: src/ registers applicators only at
    # container build, and that build has no teardown, so src/ never calls it.
    ("OperatorsEngineAPI", "unregister_applicator"),
    # the inverse of load_core's subscription wiring: unwinding the bus the
    # boot wired (with the plugins' detach).
    ("UdanContextAPI", "detach"),
    # the frontend-variant read of the render engine, over the render kind's
    # own variant axis (RENDER.variant_meta_key); reached in src/ only inside
    # the implementation.
    ("RenderEngineAPI", "has_variant"),
    # the forest+contexts form of applying operators: the engine recurses into it
    # while expanding TYPE_QUERY-typed variable arguments
    # (impl_operator_engine.py), and no other src/ caller exists.
    ("OperatorsEngineAPI", "apply_operators_with_contexts"),
    # debt from the 2026-11-06 plugin extraction (udan_plugins_attributes): the
    # typed attribute-domain read, answered only by the implementation's own
    # core-contract bridge - get_requested() (ChainContextAPI, called by the
    # walk) delegates to it in impl_attribute_runtime.py. The fix is dropping the
    # entry from AttributesContextAPI, not finding it a caller.
    ("AttributesContextAPI", "get_requested_attributes"),
    # debt from the 2026-11-06 plugin extraction (udan.renders, now udan/renders): the
    # render-domain form of the output seam, answered only by the implementation's
    # own output_forest() (OutputEngineAPI, called by the core), which delegates
    # to it in impl_render_engine.py; tests reach rendering through output_forest
    # too. The fix is dropping the entry from RenderEngineAPI.
    ("RenderEngineAPI", "render_forest"),
    # the query extras' registration surface (2026-11-11, UDAN-449): the parser's
    # extras are registered by plugins - a plugin package's PLUGIN attach - and
    # src/ never registers any; tests stand in for those callers
    # (tests/udan/parsing/test_query_extras.py). The unregister half is the
    # inverse of the register half, like OperatorsEngineAPI.unregister_applicator.
    # (The processor's half left with UDAN-452: the question sugar wraps the
    # running resolver through the plugin's decorator instead of registering.)
    ("QueryParserAPI", "register_parser_extra"),
    ("QueryParserAPI", "unregister_parser_extra"),
}


@dataclass
class ClassInfo:
    """Everything the resolver needs to know about one class."""

    name: str
    module: str
    bases: list[str] = field(default_factory=list)
    declared: set[str] = field(default_factory=set)
    # attribute name -> type names it may hold
    fields: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # method/property name -> type names it may return
    returns: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @property
    def is_api(self) -> bool:
        """True when the class name follows the *API interface convention."""
        return self.name.endswith("API")


def annotation_names(node: ast.AST | None) -> set[str]:
    """Collect the simple type names an annotation mentions.

    Unwraps `X`, `module.X`, `X[...]`, `X | None` and `Optional[X]`, so that the
    pervasive `ctx: ExecContextAPI | None = None` form resolves to ExecContextAPI.

    Args:
        node: Annotation node, or None

    Returns:
        Set of simple names; empty when nothing recognizable is present
    """
    if node is None or isinstance(node, ast.Constant):
        return set()
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return {node.attr}
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return annotation_names(node.left) | annotation_names(node.right)
    if isinstance(node, ast.Subscript):
        return annotation_names(node.value) | annotation_names(node.slice)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        names: set[str] = set()
        for elt in node.elts:
            names |= annotation_names(elt)
        return names
    return set()


class Registry:
    """Cross-module map of classes, used to resolve receiver types."""

    def __init__(self) -> None:
        self.classes: dict[str, ClassInfo] = {}
        self.api_declarations: dict[tuple[str, str], tuple[Path, int]] = {}

    def load(self, src_dir: Path) -> None:
        """Parse every module under src_dir and index its classes.

        Args:
            src_dir: Directory holding the package (e.g. src/udan)
        """
        for path in sorted(src_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except (SyntaxError, OSError, UnicodeDecodeError) as e:
                print(f"skipping {path}: {e}", file=sys.stderr)
                continue

            module = module_name(src_dir, path)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    info = self.classes.setdefault(node.name, ClassInfo(node.name, module))
                    info.bases = [base for base in (_base_name(b) for b in node.bases) if base]
                    self._index_class(info, node)
                    if info.is_api:
                        self._index_api_methods(info, path, node)

    def _index_class(self, info: ClassInfo, node: ast.ClassDef) -> None:
        """Record a class's fields and method return types.

        Field types come from explicit annotations (`self._x: T = ...`, class-level
        `x: T`) and from the dominant convention of assigning an annotated
        constructor parameter straight onto the instance (`self._x = x`).

        Args:
            info: Class info to fill in
            node: Class definition node
        """
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                info.fields[item.target.id] |= annotation_names(item.annotation)
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            info.declared.add(item.name)
            if item.returns is not None:
                info.returns[item.name] |= annotation_names(item.returns)
            params = _param_annotations(item)
            for sub in ast.walk(item):
                target = getattr(sub, "target", None)
                if not isinstance(sub, (ast.Assign, ast.AnnAssign)):
                    continue
                if not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    continue
                if isinstance(sub, ast.AnnAssign):
                    info.fields[target.attr] |= annotation_names(sub.annotation)
                elif isinstance(sub.value, ast.Name) and sub.value.id in params:
                    info.fields[target.attr] |= params[sub.value.id]

    def _index_api_methods(self, info: ClassInfo, path: Path, node: ast.ClassDef) -> None:
        """Record where an interface declares each of its methods.

        Args:
            info: Class info for the interface
            path: File the interface is declared in
            node: Class definition node
        """
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("__"):
                self.api_declarations[(info.name, item.name)] = (path, item.lineno)

    def ancestors(self, name: str) -> set[str]:
        """Return a class and every base it inherits from, transitively.

        Args:
            name: Class name to start from

        Returns:
            Set of class names including `name` itself
        """
        seen: set[str] = set()
        stack = [name]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            info = self.classes.get(current)
            if info:
                stack.extend(b for b in info.bases if b not in seen)
        return seen

    def implementer_modules(self, api_name: str) -> set[str]:
        """Return the modules that implement an interface.

        A module implements an interface when it holds a concrete (non-*API)
        class inheriting from it. Interfaces inheriting other interfaces do not
        count, so ExecContextAPI(LoggerAPI) does not make api_exec_context.py an
        implementation of LoggerAPI.

        Args:
            api_name: Interface name (e.g. "RenderSpecHandlerAPI")

        Returns:
            Set of module names (e.g. {"udan.core.impl_render_spec_handler"})
        """
        modules: set[str] = set()
        for name, info in self.classes.items():
            if info.is_api:
                continue
            if api_name in self.ancestors(name):
                modules.add(info.module)
        return modules

    def apis_declaring(self, method: str, receiver_types: set[str]) -> set[str]:
        """Return the interfaces that declare `method` for a given receiver.

        Args:
            method: Method name being accessed
            receiver_types: Types the receiver resolved to; empty when unknown

        Returns:
            Interface names declaring the method. An unknown receiver credits
            every interface declaring the method, so an unresolved call is never
            allowed to make a method look dead.
        """
        if receiver_types:
            hierarchy: set[str] = set()
            for type_name in receiver_types:
                hierarchy |= self.ancestors(type_name)
            return {
                name
                for name in hierarchy
                if name in self.classes and self.classes[name].is_api and method in self.classes[name].declared
            }
        return {name for name, info in self.classes.items() if info.is_api and method in info.declared}


def _base_name(node: ast.AST) -> str | None:
    """Return the simple name of a base class expression.

    Args:
        node: Base class expression

    Returns:
        Simple name, or None when it is not a plain name
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _param_annotations(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, set[str]]:
    """Map a function's parameter names to the types they are annotated with.

    Args:
        node: Function definition node

    Returns:
        Dict of parameter name to type names; unannotated params map to empty
    """
    args = node.args
    positional = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    extra = [a for a in (args.vararg, args.kwarg) if a]
    return {a.arg: annotation_names(a.annotation) for a in [*positional, *extra]}


def _scope_for(node: ast.FunctionDef | ast.AsyncFunctionDef, class_name: str | None) -> dict[str, set[str]]:
    """Build the initial name -> types mapping for a function body.

    Args:
        node: Function definition node
        class_name: Enclosing class name, or None for module-level functions

    Returns:
        Dict of variable name to type names
    """
    scope = _param_annotations(node)
    if class_name:
        scope["self"] = {class_name}
        scope["cls"] = {class_name}
    return scope


class CallScanner(ast.NodeVisitor):
    """Collects interface methods referenced from one function body."""

    def __init__(
        self,
        registry: Registry,
        used: set[tuple[str, str]],
        scope: dict[str, set[str]],
        class_name: str | None,
    ) -> None:
        self.registry = registry
        self.used = used
        self.scope = scope
        self.class_name = class_name

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Recurse into nested functions with their own parameter scope.

        Args:
            node: Nested function definition
        """
        nested = CallScanner(self.registry, self.used, _scope_for(node, None), self.class_name)
        for stmt in node.body:
            nested.visit(stmt)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        """Record `recv.method(...)` calls.

        Args:
            node: Call node
        """
        if isinstance(node.func, ast.Attribute):
            self._record(node.func)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Record a bare method reference, e.g. one passed as a callback.

        Args:
            node: Attribute node
        """
        if isinstance(node.ctx, ast.Load):
            self._record(node)
        self.generic_visit(node)

    def _record(self, attr: ast.Attribute) -> None:
        """Credit the referenced method to every interface declaring it.

        A class calling a method of its own contract through `self` does not
        count: that is the implementation reaching itself, which is exactly what
        this hook looks for. Calling it on any other object does count, even when
        that object is another instance of the same implementation held in the
        same file - e.g. `self.operator_engine.resolve_typed_variable_arguments(...)`
        inside OperatorImpl.

        Args:
            attr: Attribute node holding the method access
        """
        own_hierarchy = self._own_hierarchy(attr.value)
        receiver_types = self.resolve(attr.value)
        for api_name in self.registry.apis_declaring(attr.attr, receiver_types):
            if api_name in own_hierarchy:
                continue
            self.used.add((api_name, attr.attr))

    def _own_hierarchy(self, receiver: ast.AST) -> set[str]:
        """Return the interfaces of the receiver's own class, for `self`/`cls`.

        Args:
            receiver: Receiver expression of the method access

        Returns:
            Set of interface names the enclosing class implements; empty when the
            receiver is not `self`/`cls` or there is no enclosing class
        """
        if not (isinstance(receiver, ast.Name) and receiver.id in ("self", "cls")):
            return set()
        if self.class_name is None:
            return set()
        return {
            name
            for name in self.registry.ancestors(self.class_name)
            if name in self.registry.classes and self.registry.classes[name].is_api
        }

    def resolve(self, node: ast.AST) -> set[str]:
        """Resolve an expression to the type names it may hold.

        Args:
            node: Expression node

        Returns:
            Set of type names; empty when the type cannot be determined
        """
        if isinstance(node, ast.Name):
            return self.scope.get(node.id, set())
        if isinstance(node, ast.Attribute):
            types: set[str] = set()
            for type_name in self.resolve(node.value):
                info = self.registry.classes.get(type_name)
                if info:
                    types |= info.fields.get(node.attr, set())
                    types |= info.returns.get(node.attr, set())
            return types
        if isinstance(node, ast.Call):
            return self.resolve(node.func)
        return set()


def module_name(src_dir: Path, path: Path) -> str:
    """Return the dotted module name of a file inside the package.

    Args:
        src_dir: Directory holding the package (e.g. src/udan)
        path: File inside that directory

    Returns:
        Dotted module name (e.g. "udan.plugins_history.api_history")
    """
    parts = path.relative_to(src_dir).with_suffix("").parts
    return ".".join((src_dir.name, *parts))


def collect_usage(registry: Registry, src_dir: Path) -> set[tuple[str, str]]:
    """Walk every module and collect the interface methods it uses.

    Args:
        registry: Class index built by Registry.load
        src_dir: Directory holding the package

    Returns:
        Set of (interface, method) pairs referenced from outside their own
        implementation
    """
    used: set[tuple[str, str]] = set()
    for path in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except (SyntaxError, OSError, UnicodeDecodeError) as e:
            print(f"skipping {path}: {e}", file=sys.stderr)
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                class_name = _enclosing_class(tree, node)
                scanner = CallScanner(registry, used, _scope_for(node, class_name), class_name)
                for stmt in node.body:
                    scanner.visit(stmt)
    return used


def _enclosing_class(tree: ast.AST, func: ast.AST) -> str | None:
    """Find the class a function is defined in.

    Args:
        tree: Module tree containing the function
        func: Function definition node

    Returns:
        Class name, or None for module-level functions
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if item is func:
                return node.name
    return None


def main() -> int:
    """Report interface methods that no module outside their implementation calls.

    Returns:
        1 when violations are found, 0 otherwise
    """
    if not SRC_DIR.exists():
        print(f"Error: {SRC_DIR} not found", file=sys.stderr)
        return 1

    registry = Registry()
    registry.load(SRC_DIR)
    used = collect_usage(registry, SRC_DIR)

    violations = []
    for (api_name, method), (path, lineno) in sorted(registry.api_declarations.items()):
        if (api_name, method) in EXCLUSIONS_ADHOC:
            continue
        if (api_name, method) in used:
            continue
        if registry.implementer_modules(api_name):
            violations.append((api_name, method, path, lineno))

    if violations:
        report = []
        for api_name, method, path, lineno in violations:
            report.append(f"{path}:{lineno}: {api_name}.{method} is never called outside its implementation")
            report.append(
                "  Only the implementing module (and tests) reach it, so the interface entry is dead surface."
            )
            report.append(
                f"  Tip: drop the entry from {api_name} and rename the impl method with a leading underscore,"
            )
            report.append("  since a method that is not in the API is protected, not public.")
            report.append("  Or keep the entry and call it through the interface somewhere real.")
        report.append(f"\n{len(violations)} violation(s) found.")
        print("\n".join(report))
        return 1

    declared = set(registry.api_declarations)
    stale = EXCLUSIONS_ADHOC - declared
    if stale:
        print("Warning: stale exclusions (the interface method no longer exists):")
        for entry in sorted(stale):
            print(f"  ('{entry[0]}', '{entry[1]}')")
        return 1

    print(f"OK: {len(declared)} interface methods, all used outside their implementation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
