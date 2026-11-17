# Operators

Operators are special items in the forest that transform data. Each operator type has a specific function signature and behavior.

## Operator Types

### Inserter
- **Purpose**: Adds new items to the forest
- **Function**: returns the new items: `Iterable[Item]`, or `Iterable[tuple[int, Item]]` in the nested form (`is_nested: True` in meta)
- **Behavior**: Supplies the items the chain works on. A chain takes one inserter (or literal) - a second is rejected as a second data source
- **Example**: `fruits` - inserts fruit items

### Filter
- **Purpose**: Removes items that don't match a condition
- **Function**: `FilterFn = Callable[[Item], bool]` (`udan/operator/plugins_operator_filter.py`)
- **Behavior**: Keeps only items where the function returns `True`
- **Examples**: `fruits, grep berry` (`grep` is an alias of `has_pattern`); `fruits, filter_field color == red`

### Extender
- **Purpose**: Expands items into children (one-to-many transformation)
- **Function**: `ExtenderFn = Callable[[Item], Iterable[Item]]` (`udan/operator/plugins_operator_extender.py`)
- **Behavior**: Replaces each item with a node containing the item and its expanded children
- **Example**: `menu, extend_menu_fruits` - extends each menu day with its fruit items

Extending a node that already has children keeps them: the extended items are added
after them, so several extenders stacked on the same nodes all contribute children.

`--on-depth=N` targets the extension at one level: only the nodes at depth N are
extended, nodes at other depths pass through untouched. Besides a level, the value can
be one of the two selector words - see Depth selectors below. When an extender declares
an `item_type` that fits a shallower level of the chain but not the level the previous
operator created, the resolver derives `--on-depth` itself
(`QueryProcessor._derive_extender_on_depth`, `udan/core/impl_query_processor.py`) - the
query `menu, extend_menu_vegetables, extend_menu_fruits` extends the str days with both
vegetables and fruits, as if written `... extend_menu_fruits --on-depth=0`. An explicit
`--on-depth` or `--position` wins over the derivation.

### Grouper
- **Purpose**: Groups items by a key
- **Function**: `GrouperFn = Callable[[Item], "Group | Any"]` (`udan/operator/plugins_operator_grouper.py`)
- **Behavior**: Creates group nodes containing items with the same group key
- **Examples**:
  - `demo.group_by_modulo` (`group_by_modulo(item, n)`): groups numbers by the remainder
  - `group_by_field(field: str)`: Groups items by a field name (dict key or object attribute)
  - `group_by_globs(globs: ...)`: Groups path-like items by user-specified glob groups, first
    matching group wins, unmatched items fall into `<others>`
  - Group files by extension or by directory

### Sorter
- **Purpose**: Sorts items by a key
- **Function**: `SorterFn = Callable[[Item], Orderable]` (`udan/operator/plugins_operator_sorter.py`)
- **Behavior**: Reorders children based on the sort key
- **Examples**:
  - `sort_by_natural_order`: Sorts integers naturally, strings alphabetically
  - `sort_by_field(field: str)`: Sorts items by a field name (dict key or object attribute)
  - Sort files alphabetically or by modification date

### Mapper
- **Purpose**: Transforms items (one-to-one transformation)
- **Function**: `MapperFn = Callable[[Item], Item]` (`udan/operator/plugins_operator_mapper.py`)
- **Behavior**: Replaces each item with the transformed version. Can be used to add attributes or metadata to items.
- **Examples**: `range 3, peval "it * 10"` (the `peval` mapper evaluates a Python expression per item); `fruits, as_str` (stringifies every item)

### Replacer
- **Purpose**: Replaces all children with new items (clears existing children)
- **Function**: `ReplacerFn = Callable[[list[Item]], list[Item]]` (`udan/operator/plugins_operator_replacer.py`)
- **Behavior**: Removes all existing children and inserts new items in their place
- **Example**: `help(pattern)` in `udan/plugins_tools_core/plugins_help.py` - replaces the chain with the tool listing

### Nested Replacers
Some replacers can return depth-item pairs for hierarchical filtering:
- `is_nested: True` metadata indicates the replacer returns `Iterable[tuple[int, Item]]`
- Framework passes `items` and `nodes` parameters to nested replacers (the replacer kind declares `injected_args=("items", "nodes")`)
- `items`: List of plain items (for compatibility with existing replacers)
- `nodes`: List of Node objects with tree structure (for depth-based filtering)
- Examples:
  - `sgrep(pattern: str)` - takes items at a specific depth from the nested structure (`sgrep depth=1`)
  - `flatten` - flattens the nested tree to one level

#### flatten
Flattens a nested tree so all items appear as siblings at one level.

**Usage:** `flatten`

**Example:**
```bash
range 3, extend_multiply 2, flatten
# Output:
# - 0
# - 0
# - 1
# - 2
# - 2
# - 4
```

The same chain without `flatten` keeps the structure: `0 -> [0]`, `1 -> [2]`, `2 -> [4]`.

### Attribute-Aware Operators
- **`group_by_attribute()`**: Groups items by attribute values (e.g. `range 6, group_by_attribute is_even`)
- **`filter_by_attribute()`**: Filters items by attribute comparisons (`=`, `!=`, `<`, `>`, etc.; e.g. `range 5, filter_by_attribute is_even == True`)
- **Behavior**: These operators work with calculated attribute values via
  `attribute_runtime.get_attribute_value(at_d, item, ctx)` - the `AttributeRuntimeAPI`
  method (`udan/attributes/api_attribute_runtime.py`), not a method on the execution
  context

## Tools, Kinds and Descriptors

There is no operator registry keyed by identity strings, and there is no
`OperatorRegistry` class. A tool is a Python function declared with `@annotated`,
and the path from declaration to a running operator is:

1. **Declaration** - `@annotated(meta={...})` (`udan/core_tools_loading/api_annotated.py`)
   declares a tool function and its metadata. `tool_type` names the kind.
2. **Kind** - each kind is a `ToolKind` (`udan/core_tools_loading/api_tools.py`). The seven
   operator kinds live beside the services that apply them (`udan/operator/plugins_operator_*.py`),
   the render kind in `udan/renders/api_renders.py`, the attribute kind in
   `udan/core/api_attributes.py`. A kind declares which meta keys it promotes into typed
   metadata fields (`item_type_keys`, `metadata_meta_keys`, `required_item_type_keys`), its
   `query_keyword` (`insert`, `filter`, `extend`, `group`, `sort`, `replace`, `render`), its
   `level_change` (`replaces` / `appends` / `wraps`), its `kind_args` and its `injected_args`.
3. **Loading** - the tools loader (`udan/core_tools_loading/impl_tools_loader.py`, meta
   handling in `impl_utils_tools_loader.py`) validates a tool's meta keys against its kind and
   builds the metadata object (`OperatorMetadata`, `AttributeMetadata`, ...). A `tool_type`
   given as a bare keyword string (`"insert"`) is resolved back to the kind that claims it.
4. **Resolution** - `ToolsRegistry` (`udan/core_tools_loading/impl_tools_registry.py`) maps
   tool names and aliases to `ToolMetadata` plus the function, and validates the function's
   signature against its kind at register time (a per-item kind requires an `item` parameter).
5. **Descriptors** - per chain step, the descriptor factory
   (`udan/core/impl_descriptor_factory.py`) creates an `OperatorDescriptor` (`udan/core/api_operators.py`)
   or an `AttributeDescriptor`, binding the query's arguments into `args` and `tool_args`.
   `OperatorDescriptor` is a frozen `ToolDescriptor`: `name`, `args`, `tool_args`, and
   `get_max_depth()` for the extender recursion.

## Operator Aliases

Operators can have multiple names via the `aliases` metadata:
```python
@annotated(meta={"tool_type": "filter", "aliases": ["grep"]})
def has_pattern(item: Item, pattern: str) -> bool:
    ...
```

This allows users to use either `has_pattern` or `grep` in queries. The registry indexes
the tool under every alias (`udan/core_tools_loading/impl_tools_registry.py`).

## Creating Operators

For detailed information on how to create your own operators, including the `@annotated` decorator, all meta fields, framework-injected parameters, and complete examples for each operator type, see [writing_tools.md](writing_tools.md).

## Framework-Injected Parameters

The udan framework automatically injects certain parameters into operator functions. These parameters are provided by the framework and should not be specified by users in queries.

### Injected Parameters

| Parameter | Type | Injected Into | Description |
|-----------|------|---------------|-------------|
| `ctx` | `ExecContextAPI` | Inserters, Filters, Groupers, Replacers | The execution context, providing access to registries, configuration, and utilities |
| `item` | `Item` | Filters, Extenders, Groupers, Sorters, Mappers | The current item being processed |
| `items` | `list[Item]` | Non-nested Replacers | List of all items being replaced |
| `nodes` | `list[Node]` | Nested Replacers | List of Node objects with tree structure for depth-based filtering |

### How a Parameter Counts as Injected

There is no `meta["injected"]` field. The loader derives it from the signature:
a parameter named `ctx`, `item`, `items` or `nodes` is framework-provided and is
stripped from the user-facing schema (`_extract_injected_args` in
`udan/core_tools_loading/impl_utils_tools_loader.py`). The kind carries the same
fact as `ToolKind.injected_args` - the replacer kind declares
`injected_args=("items", "nodes")` - and the descriptor factory reads it when a
nested operator leaves those arguments unbound.

```python
@annotated(meta={"tool_type": "filter"})
def my_filter(item: str, ctx: ExecContextAPI, pattern: str) -> bool:
    """Example filter with injected parameters."""
    return pattern in item

# "item" and "ctx" are framework-provided
# The user-facing schema shows only "pattern"
```

This is what lets a query name only the parameters a user supplies, and what the
help output and introspection report as a tool's arguments.

### User-Facing vs Injected Parameters

- **User-facing parameters**: Appear in the operator's parameter schema and must be specified in queries (e.g., `pattern` in `grep --pattern="foo"`)
- **Injected parameters**: Automatically provided by the framework and hidden from user-facing schemas

For example, `at_d` (attribute descriptor) is a user-facing parameter for operators like `group_by_attribute` and `filter_by_attribute`, where users specify which attribute to use. It is **not** injected.

### Framework Arguments (sp_args)

Besides the injected parameters, a kind can accept arguments that belong to no
tool function: the query side intercepts them (`--key=value`), the
descriptor carries them as sp_args, and the operator engine reads them back. Each
kind declares the ones it accepts as `ToolKind.kind_args`, and
`help` lists them in the "<Kind> args:" block of a tool's help -
`range 5, extend_multiply? 2` ends with:

```
Extender args:
    on_depth: depth :: Extend only the nodes at that depth (0 = top level); 'all' extends every node, 'leaf' only the ones without children
    max_depth: integer :: Recursion levels beyond the first extension (0 = extend once, the default)
    position: path :: Extend only the node at that hierarchical position (1.2 = children[1].children[2]); the other nodes pass through untouched; -1 or the empty path switches it off
```

A parameter the description's own `Args:` section documents gets no extra line,
so the help shows every argument exactly once.

| Argument | Accepted By | Description |
|----------|-------------|-------------|
| `--on-depth=N` | Filters, Extenders, Mappers | Apply only at depth N (0 = top level); `all` targets every node, `leaf` the ones without children |
| `--max-depth=N` | Extenders | Recursion levels beyond the first extension (0 = extend once) |
| `--position=I.J` | Extenders, Groupers | Apply only at the hierarchical position `I.J` (sibling indexes); the other nodes pass through; `-1` or `""` switches it off |

Kinds without framework arguments (inserters, sorters, replacers) show
no section. Sorter ordering has no sp_arg: `desc` is an ordinary `sort_by_field`
parameter, and `-field` is sugar for the reversed order.

### Depth selectors

`--on-depth` takes a depth level or one of two words:

- `all` - every node of the tree the operator receives, at every depth. For a filter
  that means one stage filters every level instead of one `--on-depth=N` stage per
  depth, and a node the filter rejects still loses its subtree with it; for a mapper
  it is the same as leaving the argument out. An extender extends every node, the
  children a node already has included - the created items follow them, and only
  `--max-depth` re-targets the extension at the items it created.
- `leaf` - the nodes without children, at whatever depth they sit. A filter drops the
  failing leaves, an extender extends the childless ones, a mapper maps only them.
  The children an extender creates are leaves too, so extending them again is left to
  `--max-depth` (0 = extend once) - that is what keeps the extension finite.

An integer matches by the level, the words match by the node, so an integer stops the
walk once the target level is behind it while the words walk the whole tree. The words
are matched exactly: anything that is neither of them nor an integer is an error naming
the accepted values.

### Position

`--position=I.J` names one node by its sibling indexes: `--position=2` is the third
node of the level the operator receives, and every further component descends into
that node's children - `1.2` is `children[1].children[2]`. With a single component
it is just an index; the comma cannot be used because it separates chain items.

An extender extends only that node, keeping the children it already has; a grouper
re-groups only the children of that node. Every other node passes through untouched,
and a position past the existing siblings matches nothing - the way `--on-depth`
past the last level extends nothing. `--position=-1` and `--position=""` are the
off-switches: the empty path means no position, so the operator applies everywhere
exactly as if the argument had not been passed (and `-1` is not "the last node").
Naming the node wins over naming the level: a `--position` suppresses the derived
`--on-depth` (see Extender above) and takes precedence over an explicit one. Like
`--on-depth` on the kinds that ignore it, a `--position` on a kind that declares
none is accepted and does nothing.

```
# q: range 3, extend_multiply 2, extend_multiply 3 --position=1
#    only the second node gets the second extender: 0->[0], 1->[2, 3], 2->[4]
# q: range 6, group_by_modulo 2, group_by_modulo 3 --position=1
#    only the children of group 1(mod 2) are re-grouped by mod 3
```

## Recursive Extending

Extender operators support recursive extension:
- Controlled by `max_depth` parameter
- `OperatorDescriptor.get_max_depth()` method controls recursion depth
  (`udan/core/api_operators.py`)
- `OperatorContext.depth` field tracks current recursion level during expansion
  (`udan/operator/impl_operator_engine.py`)

`max_depth` counts the recursion levels beyond the initial extension (default
`0` - items are extended once, no recursion):

- Query syntax: `--max-depth=N`, stored as a descriptor sp_arg (like `--on-depth`)
- `--max-depth=0` is the default single extension

Examples:

```
# q: range 2 3, extend_multiply 2                # 2 -> [4]
# q: range 2 3, extend_multiply 2 --max-depth=3  # 2 -> 4 -> 8 -> 16 -> 32, depths 0..4
```
