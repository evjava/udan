# Attributes

Attributes compute per-item metadata. They are declared like any tool
(`@annotated`), with `attribute_type` in the meta, and they participate in the
chain at the position they are written at.

## Declaration

```python
from udan.core_tools_loading.api_annotated import annotated

@annotated(meta={"attribute_type": "simple", "item_type": "Fruit"})
def fruit_cost(item: dict) -> float | None:
    """Cost per unit for a fruit."""
    costs = {"apple": 1.2, "orange": 0.8}
    return costs.get(item.get("name"))  # None when the item is not recognized
```

Rules:

- Return `None` when the attribute does not apply to the item - never a default
  value; `None` is what tells the render/aggregates "not computed".
- The item parameter is named `item`.
- Extra parameters need defaults and are bound from the query
  (`fruit_cost` takes none; `filter_by_attribute`-style tools take operators).
- Only `item` is framework-injected for attributes (not `ctx`, `items`, `nodes`).
- The attribute kind (`ATTRIBUTE`, `udan/core/api_attributes.py`) promotes the meta
  keys `attribute_type`, `cache_attribute`, `precalculated`; `item_type` narrows the
  items it applies to.

## attribute_type values

Constants in `udan/core/api_attributes.py`:

| value | meaning | example |
|---|---|---|
| `simple` | per-item function of the item and its arguments | `fruit_cost`, `size`, `is_even` |
| `composite` | computed from other attributes' values | derived metrics |
| `aggregate` | one value from all items in scope | `count`, `sum`, `min`, `max` |
| `value` | generic value->value function, no `item` parameter (valid composition target: `extract_tags(summarizer)`), values still stored per item | text -> tags |
| `column` | chain item defines a column instead of producing its own value | `cattr` |

## Evaluation Order

An attribute is applied **at the position it is written at**, over the items that
exist there - exactly once per item, and only there:

- `range 6, is_odd, tracked_twice` computes the attribute for the surviving items only
- `range 6, tracked_twice, is_odd` computes it for every item the filter then selects from

`tests/test_lazy_attributes.py` pins this behavior. `calculate_attributes_in_forest`
(`udan/attributes/api_attribute_runtime.py`) computes over each stage and passes the
stage through unchanged - values land in attribute storage, not on the items.

## Caching

`AttributeCache` (`udan/attributes/impl_attribute_cache.py`) persists computed values
with joblib, one subdirectory per attribute identity, under
`UdanConfig.udan_cache_dir`/`attrs`. Declare `cache_attribute: True` in the meta to
cache an attribute. String keys - the caller serializes the descriptor.

## Consuming Attributes

```
fruits, fruit_cost                              # values available to renders
fruits, fruit_cost, :table                      # fruit_cost appears as a column
fruits, fruit_cost, extend_by_attribute fruit_cost   # value as a child of each item
fruits, fruit_cost, map_attr fruit_cost, :list       # replace items by their values
fruits, fruit_cost, group_by_attribute fruit_cost    # group by the attribute value
range 5, filter_by_attribute is_even            # boolean shorthand (== True)
range 5, filter_by_attribute is_even == False   # explicit comparison
```

`filter_field` / `group_by_field` are the field-based counterparts for dict/object items.

## Aggregates

Aggregate attributes (`attribute_type: "aggregate"`, `udan/attributes/plugins_aggregates_attribute.py`)
compute one value over all items in scope and render as a footer line:

```
$ udan "fruits, count"
...
# count: 10

$ udan "fruits, fruit_cost, sum fruit_cost"
...
# sum: 20.1

$ udan "fruits, fruit_cost, min fruit_cost, max fruit_cost"
...
# min: 0.5
# max: 4.0
```

- `count` takes no arguments
- `sum`, `min`, `max` take a required attribute name: `sum fruit_cost`
- Items without the named field fall back to attribute values (named `cattr` columns included)
- Several aggregates may appear in one query - each adds its own footer

## Columns (`cattr`)

`cattr` (`attributes_ops` domain, `attribute_type: "column"`) defines a computed
column from an expression; the column renders under its own name:

```
$ udan "fruits, cattr 'calories * 2' dbl, :table"
| name  | id | calories | color | ftype | tags                        | dbl |
|-------+----+----------+-------+-------+-----------------------------+-----|
| apple |  1 |       52 | red   | fruit | ['fruit', 'sweet', 'fresh'] | 104 |
```

First argument is the expression, second the column name.

## Origin

`origin` (`attributes_ops`) returns the chain of operators that created or affected
an item - useful when debugging where an item came from; `refresh_on_date` builds
cache keys that include the current date.
