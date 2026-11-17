# Query Examples

Practical examples of udan queries. Every example below was executed with
`udan "<query>"`; the shown output is the real output.

## Query Syntax

Queries are parsed into parse trees by the Lark grammar in `udan/parsing/impl_utils_parsing.py`.

- **Function application**: `range 5` applies `range` to argument `5`
- **Parentheses for grouping**: `a := (fruits, sort name)` groups a sub-chain
- **Comma-separated chain**: `fruits, grep berry, sort_by_field name` - a sequence of steps
- **Statements**: `;` separates statements - assignment then reuse: `a := (range 3); $a`
- **String literals**: quoted strings with escape sequences (`grep "#tag"` - a `#` inside
  a string is data, not a comment)
- **Numeric literals**: bare numbers are int/float items and open a chain as the data
  source (`3, extend_multiply 2`)
- **Aliases**: tools can have several names (`has_pattern` is also `grep`,
  `insert_fruits` is also `fruits`, `unique` is also `uniq`)
- **Comments**: everything from `#` to the end of the line is skipped:
  `fruits, grep berry # only berries`
- **Kind keyword**: a bare `sort` routes to the sorter kind (`sort name` resolves to
  `sort_by_field`); for the other kinds, use the tool name or its alias
  (`grep`/`grepv`/`uniq`/`natural`/`fruits`)

## Demo Data

- `fruits` - 10 dict items (`id`, `name`, `calories`, `color`, `ftype`, `tags`) with the
  attributes `fruit_cost`, `pfc`, `translate_ru`, `translate_ru_upper` and the extenders
  `similar_fruits`, `extend_menu_fruits`
- `vegetables` - the same shape over frozen pydantic models
- `menu` - `["day-1", ..., "day-4"]`
- `range N` - integers `0..N-1`
- `demo.*` - `extend_multiply`, `group_by_modulo`, `is_even`, `is_odd`, `double`, ...

## Filtering and Sorting

```
fruits, grep berry                  # has_pattern: strawberry, blueberry, raspberry
fruits, greps berry -blue           # AND logic with exclusions: strawberry, raspberry
fruits, greps berry blue            # both required: blueberry
fruits, grepv berry                 # has_not_pattern: everything except the berries
fruits, filter_field calories > 50  # numeric comparison on a field
fruits, tags.has_tag sweet          # keep items carrying the tag
fruits, sort_by_field name          # or just: fruits, sort name
range 5, natural                    # sort_by_natural_order
fruits, limit 3                     # first 3 items
```

`filter_field calories > 50` keeps apple, banana, blueberry, raspberry, grape, mango.

## Grouping

```
fruits, group_by_field color
menu, extend_menu_fruits, sgrep depth=1, unique, group_by_field name
```

`group_by_field color` produces `color=red`-style group items with the matching fruits
as children:

```
- color=red ::
  - 1 :: apple
  - 4 :: strawberry
  - 6 :: raspberry
- color=orange ::
  - 2 :: orange
  ...
```

## Attributes

Attributes are computed per item and declared with `attribute_type` - see
[`attributes.md`](attributes.md). Use them in a chain and then consume them:

```
fruits, fruit_cost                     # items gain fruit_cost; renders show it
fruits, fruit_cost, sum fruit_cost     # aggregate footer: "# sum: 20.1"
fruits, count                          # "# count: 10"
fruits, fruit_cost, min fruit_cost     # "# min: 0.5"
fruits, fruit_cost, group_by_attribute fruit_cost   # group items by the attribute value
fruits, fruit_cost, map_attr fruit_cost, :list      # replace each item by its attribute value
```

Attribute-driven filtering takes the attribute in the chain position - a boolean
attribute filters with a shorthand or an explicit comparison:

```
range 5, filter_by_attribute is_even           # [0, 2, 4]
range 5, filter_by_attribute is_even == True   # [0, 2, 4]
range 5, filter_by_attribute is_even == False  # [1, 3]
```

Fields on dict/object items are filtered with `filter_field` (see above) or compared
after `map_attr` / `extend_by_attribute`.

## Hierarchical Data

```
menu, extend_menu_fruits                      # fruits under each day
menu, extend_menu_fruits, sgrep depth=1       # items at depth 1 only
menu, extend_menu_fruits, sgrep depth=1, unique
menu, extend_menu_fruits, flat_children       # parent-child pairs as rows
fruits, similar_fruits, flatten               # whole tree flattened to depth 0
range 3, extend_multiply 2, extend_multiply 3 --position=1
```

## Filesystem and Shell

```
ls_files src/udan/core                  # glob a directory (alias of fs.insert_ls_files)
ls_files src/udan/core, grep api        # filter paths by pattern
ls_files docs, size_human               # "- docs/operators.md :: 14.38 KB"
ls_files src/udan/core, count_lines     # line count per file
read_env .env.example                   # structured .env entries
shell_to_lines 'ls docs'                # shell command output as items
shell_to_lines 'ls docs', has_pattern md
```

## Git

The git tools read the repository of the given directory (default: the current one).
See [`plugins-git.md`](plugins-git.md) for the full reference.

```
commits --limit=3, :commit-log
commits, extend_commit_files             # files changed per commit
insert_status, :list                     # short status, one dict per file
insert_diff                              # diffs vs HEAD, default render org-diff
git_repos .                              # repositories under a directory tree
git_repos ., untracked                   # untracked files per repository
```

Real `commits --limit=3, :commit-log` output from this repository:

```
2026-11-16--18-19 b1cbcff :: dev: removed tests-integration, Makefile fix / UNPUSHED
2026-11-16--11-35 0bbb500 :: dev: improved error message on parse errors
2026-11-14--12-23 f603f3e :: dev: showing abs-path for ext plugins
```

## Graphs

```
fruits, similar_fruits, as_dot, :raw           # DOT digraph
fruits, similar_fruits, as_dot --lr, :raw      # rankdir=LR
fruits, similar_fruits, as_dot, as_png         # org-mode image link to a rendered PNG
```

## Variables

`:=name` stores a sub-chain result, `$name` references it later in the same session:

```
a := (fruits, grep berry); $a, sort_by_field name, :list
a := (fruits, grep berry); b := ($a, sort name); $b, count
```

`vars` (system domain) lists the defined variables. Set operations work over stored
forests: `intersect`, `union`, `difference`, `symmetric_difference`.

## Introspection

The question sugar is provided by `udan/plugins_help_sugar` - see
[`architecture.md`](architecture.md) for how it hooks the resolver.

```
?                          # every available tool
range 5, ?                 # only tools usable after a data source
extend?                    # tools matching "extend" (word? is ? word)
range? 3                   # help for range - text after the question word is ignored
fruits, greps? berry       # help for greps while the query is half-written
:?json?                    # renders matching "json"
:raw ?                     # raw introspection data instead of formatted help
help                       # the tool listing (alias ?)
help_list                  # compact listing
introspect_tool sort_by_field   # metadata for one tool
system.udan_config         # the full configuration grouped by owner
```

## Render Specs

`:` selects a render; arguments are space-separated (parentheses are tolerated):

```
fruits, :list                    # "[{...}, {...}]" - aggregate comma-separated list
fruits, :lines                   # one bare line per item
fruits, :org-item id name        # "- 1 :: apple" style org items with chosen fields
fruits, :table                   # table from all dict items
range 3, :entries                # "** entry-1 / - item :: 0" numbered entries
range 5, :fmt '{item}!'          # format string; {item} is the item placeholder
fruits, :json                    # JSON dump
fruits, :raw                     # str() per item
```

`{item}` is the placeholder `:fmt` understands; attribute names in the chain render as
extra columns in `:table` (`fruits, fruit_cost, :table`).

## A Longer Chain

```
menu, extend_menu_fruits, sgrep depth=1, unique, sort_by_field name, :org-item name quantity
```

resolves as: insert the menu, extend each day with its fruits, take the depth-1 items,
deduplicate them, sort by name, render as org items with two fields.

## Processing Pipeline

1. **Parsing**: query text -> parse tree (`udan/parsing`)
2. **Resolution**: parse tree -> chains of operator/attribute descriptors
   (`QueryProcessor.resolve_query`)
3. **Application**: the operator engine applies chain steps to the forest (`udan/operator`)
4. **Attribute Calculation**: computed over the stage at each attribute's chain position
   (`udan/attributes`)
5. **Rendering**: forest -> string output (`udan/renders`)
