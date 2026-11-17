# Udan

A query language and execution engine for hierarchical data - "jq for trees".
Queries are chains of operators (inserters, filters, extenders, groupers, sorters,
mappers, replacers) applied to a forest of items; attributes compute per-item
metadata; renders format the output (org-mode, tables, lists, JSON, DOT, ...).
Tools are provided by plugins - filesystem, git, org-mode, markdown, CSV, YAML,
SQL, web, shell, Python AST, and demo datasets.

## Install

### From PyPI

Requires Python 3.14.

As an isolated tool, with `udan` on PATH:

```bash
uv tool install udan     # or: pipx install udan
```

Or into a project environment (the script lands in `.venv/bin/udan`):

```bash
uv pip install udan
```

### From a checkout (development)

```bash
uv sync
make install   # uv sync + editable install + uv tool install --force
```

## Run a query

```bash
udan "fruits"
udan "range 5, :list"
udan "menu, extend_menu_fruits, sgrep depth=1, unique"
udan "fruits, fruit_cost, sum fruit_cost"
udan "help"     # list every available tool
```

A leading `# q: ` prefix on the query is tolerated (stripped by the parser).

Example output:

```
$ udan "fruits, group_by_field color, :lines"
- color=red ::
  - 1 :: apple
  - 4 :: strawberry
  - 6 :: raspberry
- color=orange ::
  - 2 :: orange
...
```

A failed query prints its error advice to stderr and exits 1; a successful
empty result exits 0.

## Documentation

Developer documentation lives in `docs/`:

- [`docs/cli-usage.md`](docs/cli-usage.md) - CLI flags, exit codes, history
- [`docs/user_guide.md`](docs/user_guide.md) - query language tutorial
- [`docs/query_examples.md`](docs/query_examples.md) - runnable query examples
- [`docs/operators.md`](docs/operators.md) - operator kinds, chain steps, framework parameters
- [`docs/attributes.md`](docs/attributes.md) - attribute kinds, evaluation, caching, aggregates
- [`docs/data_structures.md`](docs/data_structures.md) - Forest/Node, type descriptors, renders
- [`docs/architecture.md`](docs/architecture.md) - pipeline, UdanContext, dependency injection
- [`docs/writing_tools.md`](docs/writing_tools.md) - `@annotated` tools, meta fields, plugins
- [`docs/plugins-git.md`](docs/plugins-git.md) - the git plugin reference

Agent entry points: [`CLAUDE.md`](CLAUDE.md) -> [`AGENTS.md`](AGENTS.md) ->
[`AGENTS--STYLE.md`](AGENTS--STYLE.md) -> [`AGENTS--PROJECT--UDAN.md`](AGENTS--PROJECT--UDAN.md)
-> [`AGENTS--PROJECT--UDAN--API.md`](AGENTS--PROJECT--UDAN--API.md).

## Development

```bash
make test          # pytest (xdist, testmon, no coverage)
make pre           # every pre-commit hook (ruff, ty, vulture, checks/, pytest)
make check-types   # ty
make lint          # ruff check
```

Python >= 3.14. Tests: `uv run pytest tests/`.
