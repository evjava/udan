#!/usr/bin/env python3
"""Pre-commit hook to detect public methods that exist only on an implementation.

The rule: `api_*` files define interfaces and `impl_*` files implement them, so a
concrete class that implements a `*API` interface may not invent public surface
of its own. A method reachable from outside the implementation is part of the
contract and must be declared on the interface; a method only the implementation
itself reaches is a helper and must be named with a leading underscore. Anything
else leaves the interface understating what the dependency actually offers, and
callers end up holding an object they cannot type against.

What is flagged (historical case ToolsRegistry.register_parser, since
renamed - the interface never declared it):

    src/udan/core/impl_tools_registry.py:578: ToolsRegistry.register_parser

    Only `register()` reached it, from the same file, so it was an internal step
    of registration and became `_register_parser`.

What is flagged the other way (AttributeRuntime.calculate_attribute_descriptor_in_node):

    Reached as `context.attribute_runtime.calculate_attribute_descriptor_in_node(...)`
    from a caller holding the interface, so the method is contract, not helper -
    the fix is declaring it on AttributeRuntimeAPI, not hiding it.

What is not flagged:

    Properties and their setters. `UdanContext.config` is an accessor over
    injected state, and check-no-properties-in-api.py already keeps properties
    off the interfaces; an accessor the interface deliberately omits is not a
    missing method.

Not flagged either are methods the interface already declares, however far up
the hierarchy they sit - the check is against the union of every `*API` ancestor.

The line is drawn on the receiver, not the file, and tests are never counted as
usage: a method only tests reach is not public. Receiver types come from
annotations so that same-named methods on unrelated classes (`dict.get`,
`Node.create`) are not mistaken for cross-implementation calls; an undecidable
receiver counts as external usage, so a method that might be contract is never
quietly renamed.

EXCLUSIONS_ADHOC holds ("Class", "method") pairs that violate the rule today.
They are debt to be resolved, not permissions: shrink them, never grow them.
"""

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

SRC_DIR = Path("src/udan")

# ("Class", "method") pairs that are public on an implementation but absent from
# the interface it implements.
EXCLUSIONS_ADHOC: set[tuple[str, str]] = set()


@dataclass
class ClassInfo:
    """Everything the resolver needs to know about one class."""

    name: str
    module: str
    path: Path
    lineno: int
    bases: list[str] = field(default_factory=list)
    declared: set[str] = field(default_factory=set)
    # declared names that are @property accessors rather than methods
    accessors: set[str] = field(default_factory=set)
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

    Unwraps `X`, `module.X`, `X[...]`, `X | None` and `Optional[X]`.

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


def module_name(src_dir: Path, path: Path) -> str:
    """Return the dotted module name of a file inside the package.

    Args:
        src_dir: Directory holding the package (e.g. src/udan)
        path: File inside that directory

    Returns:
        Dotted module name (e.g. "udan.core.impl_tools_registry")
    """
    parts = path.relative_to(src_dir).with_suffix("").parts
    return ".".join((src_dir.name, *parts))


def _is_accessor(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Tell whether a def is a property accessor rather than a method.

    Args:
        node: Function definition node

    Returns:
        True for @property and for the @x.setter / @x.deleter companions
    """
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in ("property", "cached_property"):
            return True
        # The setter/deleter of a property is decorated as `<name>.setter`.
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter"):
            return True
    return False


class Registry:
    """Cross-module map of classes, used to resolve receiver types."""

    def __init__(self) -> None:
        self.classes: dict[str, ClassInfo] = {}

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
                if not isinstance(node, ast.ClassDef):
                    continue
                info = self.classes.setdefault(node.name, ClassInfo(node.name, module, path, node.lineno))
                info.bases = [base for base in (_base_name(b) for b in node.bases) if base]
                self._index_class(info, node)

    def _index_class(self, info: ClassInfo, node: ast.ClassDef) -> None:
        """Record a class's fields and declared methods.

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
            if _is_accessor(item):
                info.accessors.add(item.name)
            if item.returns is not None:
                info.returns[item.name] |= annotation_names(item.returns)
            params = _param_annotations(item)
            for sub in ast.walk(item):
                if isinstance(sub, ast.AnnAssign):
                    targets = [sub.target]
                elif isinstance(sub, ast.Assign):
                    targets = sub.targets
                else:
                    continue
                for target in targets:
                    self._index_self_assignment(info, sub, target, params)

    def _index_self_assignment(
        self,
        info: ClassInfo,
        sub: ast.AnnAssign | ast.Assign,
        target: ast.AST,
        params: dict[str, set[str]],
    ) -> None:
        """Record the type of one `self.<attr> = ...` assignment.

        Args:
            info: Class info to fill in
            sub: The assignment node
            target: Assignment target, expected to be `self.<attr>`
            params: Constructor/parameter annotations for inferring untyped assignments
        """
        if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self"):
            return
        if isinstance(sub, ast.AnnAssign):
            info.fields[target.attr] |= annotation_names(sub.annotation)
        elif isinstance(sub.value, ast.Name) and sub.value.id in params:
            info.fields[target.attr] |= params[sub.value.id]

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

    def api_ancestors(self, name: str) -> set[str]:
        """Return the interfaces a class implements.

        Args:
            name: Class name

        Returns:
            Set of `*API` names among the class and its ancestors
        """
        return {
            ancestor for ancestor in self.ancestors(name) if ancestor in self.classes and self.classes[ancestor].is_api
        }

    def implementer_modules(self, class_name: str) -> set[str]:
        """Return the modules that hold a concrete implementation of a class.

        Args:
            class_name: Class whose implementing modules are wanted

        Returns:
            Set of module names (e.g. {"udan.core.impl_tools_registry"})
        """
        return {
            info.module for name, info in self.classes.items() if class_name in self.ancestors(name) and not info.is_api
        }


class UsageScanner(ast.NodeVisitor):
    """Collects which implementation methods are reached from outside their class."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        # (class_name, method) -> set of modules reaching it from another class
        self.external: dict[tuple[str, str], set[str]] = defaultdict(set)
        # (class_name, method) reached only through self/cls of the same class
        self.internal: set[tuple[str, str]] = set()

    def scan(self, src_dir: Path) -> None:
        """Walk every module and record receiver-resolved method accesses.

        Args:
            src_dir: Directory holding the package
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
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                class_name = _enclosing_class(tree, node)
                self._scan_function(node, module, class_name)

    def _scan_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, module: str, class_name: str | None) -> None:
        """Record method accesses in one function body.

        Args:
            node: Function definition node
            module: Module the function lives in
            class_name: Enclosing class name, or None
        """
        scope = _scope_for(node, class_name)
        for sub in ast.walk(node):
            if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)):
                continue
            self._record(sub.func, module, class_name, scope)

    def _record(self, attr: ast.Attribute, module: str, class_name: str | None, scope: dict[str, set[str]]) -> None:
        """Credit a method access to the classes its receiver may hold.

        A call through `self`/`cls` of the enclosing class is the implementation
        reaching itself and is not usage. Calling it on any other object counts,
        even when the receiver is another instance of the same implementation.

        An undecidable receiver credits every class declaring the method: that
        over-credits, but the alternative is reading contract as helper and
        renaming a method callers depend on.

        Args:
            attr: Attribute node holding the method access
            module: Module the access appears in
            class_name: Enclosing class name, or None
            scope: Variable name to type names for the enclosing body
        """
        receiver_types = self._resolve(attr.value, scope)
        if not receiver_types:
            receiver_types = {name for name, info in self.registry.classes.items() if attr.attr in info.declared}
        own_hierarchy = set()
        if class_name and isinstance(attr.value, ast.Name) and attr.value.id in ("self", "cls"):
            own_hierarchy = self.registry.ancestors(class_name)
        for type_name in receiver_types:
            info = self.registry.classes.get(type_name)
            if info is None or attr.attr not in info.declared:
                continue
            key = (type_name, attr.attr)
            if type_name in own_hierarchy:
                self.internal.add(key)
                continue
            self.external[key].add(module)

    def _resolve(self, node: ast.AST, scope: dict[str, set[str]]) -> set[str]:
        """Resolve an expression to the type names it may hold.

        Args:
            node: Expression node
            scope: Variable name to type names for the enclosing body

        Returns:
            Set of type names; empty when the type cannot be determined
        """
        if isinstance(node, ast.Name):
            return scope.get(node.id, set())
        if isinstance(node, ast.Attribute):
            types: set[str] = set()
            for type_name in self._resolve(node.value, scope):
                info = self.registry.classes.get(type_name)
                if info:
                    types |= info.fields.get(node.attr, set())
                    types |= info.returns.get(node.attr, set())
            return types
        if isinstance(node, ast.Call):
            return self._resolve(node.func, scope)
        return set()


@dataclass
class Violation:
    """One public method that its interface does not declare."""

    class_name: str
    method: str
    path: Path
    lineno: int
    api_ancestors: list[str]
    # modules reaching the method from outside its own class
    external_modules: set[str]

    @property
    def is_used_externally(self) -> bool:
        """True when something other than the implementation itself reaches it."""
        return bool(self.external_modules)

    def fix(self) -> str:
        """Return the fix this violation calls for.

        Returns:
            "declare on the interface" when the method is contract, otherwise
            "rename with a leading underscore" when it is a private helper
        """
        if self.is_used_externally:
            return "declare it on the interface"
        return "rename it with a leading underscore"


def find_violations(registry: Registry, usage: UsageScanner) -> list[Violation]:
    """Find public methods on implementing classes that no interface declares.

    Args:
        registry: Class index built by Registry.load
        usage: Receiver-resolved accesses collected by UsageScanner

    Returns:
        Violations sorted by file and line
    """
    found: list[Violation] = []
    for info in registry.classes.values():
        if info.is_api:
            continue
        api_ancestors = registry.api_ancestors(info.name)
        if not api_ancestors:
            continue
        api_methods: set[str] = set()
        for ancestor in api_ancestors:
            api_methods |= registry.classes[ancestor].declared
        for method in sorted(info.declared):
            if method.startswith("_") or method in info.accessors or method in api_methods:
                continue
            if (info.name, method) in EXCLUSIONS_ADHOC:
                continue
            found.append(
                Violation(
                    class_name=info.name,
                    method=method,
                    path=info.path,
                    lineno=info.lineno,
                    api_ancestors=sorted(api_ancestors),
                    external_modules=set(usage.external.get((info.name, method), set())),
                )
            )
    return sorted(found, key=lambda v: (str(v.path), v.lineno))


def main() -> int:
    """Report public methods that an implementation declares but its interface does not.

    Returns:
        1 when violations are found, 0 otherwise
    """
    if not SRC_DIR.exists():
        print(f"Error: {SRC_DIR} not found", file=sys.stderr)
        return 1

    registry = Registry()
    registry.load(SRC_DIR)
    usage = UsageScanner(registry)
    usage.scan(SRC_DIR)

    violations = find_violations(registry, usage)

    if violations:
        for v in violations:
            print(
                f"{v.path}:{v.lineno}: {v.class_name}.{v.method} is public but {', '.join(v.api_ancestors)} does not declare it"
            )
            if v.is_used_externally:
                reached = ", ".join(sorted(v.external_modules))
                print(f"  Reached from outside the implementation ({reached}), so it is contract: {v.fix()}.")
            else:
                print(f"  Only its own implementation reaches it, so it is a helper: {v.fix()}.")
        print(f"\n{len(violations)} violation(s) found.")
        return 1

    declared = {(v.class_name, v.method) for v in violations}
    stale = EXCLUSIONS_ADHOC - declared
    if stale:
        print("Warning: stale exclusions (the method is no longer public on the implementation):")
        for entry in sorted(stale):
            print(f"  ('{entry[0]}', '{entry[1]}')")
        return 1

    print("OK: every public method on an implementing class is declared by its interface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
