# Udan CLI Usage Guide

The CLI is a plain argparse program in `src/udan/parsing/main.py`. It lives in the
parsing package because it is a query-language entry point: it parses the query text
and hands the node to the engine context (`UdanContextAPI.execute_query`), which runs
the steps of the execution. It is not a Fire-generated CLI.

## Running a query

The installed console script:

```bash
udan "fruits"
```

Or the module directly:

```bash
uv run python -m udan.parsing.main "fruits"
```

The script entry point is declared in `pyproject.toml` as
`udan = "udan.parsing.main:main_io"`. The callable it wraps is
`main(query: str, comment: str = "", debug: bool = False) -> str`, which returns the
rendered output string.

The `# q: ` prefix is optional. The parser strips it when present
(`impl_query_parser.py` calls `remove_prefix_if_needed(query_text, "# q:")`), so both
of these are the same query:

```bash
udan "fruits"
udan "# q: fruits"
```

A `#` starts a comment that runs to the end of the line; a query that is only a
comment falls back to the `?` question atom (the tool listing).

## Arguments

| Argument | Type | Meaning |
|---|---|---|
| `query` | positional, required | The query string to execute |
| `--comment` | string, default `""` | Purpose of the query; stored in history |
| `--debug` | flag (`store_true`) | Enable debug output |
| `--query` / `--query=value` | string | Alternative to the positional form |

`--query` is handled before argparse (so `--query="a, b"` survives shell splitting)
and overrides the positional value when both are given:

```bash
udan --query="fruits, grep berry, :list"
udan --query "menu"
```

`--debug` is a `store_true` flag. Passing an explicit value is an argparse error:

```bash
udan "fruits" --debug=False
# usage: udan [-h] [--comment COMMENT] [--debug] [query]
# udan: error: argument --debug: ignored explicit argument 'False'
```

Omitting the query entirely is also an argparse error:

```bash
udan
# udan: error: the following arguments are required: query
```

`udan --help` prints the argparse help:

```text
usage: udan [-h] [--comment COMMENT] [--debug] [query]

Universal Data Navigator - Query language for hierarchical data exploration

positional arguments:
  query              Query string to execute (e.g., 'fruits', 'menu, sort name')

options:
  -h, --help         show this help message and exit
  --comment COMMENT  Comment to describe the purpose of this query
  --debug            Enable debug mode for verbose
```

## Success and failure

`main` returns the rendered output on success and `main_io` prints it to stdout.
On failure the diagnostic goes to stderr and the exit code is 1, so a scripted
pipeline can tell a failing query from an empty result:

```bash
udan "nonexistent_tool_xyz"
# exit code 1
# stdout: empty
# stderr:
#   Bare literal 'nonexistent_tool_xyz' is not allowed.
#   If you want to use this as a literal string, quote it: "nonexistent_tool_xyz"
```

A failed parse prints a `Query parse error: ...` line with the tokens the parser
would have accepted at that position:

```bash
udan ":=r fruits"
# Query parse error: Unexpected token Token('ASSIGN', ':=') at line 1, column 1.
# Expected one of:
#   * CMP_OP
#   * RENDER
#   * KEYVAL
#   * ATOM
```

## Examples

```bash
# Basic query
udan "fruits"
# - 1 :: apple
# - 2 :: orange
# ...

# Chain with a filter and a render
udan "fruits, grep berry, :list"

# Named arguments with the --name form
udan "commits --limit=3, :list"

# Comment for history tracking
udan "menu" --comment="Planning weekly meals"

# Debug mode
udan "fruits, grep berry" --debug

# Combined
udan "fruits, grep berry, :list" --comment="Berry check" --debug
```

Strings with spaces need quoting, in both the query and the comment.

## Debug output

`--debug` prepends the execution debug log to the output. Every debug line is
prefixed `# [DEBUG]`:

```text
# [DEBUG] loaded tools: ['count', 'sum', 'min', 'max']
# [DEBUG] Registered tools from udan.attributes.plugins_aggregates_attribute
# [DEBUG] query_tree=N(item=ROOT, ch=[N(item=CHAIN, ch=[N(item=fruits), ...
# [DEBUG] query_text='fruits'
- 1 :: apple
- 2 :: orange
...
```

Setting `udan_log_time` (env `UDAN_LOG_TIME=1`) adds an elapsed-time prefix to every
debug line, formatted `[HH:MM.mmm]`:

```text
# [21:15.386] [DEBUG] loaded tools: ['count', 'sum', 'min', 'max']
```

The `debug-time` chain step shows the elapsed time for the query whether or not
`udan_log_time` is set:

```bash
udan "fruits, debug-time"
# ...
# [DEBUG] Time: 0.005s
```

## History

History is not a CLI feature: it belongs to the `udan.plugins_history` package, and
the CLI only passes `--comment` through to `execute_query`, which logs every run -
comment or no comment.

The storage is plugin configuration (`HistoryConfig` in
`src/udan/plugins_history/history_config.py`), not a field of `UdanConfig`. Its env
prefix is `UDAN_HISTORY_`:

| Variable | Default | Meaning |
|---|---|---|
| `UDAN_HISTORY_PATH` | `./.udan/history.db` | History storage file |
| `UDAN_HISTORY_SAVED_PATH` | `./.udan/saved.db` | Saved queries storage file |

The path extension selects the implementation: `.jsonl` uses the JSONL file backend,
`.db` uses SQLite, anything else (or no path) disables the storage. The default is
SQLite.

Each history entry records `timestamp`, `command`, `success`, `total_items`,
`depth_zero_items`, `error` and `comment`.

The current values are visible through the config query:

```bash
udan "config"
# - core
#   - udan_cache_dir: ...
# - history
#   - path: .udan/history.db
#   - saved_path: .udan/saved.db
```

## Notes

1. Quote the query - it contains spaces and commas.
2. `--comment` is optional and free-form; it lands in the history `comment` column.
3. Introspection from the CLI is a query, not a flag: `?` lists the tools by domain,
   `? has_pattern` shows one tool's description and user-facing parameters.
4. `fire` is used only by standalone scripts under `tools/`. The `udan` entry point
   never goes through Fire.
