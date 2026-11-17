# Writing Tools

Tools are the building blocks of udan. They are Python functions annotated with metadata that define how they operate on data.

This guide explains how to create your own tools, including operators, attributes, and renders.

## Introduction

**What are tools?**

Tools are composable functions that transform hierarchical data. Each tool has a specific type (inserter, filter, extender, etc.) and is annotated with metadata that tells udan how to use it.

**Why write custom tools?**

- Extend udan with domain-specific operations
- Create reusable data transformations
- Integrate custom data sources
- Add specialized output formats
- Compute custom metadata/attributes

## The @annotated Decorator

All tools use the `@annotated` decorator to attach metadata:

**Import and Basic Usage**

```python
from udan.core_tools_loading.api_annotated import annotated

@annotated(meta={"tool_type": "filter"})
def my_filter(item: str) -> bool:
    """Filter items based on condition."""
    return "important" in item
```

**How it works**

The `@annotated` decorator:

1. Attaches metadata to the function via the `_annotated` and `_annotated_kwargs` attributes
2. Preserves the original function signature and behavior (using `functools.wraps`)
3. Allows udan's loading system to discover and register the tool

**Decorator Syntax**

```python
# Basic form
@annotated(meta={"tool_type": "filter"})
def my_func(item: str) -> bool:
    ...

# With multiple metadata fields
@annotated(meta={"tool_type": "filter", "aliases": ["myfilter"]})
def my_func(item: str) -> bool:
    ...
```

## Meta Fields Reference

Metadata is passed as a dictionary to the `@annotated` decorator. Here are all available fields:

**Required Fields**

`tool_type`
The type of tool. Required for all operators and renders.
Must be one of: `inserter`, `filter`, `extender`, `grouper`, `sorter`, `mapper`, `replacer`, `render`, `attribute`

When `tool_type` is absent the tool is resolved from its name prefix (`insert_diff`
matches the kind whose query keyword is `insert`, `extend_commit_files` matches
`extend`) and otherwise becomes the vocabulary's default kind, which is `attribute`.

**Optional Fields**

`aliases`
Alternative names for the tool. Users can use any alias in queries.
Type: `list[str]`
Example: `["grep", "search"]`

`attribute_type`
The type of attribute. Declared by attributes only.
Must be one of: `simple`, `composite`, `aggregate`, `value`, `column` (the
`ATTRIBUTE_TYPE_*` constants in `udan/core/api_attributes.py`). `"simple"` is the
undeclared default.
A `simple` attribute is computed per item and receives the item as `item`; an
`aggregate` attribute computes one value over all items and receives `items`; a
`value` attribute is a generic value-to-value function (e.g. `text -> tags`) that
takes no `item`: its parameters receive the composed inputs, which makes it a valid
composition target; a `column` attribute registers a named column once per query.

`item_type`
Type of the item the tool CONSUMES: for operators, the items arriving from upstream in
the chain; for attributes, the item the attribute is computed on; for renders, the
type of the items the render formats.
Declared by filters, sorters, groupers, extenders, mappers, replacers, attributes and
renders. An inserter consumes no items and must not declare it.
Type: `str`
Example: `"dict"`, `"GitDiffFile"`, `"any"` (explicitly unconstrained)

`output_type`
Type of the item the tool CREATES. Declared by inserters, extenders, mappers and
replacers. Filters, sorters and groupers only select or reorder items and must not
declare it. Extenders must declare it: their output items are what the operator
produces.
Type: `str`
Example: `"path"`, `"GitDiffFile"`

`output_semantic`
The domain meaning of the created item, riding on `output_type`. The type names the
Python class the item is (`"dict"`), the semantic names what it means (`"fruit"`)
when the class alone does not say it.
Type: `str`
Example: `"fruit"` (see `insert_fruits` in `udan/plugins_tools_demo/plugins_fruits.py`)

`is_nested`
For inserters and replacers, indicates whether the function operates on nested tree
structures and returns `list[tuple[int, item]]` depth-item pairs.
Type: `bool`
Default: `False`

`dependencies`
Lists attributes whose values feed this tool. The framework calculates them first and injects
each value as the named parameter.
Type: `list[str]`, `dict[str, str | None]` or `None`
Examples: `["translate_ru"]` means this attribute requires `translate_ru` to be calculated first (the
attribute name is also the parameter name); `{"value": "translate_ru"}` maps a parameter to another
attribute; `{"value": None}` is the resolve-per-item marker - the value comes from the query
arguments and is resolved per item during application (`group_by_attribute` and
`filter_by_attribute` both use it)

`cache_attribute`
For attributes, specifies another attribute to use as a cache key. Used for expensive operations that should be cached.
Type: `str`
Example: `"refresh_on_date"` means cache results based on the current date

`precalculated`
For attributes, marks the attribute's values as set during tool application rather
than computed on demand.
Type: `bool`
Default: `False`

`shape`
For renders, whether the render takes one item or the whole forest at once.
Must be `SHAPE_ITEM` (`"item"`, per-item) or `SHAPE_CHILDREN` (`"children"`,
aggregate) from `udan/renders/api_renders.py`.

`supported_renders`
Default render specifications for the output. The render an inserter's result falls
back to when the chain names none.
Type: `list[str]`
Example: `["org-item(id,name)"]` (used by `insert_fruits`), `["org-diff"]` (used by `insert_diff`)

`vararg`
For parameters, indicates that the parameter accepts variable arguments. The parameter must be annotated with
`Annotated[list[T], "vararg"]` where `T` is the type of each argument.
Type: `str` (the literal string `"vararg"` as a description in the Annotated type)
Example: `patterns: Annotated[list[str], "vararg"]` means the parameter accepts any number of string arguments

**IMPORTANT**: Use the `Annotated[list[T], "vararg"]` pattern for variable arguments, NOT Python's `*args` syntax.
The `*args` approach does not work with udan's parameter binding system.

```python
# CORRECT - Use Annotated with "vararg" description
from typing import Annotated

@annotated(meta={"tool_type": "filter"})
def greps(item: Any, patterns: Annotated[list[str], "vararg"]) -> bool:
    """Filter items matching multiple patterns with AND logic."""
    for pattern in patterns:
        if pattern.startswith("-"):
            # Negative pattern (must NOT match)
            if pattern[1:] in str(item):
                return False
        elif pattern not in str(item):
            # Positive pattern (must match)
            return False
    return True

# WRONG - Do NOT use *args (this does not work)
@annotated(meta={"tool_type": "filter"})
def greps(item: Any, *patterns: str) -> bool:
    ...
```

Usage in query: `fruits, greps berry -blue, :list` passes `["berry", "-blue"]` as `patterns`.

**Validation**

The loader promotes the item-contract keys (`item_type`, `output_type`,
`output_semantic`) from meta into the kind's metadata class, and validates the
promotion against the kind. A key from that family the kind cannot carry raises
`ValueError` at load time, as does a required one that is missing:

```text
Tool 'g1' (filter) declares unsupported item type/semantic key(s): output_type.
Allowed for 'filter': item_type.
Tool 'g2' (inserter) declares unsupported item type/semantic key(s): item_type.
Allowed for 'inserter': output_semantic, output_type.
Tool 'f3' (extender) does not declare required item type key(s): output_type.
Required for 'extender': output_type.
```

Keys outside that family (`aliases`, `dependencies`, `cache_attribute`, ...) are
read by name and unknown ones are simply ignored.

**What is not a meta key**

`input_type`, `allows_mutation`, `item_calc_attribute` and `field` are not meta
keys anywhere in udan; a `meta["injected"]` list does not exist either. The item a
tool consumes is declared `item_type`, and the injected parameters are derived from
the signature (see [Framework-Injected Parameters](#framework-injected-parameters)).

## Tool Types

### Inserter

**Purpose**: Add data to the forest

**Function Signature**:

```python
def my_inserter(ctx: UdanContext, ...) -> list[Item]:
    ...
```

**Behavior**:
- Receives `ctx` when it declares the parameter
- User-provided parameters come after `ctx`
- Return value can be a list or any iterable

**Example** (from `udan/plugins_tools_demo/plugins_fruits.py`):

```python
@annotated(meta={"tool_type": "inserter", "aliases": ["fruits"], "output_type": "dict", "output_semantic": "fruit"})
def insert_fruits(pattern: str = "") -> list[dict]:
    """Insert fruit items with id, name, calories, color, ftype, and tags."""
    if not pattern:
        return ALL_FRUITS
    return [fruit for fruit in ALL_FRUITS if pattern.lower() in fruit["name"].lower()]

# Usage in query: "fruits" or "fruits berry"
```

**Nested Inserter**:

For hierarchical data, use `is_nested: True` and return `(depth, item)` pairs:

```python
@annotated(meta={"tool_type": "inserter", "is_nested": True})
def tree_data(ctx: UdanContext) -> list[tuple[int, str]]:
    """Insert hierarchical data."""
    return [
        (0, "root"),
        (1, "child1"),
        (1, "child2"),
        (2, "grandchild"),
    ]
```

The framework converts the pairs into the levels they describe.

### Filter

**Purpose**: Remove items that don't match a condition

**Function Signature**:

```python
def my_filter(item: Item, ...) -> bool:
    ...
```

**Behavior**:
- Receives each item as `item` parameter (injected)
- Returns `True` to keep the item, `False` to remove it
- User-provided parameters come after `item`

**Example** (from `udan/plugins_tools_examples/plugins_builtins.py`):

```python
@annotated(meta={"tool_type": "filter", "item_type": "any", "aliases": ["grep"]})
def has_pattern(item: Item, pattern: str) -> bool:
    """Check if pattern matches the item."""
    if isinstance(item, dict):
        return any(pattern in str(v) for v in item.values())
    return pattern in str(item)

# Usage in query: "fruits, grep berry, :list"
```

### Extender

**Purpose**: Expand items into children (one-to-many transformation)

**Function Signature**:

```python
def my_extender(item: Item, ...) -> list[Item]:
    ...
```

**Behavior**:
- Receives each item as `item` parameter (injected)
- Returns a list of child items
- The framework wraps each item in a node with the item as parent and returned items as children
- Must declare `output_type`

**Example**:

```python
@annotated(meta={"tool_type": "extender", "item_type": "int", "output_type": "int"})
def extend_multiply(item: int, mults: Annotated[list[int] | None, "vararg"] = None) -> list:
    """Extend items by multiplying with multiple multipliers."""
    if not mults:
        mults = [2]
    mults_ints = [int(m) if isinstance(m, str) else m for m in mults]
    return [item * m for m in mults_ints]

# Usage in query: "range 5, extend_multiply 3, :list"
# Result: Each number 0,1,2,3,4 gets a child multiplied by 3
```

### Grouper

**Purpose**: Group items by a key

**Function Signature**:

```python
def my_grouper(item: Item, ...) -> Any:
    ...
```

**Behavior**:
- Receives each item as `item` parameter (injected)
- Returns a group key (the value to group by)
- Items with the same key are grouped together under a group node

**Example** (from `udan/plugins_tools_examples/plugins_builtins.py`):

```python
@annotated(meta={"tool_type": "grouper", "item_type": "any"})
def group_by_field(item: Item, field: str) -> Any:
    """Group items by a field."""
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)

# Usage in query: "fruits, group_by_field color"
```

### Sorter

**Purpose**: Sort items by a key

**Function Signature**:

```python
def my_sorter(item: Item, ...) -> Any:
    ...
```

**Behavior**:
- Receives each item as `item` parameter (injected)
- Returns a sort key (value to sort by)
- Items are sorted based on these keys

**Example** (from `udan/plugins_tools_examples/plugins_builtins.py`):

```python
@annotated(meta={"tool_type": "sorter", "item_type": "any"})
def sort_by_natural_order(item: Item) -> int | str:
    return item if isinstance(item, int) else str(item)

# Usage in query: "range 5, natural" (via the `natural` alias)
```

### Mapper

**Purpose**: Transform items (one-to-one transformation)

**Function Signature**:

```python
def my_mapper(item: Item, ...) -> Item:
    ...
```

**Behavior**:
- Receives each item as `item` parameter (injected)
- Returns a transformed item

**Example** (from `udan/plugins_tools_examples/plugins_builtins.py`):

```python
@annotated(meta={"tool_type": "mapper", "item_type": "any", "output_type": "str"})
def as_str(item: Item) -> str:
    """Convert each item to its string representation."""
    return str(item)

# Usage in query: "range 5, as_str, :list"
```

### Replacer

**Purpose**: Replace items with new ones, per level or nested

**Function Signature**:

```python
def my_replacer(items: list[Item], ...) -> list[Item]:
    ...
```

**Behavior**:
- The flat form runs level by level: the function receives the level's items as
  `items` and returns the new items, and the tree keeps its shape
- The nested form (`is_nested: True`) runs once over the whole subtree: the
  function receives the nodes as `nodes` and returns depth-item pairs
- Useful for operations that need to see all items at once (like deduplication)

**Example** (from `udan/plugins_tools_examples/plugins_builtins.py`):

```python
@annotated(meta={"tool_type": "replacer", "aliases": ["uniq"]})
def unique(items: list[Any]) -> list[Any]:
    """Remove duplicate items."""
    seen = set()
    result = []
    for item in items:
        key = item if isinstance(item, int) else str(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

# Usage in query: "fruits, uniq, :list"
```

**Nested Replacer**:

`nodes` are `Node` objects (`udan/core/api_forests.py`) carrying `item` and
`children`; they have no `depth` field, so a nested replacer that needs depth must
compute it itself. The real `sgrep` does exactly that:

```python
@annotated(meta={"tool_type": "replacer", "is_nested": True})
def sgrep(pattern: str, nodes: list[Any]) -> list[tuple[int, Any]]:
    """Search items in nested tree."""
    ...  # parses 'depth=X' from pattern, keeps the items at that depth

# Usage in queries:
#   "menu, extend_menu_fruits, sgrep depth=0"   -> the 4 day names
#   "menu, extend_menu_fruits, sgrep depth=1"   -> the fruit dicts under them
```

### Attribute

**Purpose**: Compute metadata/attributes for items

**Function Signature**:

```python
def my_attribute(item: Item, ...) -> Any:
    ...
```

**Behavior**:
- Receives each item as `item` parameter (injected); aggregates receive `items`
- Returns a computed value (metadata)
- Can depend on other attributes via `dependencies`
- Declares `attribute_type`; `tool_type` may be omitted, since `attribute` is the
  default kind

**Example** (simple attribute, from `udan/plugins_tools_demo/plugins_fruits.py`):

```python
@annotated(meta={"attribute_type": "simple"})
def translate_ru(item: dict) -> str | None:
    """Translate fruit name to Russian."""
    translations = {
        "apple": "яблоко",
        "orange": "апельсин",
        "banana": "банан",
    }
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    if not isinstance(name, str):
        return None
    return translations.get(name)
```

**Example** (dependent attribute, same module):

```python
@annotated(meta={"attribute_type": "simple", "dependencies": ["translate_ru"]})
def translate_ru_upper(item: dict, translate_ru: str | None = None) -> str | None:
    """Translate and uppercase."""
    if translate_ru is None:
        return None
    return translate_ru.upper()

# Usage in query: "fruits, translate_ru_upper"
```

**Example** (cached attribute):

```python
@annotated(meta={"attribute_type": "simple", "cache_attribute": "refresh_on_date"})
def expensive_computation(item: str) -> dict:
    """Expensive operation cached daily."""
    ...
```

### Render

**Purpose**: Format output for display

**Function Signature**:

```python
def my_render(item: Item, indent: str = "", ...) -> str:
    ...
```

**Behavior**:
- Receives each item as `item` parameter
- Takes `indent` (and optionally `depth`) as ordinary defaulted parameters - the
  framework passes them positionally by name when it renders a level, it does not
  inject them
- Returns a formatted string
- Should handle both simple items and complex structures

**Example** (from `udan/renders/plugins_renders.py`):

```python
@annotated(meta={"item_type": "any", "tool_type": "render", "aliases": ["list-item"], "shape": SHAPE_ITEM})
def render_list(item: Item, indent: str = "", depth: int = 0) -> str:
    """Render item as a list element with nested brackets based on depth.

    Items at depth 0 are rendered as-is: a
    Items at depth 1 are wrapped in brackets: [a]
    """
    if isinstance(item, list):
        return str(item)
    brackets = depth * "["
    brackets_close = depth * "]"
    return f"{brackets}{str(item)}{brackets_close}"

# Usage in query: "fruits, list-item"
```

An aggregate render declares `"shape": "children"` and takes the whole level at
once (`render_list_aggregate`, `render_table_aggregate` in the same module).

A render can also take service dependencies as defaulted parameters - see
[Dependency Providers](#dependency-providers).

## Framework-Injected Parameters

Injection is type-driven. `FunctionInjectorAPI`
(`udan/core_tools_loading/api_function_injector.py`) inspects each parameter's type
annotation and classifies it with `_classify_injected_params`, so a tool declares a
dependency by annotating a parameter with the service's type - it does not list
injections in meta.

The parameter names the operators engine passes by name are `ctx`, `item`, `items`
and `nodes`:

| Parameter | Type | Passed by | Description |
|---|---|---|---|
| `ctx` | `ExecContextAPI` | every operator kind, attributes, renders | Execution context: debug logging, symbols env |
| `item` | `Item` | filters, extenders, groupers, sorters, mappers, attributes | The current item being processed |
| `items` | `list[Item]` | flat replacers | The level's items being replaced |
| `nodes` | `list[Any]` | nested replacers (`is_nested: True`) | The subtree's nodes |

Only the replacer kind declares this in meta: `injected_args=("items", "nodes")` on
the `REPLACER` kind in `udan/operator/plugins_operator_replacer.py`.

Renders do not receive injected `indent` or `depth` - they take them as ordinary
defaulted parameters (`render_raw(item, indent="", attrs=None)`,
`render_list(item, indent="", depth=0)` in `udan/renders/plugins_renders.py`).

**User-Facing vs Injected Parameters**

`item`, `items`, `nodes` and `ctx` are dropped from the tool's user-facing
parameter schema (`_patch_operator_parameters` in
`udan/core_tools_loading/impl_utils_tools_loader.py`), and the `Args:` entries for
them are stripped from the docstring shown to users. Everything left must be
provided in the query.

For example, `at_d` (attribute descriptor) is a user-facing parameter for
`group_by_attribute` and `filter_by_attribute`, where users specify which attribute
to use. It is **not** injected.

```bash
udan "? has_pattern"
# - has_pattern (filter) [src/udan/plugins_tools_examples/plugins_builtins.py:417]
#   - Check if pattern matches the item.
#   - pattern: string!
#   ... (the kind's shared filter arguments follow)
```

## Dependency Providers

`@annotated_dependency` (`udan/core_tools_loading/api_annotated.py`) marks a
function as a service provider. Everything is inferred from its signature: the
return type annotation is what it provides, the parameter types are what it needs.

```python
from udan.core_tools_loading.api_annotated import annotated_dependency

@annotated_dependency
def provide_query_history(config: HistoryConfig) -> HistoryLoggerAPI:
    """Provide the history storage selected by the configured path extension."""
    return create_history_storage(str(config.path))
```

A tool then receives the service by annotating a parameter with its type:

```python
@annotated(meta={"attribute_type": "simple"})
def saved(item: Item, saved_storage: SavedQueriesAPI | None = None) -> bool:
    """Was this item saved as a query?"""
    if saved_storage is None:
        return False
    ...
```

This is the shape of the real history tools
(`udan/plugins_history/plugins_history.py`): `saved`, `saved_tags_list`,
`history_saved`, `history_saved_tags` and `render_history` all take
`saved_storage: SavedQueriesAPI | None = None`, and the default `None` keeps the
tool usable when the storage is not configured.

`plugins_only=True` marks a provider as available to the CLI flow only, for
services a hosting process cannot use (terminal input, for instance):

```python
@annotated_dependency(plugins_only=True)
def get_user_prompt() -> UserPrompt:
    return UserPrompt(input("Enter value: "))
```

App-scoped services belong in a package's `PLUGIN` factories (`udan.decompof`)
instead of a free-standing provider: `udan.plugins_history` provides
`history_logger` and `saved_storage` through `HistoryPlugin` and closes them in its
`detach`, which is the pattern to follow when the service holds a resource.

## Complete Examples

### Example 1: Complete Plugin

```python
"""My custom udan plugin."""

from typing import Any

from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "myplugin"


@annotated(meta={"tool_type": "inserter", "output_type": "dict"})
def my_data() -> list[dict]:
    """Insert my custom data."""
    return [
        {"name": "Alice", "age": 30, "city": "NYC"},
        {"name": "Bob", "age": 25, "city": "LA"},
        {"name": "Charlie", "age": 35, "city": "NYC"},
    ]


@annotated(meta={"tool_type": "filter", "item_type": "dict"})
def filter_by_city(item: dict, city: str) -> bool:
    """Keep items with matching city."""
    return item.get("city") == city


@annotated(meta={"attribute_type": "simple"})
def age_category(item: dict) -> str:
    """Compute age category."""
    age = item.get("age", 0)
    if age < 30:
        return "young"
    elif age < 40:
        return "mid"
    return "senior"


@annotated(meta={"item_type": "dict", "tool_type": "render", "aliases": ["person"], "shape": "item"})
def render_person(item: Any, indent: str = "") -> str:
    """Render person item."""
    if isinstance(item, dict):
        name = item.get("name", "?")
        age = item.get("age", "?")
        city = item.get("city", "?")
        return f"{indent}- {name} ({age} years old, {city})"
    return f"{indent}- {str(item)}"
```

### Example 2: Nested Data Processing

```python
import os

from udan.core_tools_loading.api_annotated import annotated


@annotated(meta={"tool_type": "inserter", "is_nested": True, "output_type": "dict"})
def file_tree(path: str) -> list[tuple[int, dict]]:
    """Insert file tree as nested structure."""
    results = []
    for root, dirs, files in os.walk(path):
        depth = root.count(os.sep) - path.count(os.sep)
        results.append((depth, {"type": "dir", "path": root}))
        for file in files:
            results.append((depth + 1, {"type": "file", "name": file}))
    return results


@annotated(meta={"tool_type": "replacer", "is_nested": True})
def filter_depth(nodes: list, min_depth: int, max_depth: int) -> list[tuple[int, dict]]:
    """Keep the nodes whose computed depth falls in the range."""
    results = []
    for depth, node in walk(nodes):  # depth is computed, Node has no depth field
        if min_depth <= depth <= max_depth:
            results.append((depth, node.item))
    return results
```

## Best Practices

1. **Use Type Hints**
   Always include type hints for parameters and return values. Injection is
   type-driven, so a missing annotation on a service parameter means the service is
   not found, and the item contract is derived from the `item` annotation when meta
   does not declare one.

   ```python
   # Good
   def my_filter(item: str, pattern: str) -> bool:
       ...

   # Avoid
   def my_filter(item, pattern):
       ...
   ```

2. **Write Clear Docstrings**
   Docstrings are shown in introspection output. Explain what the tool does and
   what parameters it accepts; `Args:` entries for `item`/`items`/`nodes`/`ctx`
   are stripped automatically.

   ```python
   @annotated(meta={"tool_type": "filter"})
   def my_filter(item: str, pattern: str) -> bool:
       """Filter items by pattern.

       Args:
           pattern: Pattern to search for (user-provided)

       Returns:
           True if pattern is found in item, False otherwise
       """
       return pattern in item
   ```

3. **Provide Aliases for Common Operations**
   Short aliases make queries more readable.

   ```python
   @annotated(meta={"tool_type": "filter", "aliases": ["grep"]})
   def has_pattern(item: Item, pattern: str) -> bool:
       ...
   ```

4. **Use `dependencies` for Complex Attributes**
   Break complex attributes into smaller, reusable pieces.

   ```python
   @annotated(meta={"attribute_type": "simple"})
   def translate_ru(item: dict) -> str | None:
       ...

   @annotated(meta={"attribute_type": "simple", "dependencies": ["translate_ru"]})
   def translate_ru_upper(item: dict, translate_ru: str | None = None) -> str | None:
       ...
   ```

5. **Set `cache_attribute` for Expensive Operations**
   Use caching attributes for operations that shouldn't run too frequently.
   `refresh_on_date` (`udan/attributes/plugins_operators_attribute.py`) is the
   cache key the attribute family ships with.

   ```python
   @annotated(meta={"attribute_type": "simple", "cache_attribute": "refresh_on_date"})
   def fetch_external_data(item: str) -> dict:
       """Fetch data from external API (cached daily)."""
       ...
   ```

6. **Handle Different Item Types**
   Make your tools robust by handling different input types.

   ```python
   @annotated(meta={"tool_type": "filter", "item_type": "any"})
   def has_pattern(item: Item, pattern: str) -> bool:
       """Check pattern in item (handles dicts, strings, etc.)."""
       if isinstance(item, dict):
           return any(pattern in str(v) for v in item.values())
       return pattern in str(item)
   ```

7. **Declare `supported_renders` for Structured Output**
   The render an inserter's result falls back to when the chain names none.

   ```python
   @annotated(meta={
       "tool_type": "inserter",
       "output_type": "dict",
       "supported_renders": ["org-item(id,name)"],
   })
   def structured_data() -> list[dict]:
       """Insert data best shown as an org item with id and name columns."""
       return [{"id": 1, "name": "Alice"}]
   ```

8. **Test Your Tools**
   Compose the container directly and run a query through it.

   ```python
   from udan.core.config import UdanConfig
   from udan.core.api_udan_context import UdanContextAPI
   from udan.core.impl_ioc import create_udan_container
   from udan.parsing.api_query_parser import QueryParserAPI
   import myplugin

   def test_my_filter():
       container = create_udan_container(UdanConfig())
       ctx = container.get(UdanContextAPI).load_core()
       parser = container.get(QueryParserAPI)
       exec_ctx = ctx.create_exec_context(debug=False)
       node = parser.parse_text_to_tree("my_data, filter_by_city NYC, :list", exec_ctx)
       forest, _, _, out, _ = ctx.execute_query(
           node, exec_ctx, query_text="my_data, filter_by_city NYC, :list"
       )
       assert len(forest) > 0
   ```

9. **Follow Naming Conventions**
   - Use descriptive names: `filter_by_city` (not `fbc`)
   - Use prefixes for clarity: `filter_`, `sort_`, `group_`, and the kind's query
     keyword as the first token (`insert_`, `extend_`) when `tool_type` is omitted
   - Avoid conflicts with Python builtins

10. **Declare the Module Domain**
    A module-level `DOMAIN` names the tool's domain, which is the prefix used for
    domain-qualified calls (`git.commits`) and the section name under `?` and
    `plugins`.

    ```python
    DOMAIN = "myplugin"
    ```

## Common Patterns

**Pattern 1: Field Extraction**

```python
@annotated(meta={"tool_type": "sorter", "item_type": "any"})
def sort_by_field(item: Item, field: str, desc: bool = False) -> Any:
    """Extract field for sorting."""
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)

# Usage in query: "fruits, sort calories" or "fruits, sort calories --desc"
```

**Pattern 2: Conditional Logic**

```python
@annotated(meta={"tool_type": "filter", "item_type": "any"})
def filter_field(
    item: Item,
    key: str,
    operator: Literal["=", "!=", "<", "<=", ">", ">=", "==", "contains", "startswith", "endswith", ...],
    value: Any,
) -> bool:
    """Filter items by comparing a specific field's value."""
    ...

# Usage in query: "fruits, filter_field calories > 50, :list"
```

**Pattern 3: Attribute Chaining**

```python
@annotated(meta={"attribute_type": "simple"})
def raw_data(item: str) -> dict:
    """Fetch raw data."""
    return fetch_from_api(item)


@annotated(meta={"attribute_type": "simple", "dependencies": ["raw_data"]})
def processed_data(item: str, raw_data: dict) -> dict:
    """Process raw data."""
    return process(raw_data)


@annotated(meta={"attribute_type": "simple", "dependencies": ["processed_data"]})
def final_value(item: str, processed_data: dict) -> float:
    """Extract final value."""
    return processed_data.get("value", 0.0)
```

## Troubleshooting

**My tool isn't found**

- Check that you're using `@annotated` decorator
- Check the module is reached by the loader: the core's own plugin subpackages are
  always scanned, an external package must follow the `udan_plugins_*` naming
  convention to be discovered (`udan_plugin_modules` in `UdanConfig` replaces that
  list)
- Check for typos in the function name; `? <name>` shows what udan resolved

**Parameters aren't being passed correctly**

- Verify parameter names match exactly - arguments bind by name
- Check that the parameter is not framework-provided (`item`, `items`, `nodes`,
  `ctx` are dropped from the user-facing schema)
- Use `? <tool>` to see the actual user-facing parameter schema

**Attribute dependencies aren't working**

- Ensure `dependencies` lists exact attribute names
- Check that dependent attributes are also registered
- Verify parameter names match the dependent attribute names, or map them with the
  `{"param": "attribute"}` form

**Nested inserters/replacers don't work**

- Set `is_nested: True` in metadata
- Return `(depth, item)` pairs for inserters and nested replacers
- Accept `nodes` for nested replacers; `Node` has no `depth` field, so compute
  depth from the tree yourself

**For more help**

- Use `?` to list tools and `? <tool>` to introspect one
- Check the examples in `udan/plugins_tools_demo/plugins_fruits.py` and
  `udan/plugins_tools_examples/plugins_builtins.py`
- See [operators.md](operators.md) for the operator reference
