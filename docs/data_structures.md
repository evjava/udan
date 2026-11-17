# Data Structures

## Forest Data Structure

A **Forest** is a hierarchical data structure that stores:
- **Items**: The actual data elements (strings, numbers, dicts, models, descriptors)
- **Depths**: The hierarchical depth level for each item
- **Nodes**: Tree representation where each node contains an item and its children

### Forest Format
A Forest consists of two parallel arrays of the same length:
- `items`: List of items
- `depths`: List of depth integers, where `depths[i]` is the depth of `items[i]`

### Node Format
A Node is a tree structure with:
- `item`: The data item
- `children`: List of child Nodes
- `types`: Type descriptor of the forest this tree maps to (same field as on `Forest`; level 0 is the node's children, since conversions skip the node itself)

Nodes also carry provenance fields: `source_operator`, `source_path`, `origin_chain`
(`udan/core/api_forests.py`).

### Forest Conversions
Forests can be converted between:
- **Forest format**: Flat lists of items with depth information (parallel arrays)
- **Node format**: Tree structure with parent-child relationships

`Forest.convert_to_node` and `Node.convert_to_forest` carry `types` across, so
the descriptor survives a conversion instead of being re-attached by callers.
`ForestBuilder` (`udan/core/api_forests.py`) builds a forest incrementally.

## Forest Type Descriptor

`Forest` carries its type descriptor next to the structure (attributes are
computed on demand from the requested attribute descriptors, not stored on the forest):

```python
class Forest(BaseModel):
    depths: list[Depth]  # depth per item
    items: list[Item]  # the items themselves
    types: ForestTypeDescriptor  # Item type per level, empty = unknown/hand-built
```

`ForestTypeDescriptor` (in `udan/core/api_type_system.py`) folds the operator chain at
query resolution: an inserter sets the level types, an extender appends a level, a
grouper prepends `"group"`, a mapper/replacer rewrites the deepest level, and
filters/sorters pass through. Attribute descriptors requested by the query are
attached to their level; `types.flattened_requested()` is the flat list the
attribute runtime computes. `debug` output shows the descriptor as a
`forest types: [dict{fruit_cost}]` line.

This enables attribute-aware operators like `group_by_attribute` and `filter_by_attribute`.

## Descriptors

Chain steps are carried as serializable descriptors, not functions:

- `OperatorDescriptor` (`udan/core/api_operators.py`): the wire format for an operator
  step - the tool `name`, the bound `args`/`tool_args`, and the kind (`tool_type`);
  `get_max_depth()` drives recursive extending
- `AttributeDescriptor` / `RenderDescriptor`: the same idea for the attribute and
  render domains (`udan/core/api_attributes.py`, `udan/renders/api_renders.py`)
- `ToolDescriptor` / `ToolMetadata` (`udan/core_tools_loading/api_tools.py`): what the
  loader registers per declared tool; resolution goes through `ToolsRegistry`
  (`udan/core_tools_loading/impl_tools_registry.py`), which maps names and aliases to
  metadata + function

The descriptor factory (`udan/core/impl_descriptor_factory.py`) creates the descriptors
at query resolution and binds query arguments against each tool's parameter schema
(`_bind_with_schema_ext`).

### Operators Derivation
Operators should be derived from simple functions with serializable arguments:
- Functions take serializable parameters
- Functions can be converted to descriptors for storage
- Descriptors can be resolved back to functions for execution

## Attribute System

Attributes provide metadata about items in the forest - see
[`attributes.md`](attributes.md) for the full reference.

### Attribute Calculation
- Attributes are calculated via `calculate_attributes_in_forest()`
  (`udan/attributes/api_attribute_runtime.py`), at each attribute's chain position
- Stored in `AttributeStorage` for efficient retrieval
- A disk cache (`udan/attributes/impl_attribute_cache.py`) persists computed values

### Attribute Examples
- **Filesystem attributes**: `size`, `size_human`, `modification_date`, `count_lines`,
  `get_directory_size`, `total_files_count`
- **Git attributes**: `untracked_count`, `untracked_size`, `git_diff_file_size`,
  `push_status`, `commit_message`
- **Demo attributes**: `fruit_cost`, `pfc`, `translate_ru`, `is_even`
- **Aggregates**: `count`, `sum`, `min`, `max` over the whole forest

### Attribute-Aware Operators
Operators like `group_by_attribute` and `filter_by_attribute` work with calculated
attribute values via `AttributeRuntimeAPI.get_attribute_value(at_d, item, ctx)`
(`udan/attributes/api_attribute_runtime.py`).

## Render System

### Render Descriptors
Renders are tools that transform output into different formats:
- `RenderDescriptor`: Serializable descriptor for render specifications
- `RenderMetadata`: Metadata class for render tools
- Each render declares a `shape` (`SHAPE_ITEM` per-item, `SHAPE_CHILDREN` aggregate) in
  `udan/renders/api_renders.py`; aggregate renders compose the per-item lines

### Common Renders

Per-item renders (`udan/renders/plugins_renders.py` unless noted):

| render | alias | output |
|---|---|---|
| `render_raw` | `raw` | `str()` of the item |
| `render_list` | `list-item` | `- item` with depth-based nesting |
| `render_lines_item` | `lines-item` | bare line, no bullet |
| `render_table` | `table-row-single` | one dict item as a table row |
| `render_table_row` | `table-row` | table row with attribute columns |
| `render_org_item` | `org-item` | dict item as org item with chosen fields |
| `render_org_items` | `org-items` | dict items in org property format |
| `render_org_generic` | `org` | org-mode outline (in `plugins_org.py`) |
| `render_org_images` | `images` | org-mode inline image (in `plugins_org.py`) |
| `render_fruit` / `render_vegetable` | `fruit` / `vegetable` | emoji + name (demo) |

Aggregate renders (compose per-item output):

| render | alias | output |
|---|---|---|
| `render_list_aggregate` | `list` | `[{...}, {...}]` comma-separated |
| `render_lines_aggregate` | `lines` | one bare line per item |
| `render_bullets_aggregate` | `bullets` | bullet list |
| `render_table_aggregate` | `table` | table from all dict items |
| `render_org_aggregate` | `org-aggregate` | org outline |
| `render_org_dump` | `org-structure` | org headings with optional properties |
| `render_org_list_aggregate` | `org-list` | org-mode list |
| `render_entries` | `entries` | numbered entries (`plugins_tables.py`) |

### Render Spec Syntax
Render specs use the syntax: `:render-name [args...]`
- Example: `:org-item id name`, `:table`, `:list`
- Arguments can be provided space-separated: `:org-item id name`
- For format strings with spaces or special characters, use quotes: `:fmt "key: {item}"`
- Parentheses are not required (but supported for backward compatibility): `:org-item(id, name)` works but `:org-item id name` is preferred
- A postfix question mark asks about a render: `:?json?` lists renders matching "json"

### Supported Renders Metadata
Inserters can declare a default render in their metadata:
```python
@annotated(meta={"tool_type": "inserter", "supported_renders": ["saved-item"]})
def saved(patterns: Annotated[list[str] | None, "vararg"] = None) -> Iterable[dict]:
    ...
```
The first render in the list is the default when the query names no explicit render.

## Node Traversal

For nested operations, the framework provides Node objects:
- `node.item`: The data item
- `node.children`: List of child nodes
- Recursive traversal is done by nested operators like `sgrep` (which takes
  `nodes: list[Node]` and computes depths itself)
