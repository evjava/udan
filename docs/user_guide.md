# Udan User Guide

This guide explains the important features of udan; details are found in [operators.md](operators.md) and [architecture.md](architecture.md).

## Getting started

### What is Udan?

**Udan** (Universal Data Navigator) is a query language and execution engine for hierarchical data exploration and transformation.

Think of udan as a powerful, composable tool for working with any data structure:
- Query file systems, Git repositories, Python code, and more
- Filter, sort, group, and transform data intuitively
- Chain operations together in a declarative way
- Extend with custom tools (operators, attributes, renders)

Key concepts:

**Forest**: A collection of items (data structures) that can be manipulated

**Tools**: Functions that operate on forests:
- **Inserters** - Add data to the forest (e.g., `fruits`, `ls_files`, `commits`)
- **Filters** - Remove items based on conditions (e.g., `has_pattern`, `greps`, `filter_field`)
- **Extenders** - Add information to items (e.g., `extend_multiply`, `extend_commit_files`)
- **Groupers** - Group items by fields (e.g., `group_by_field`)
- **Sorters** - Sort items (e.g., `sort_by_field`, `sort_by_natural_order`)
- **Renders** - Output formats (e.g., `:json`, `:list`, `:table`)

**Query**: A chain of tools applied to data (e.g., `fruits, sort name, :json`)

### Installation

```bash
uv tool install udan      # or: pipx install udan
```

This installs the `udan` command onto your PATH and fetches Python >= 3.14 when
it is missing. `uv pip install udan` / `pip install udan` also succeed, but the
script lands in the discovered environment's `bin/` directory, which is
typically not on your PATH - so `udan` can look missing despite a successful
install. In that case activate that environment, or reinstall with
`uv tool install udan`.

### Quickstart

**Command-line usage:**

```bash
# Query fruits from demo data, sort by name, output as JSON
udan 'fruits, sort name, :json'

# List files in the current directory
udan 'ls_files .'

# Git commit history for the current repository
udan 'commits'
```

See [cli-usage.md](cli-usage.md) for the flags, the exit-code contract and history.

**Python API usage:**

```python
from udan.core.config import UdanConfig
from udan.core.api_udan_context import UdanContextAPI
from udan.core.impl_ioc import create_udan_container
from udan.parsing.api_query_parser import QueryParserAPI

container = create_udan_container(UdanConfig())
ctx = container.get(UdanContextAPI).load_core()
parser = container.get(QueryParserAPI)
exec_ctx = ctx.create_exec_context(debug=False)

node = parser.parse_text_to_tree("fruits, sort name", exec_ctx)
forest, _, _, out, _ = ctx.execute_query(node, exec_ctx, query_text="fruits, sort name")
print(out)
```

The container owns the tools registry, the operators engine and the parser; the
execution context is created per query from it.

### Udan basics for beginners

**Anatomy of a query**

A udan query has three parts:

1. **Data source** (inserter): `fruits`, `ls_files .`, `commits`
2. **Transformations** (operators): `sort name`, `grep berry`, `group_by_field color`
3. **Output format** (render): `:json`, `:list`, `:table`

Example: `fruits, sort name, :json`
- Starts with demo fruit data
- Sorts by name field
- Outputs as JSON

**Chaining operations**

Operations are applied left-to-right, separated by commas:

```text
fruits, filter_field calories > 50, sort calories, :list
```

1. Get fruit data
2. Keep only fruits above 50 calories
3. Sort by calories
4. Output as list

**Using parameters**

Tools can take parameters:

```text
commits --limit=3, :list
```

- `commits` - the tool
- `--limit=3` - named argument

Positional arguments work too: `fruits berry` passes `berry` to `insert_fruits(pattern=...)`.

## Fundamentals and usage

### Udan fundamentals

#### Query execution flow

When you run a udan query:

1. **Parsing**: The query string is parsed into a tree structure (`QueryParserAPI`)
2. **Resolution**: The tree is walked to resolve tool names into descriptors
3. **Execution**: The chain groups are applied to transform the data forest
4. **Attribute calculation**: Attributes (metadata) are computed for items
5. **Rendering**: Results are formatted for output

#### Working with the container

The container created by `create_udan_container` is the central object that coordinates all udan operations:

```python
from udan.core.config import UdanConfig
from udan.core.api_udan_context import UdanContextAPI
from udan.core.impl_ioc import create_udan_container
from udan.parsing.api_query_parser import QueryParserAPI

container = create_udan_container(UdanConfig())
ctx = container.get(UdanContextAPI).load_core()
parser = container.get(QueryParserAPI)
```

The context coordinates:
- **Tools registry**: Stores available tools (`ToolsRegistryAPI`)
- **Operators engine**: Applies the chain groups of each kind to the forest
- **Attribute runtime**: Computes attributes (the `udan.attributes` package's service)
- **Query processor**: Resolves query trees (`QueryProcessor.resolve_query`)
- **Debug logger**: Provides debug output

#### Tool types

**Inserters** add data:

```text
fruits              # Demo fruit data
ls_files .          # Files and directories under a path
commits             # Git commits for the current directory
```

**Filters** remove data:

```text
grep berry                        # Keep items matching a pattern (has_pattern)
greps berry -blue                 # AND of patterns, '-' prefixes a negative one
filter_field calories > 50        # Compare a named field
```

**Sorters** order data:

```text
sort calories               # Sort by field (ascending)
sort calories --desc        # Sort by field (descending)
natural                     # Natural order (sort_by_natural_order)
```

**Groupers** organize data:

```text
group_by_field color        # Group by a field
```

**Extenders** add children:

```text
extend_multiply 3           # Extend each number with its multiples
extend_commit_files         # Extend each commit with its changed files
```

**Renders** format output:

```text
:json              # JSON format
:list              # Python-style list
:table             # Table format
:org               # Org-mode headings
```

`?` lists the tools by domain and `? <tool>` shows one tool's parameters:

```bash
udan "? has_pattern"
```

### Creating custom tools

Tools are Python functions with metadata. For the complete guide on writing your own
tools (operators, attributes, and renders), including the meta-key reference, the
injected-parameter rules and dependency providers, see
[writing_tools.md](writing_tools.md).

### Udan tutorials

#### Tutorial: Query the file system

```bash
udan "ls_files ."
udan "ls_files docs/, grep md, :list"
```

Or through the Python API:

```python
node = parser.parse_text_to_tree("ls_files ., grep md, :list", exec_ctx)
forest, _, _, out, _ = ctx.execute_query(node, exec_ctx, query_text="ls_files ., grep md, :list")
```

Git repositories are queried the same way; see [plugins-git.md](plugins-git.md) for
the git tool reference.

## Advanced usage and interoperability

### Debugging queries

Add `debug` as a chain step to see query execution details:

```text
fruits, sort name, debug
```

Or pass `--debug` on the CLI. In Python, turn the flag on the execution context:

```python
exec_ctx = ctx.create_exec_context(debug=True)
node = parser.parse_text_to_tree("fruits, sort name", exec_ctx)
forest, _, _, out, _ = ctx.execute_query(node, exec_ctx, query_text="fruits, sort name")
print(out)                                  # debug lines are prepended to the output
print(exec_ctx.get_debug_log())             # the debug log on its own
```

Debug lines are prefixed `# [DEBUG]`. See [cli-usage.md](cli-usage.md) for the format.

### Variable assignment

Statements are separated by semicolons; `:=name` stores a result and `$name` reads it back:

```text
r := fruits, sort calories; $r, :list
```

### Plugin system

Udan's tools are grouped into domains, one per plugin module. `plugins` lists them:

```bash
udan "plugins"
# - {'name': 'fs', 'domain': 'fs', 'count': 27}
# - {'name': 'git', 'domain': 'git', 'count': 22}
# - {'name': 'org', 'domain': 'org', 'count': 15}
# ...
```

Domain-qualified names resolve ambiguity: `fs.ls_files`, `git.commits`.

Notable domains:
- `fs` - file system operations
- `git` - git repositories (see [plugins-git.md](plugins-git.md))
- `org` - Org-mode file parsing
- `markdown` - Markdown processing
- `renders` - output formats

#### Creating plugins

A plugin is a `plugins_*.py` module of `@annotated` functions. In-repo plugins live
under `udan/plugins_tools_*` (for example `udan/plugins_tools_examples/plugins_git.py`),
declare a module-level `DOMAIN`, and are always scanned with the core.

An external plugin is a separate installed package following the `udan_plugins_*`
naming convention; udan discovers every such package on start-up
(`udan.core.config._discover_plugin_packages`), and `UDAN_PLUGIN_MODULES` replaces
that list - omitting a package turns its capability off.

```python
# udan_plugins_mytools/plugins_demo.py
from udan.core_tools_loading.api_annotated import annotated

DOMAIN = "mytools"

@annotated(meta={"tool_type": "inserter", "output_type": "dict"})
def my_data() -> list[dict]:
    return ["data1", "data2"]
```

See [writing_tools.md](writing_tools.md) for the decorator, the meta keys and the
dependency providers.

### Best practices

1. **Start simple**: Begin with basic queries, add complexity gradually
2. **Use debug**: Enable debug output to understand query execution
3. **Chain operations**: Break complex operations into steps
4. **Use introspection**: `?` and `? <tool>` show what is available and what a tool takes
5. **Test incrementally**: Verify each step of complex queries

For complete API details, see [operators.md](operators.md) and [architecture.md](architecture.md).
