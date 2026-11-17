# Udan Architecture

Udan is **Universal Data Navigator** - a query language and execution engine for hierarchical data exploration and transformation.

## Package Layout

`src/udan/` has no flat modules. The code lives in subpackages:

| Package | Contents |
|---------|----------|
| `udan/core` | engine context, query processor, forests, the operators vocabulary, config, IOC, chain machinery, the type system |
| `udan/core_tools_loading` | `@annotated`, the tools loader and registry, the function injector, `ToolKind` |
| `udan/operator` | the operators engine plus one `plugins_operator_*.py` module per kind (`inserter`, `filter`, `extender`, `grouper`, `mapper`, `replacer`, `sorter`) |
| `udan/parsing` | grammar, parser, CLI (`main.py`) |
| `udan/attributes` | attribute runtime, storage and cache, aggregates, attribute operators |
| `udan/renders` | render engine, renders, tables |
| `udan/decompof` | `Plugin` / `Container`, the DI substrate |
| `udan/plugins_help_sugar` | the question sugar |
| `udan/plugins_history` | query history and saved queries |
| `udan/plugins_tools_core` | `plugins_help.py`, `plugins_system.py` |
| `udan/plugins_tools_demo` | `plugins_demo.py`, `plugins_fruits.py`, `plugins_vegetables.py` |
| `udan/plugins_tools_examples` | fs, git, org, markdown, json, yaml, csv, sql, web, shell, dev, dot, tags, peval, mock, builtins |

A plugin package outside udan itself follows the `udan_plugins_*` naming convention; see Configuration System below.

## Execution Pipeline

The system processes a query in five stages:

1. **Parsing**: the query text is parsed into a tree (`QueryParserAPI.parse_text_to_tree()`, Lark-based; the grammar and the transformer live in `udan/parsing`, the raw text-to-tree entry point is `parse_tree()` in `udan/parsing/impl_utils_parsing.py`)
2. **Resolution**: the tree is resolved into a forest of data items and tool descriptors (`QueryProcessorAPI.resolve_query()`, `udan/core/impl_query_processor.py`)
3. **Application**: descriptors are applied (`OperatorsEngineAPI.apply_operators_with_contexts()`, `udan/operator/api_operator_engine.py`); each kind's chain groups go through the same `apply_chain_step` (`udan/operator/impl_operator_engine.py`)
4. **Attribute Calculation**: attributes are computed (`AttributeRuntimeAPI.calculate_attributes_in_forest()`, `udan/attributes/api_attribute_runtime.py`)
5. **Rendering**: the forest is turned into text (`RenderEngineAPI.render_forest()`, `udan/renders/api_render_engine.py`)

The context runs stages 2-5: `UdanContextAPI.execute_query()` takes the parse tree the caller obtained and returns the forest, the attributes, the render specs and the output string. Only the parse is the caller's job, because the parser is the parsing package's, not the context's.

## UdanContext Architecture

The `UdanContext` class (`udan/core/impl_udan_context.py`) coordinates the runtime. Its constructor takes thirteen injected dependencies: config, tools registry, tools loader, dependency registry, event bus, symbols env, output engine, function injector, query processor, chain routing, chain context factory, plugins, container.

`OperatorsEngine` and `AttributeRuntime` are not members: the engine is reached through the chain routing, the attribute runtime through the chain-context factory that the value domains' packages decorate. `DebugLogger` is not a member either - each execution context carries its own, so `create_exec_context(debug=...)` gets a fresh logger over the shared symbols env.

The five services around it, and what each does:

### 1. Tools registry (`udan/core_tools_loading/impl_tools_registry.py`)
- Stores and resolves tools (operators, attributes, renders)
- Maps names and aliases to metadata and functions
- Handles alias resolution

### 2. Operators engine (`udan/operator/impl_operator_engine.py`)
- Owns the walk every operator goes through: resolve the descriptor to its metadata
  and function, bind its arguments, pre-extract the selector values into
  `OperatorArgs`, call the kind's applicator, mark what came out with its origin,
  recurse into the tree
- Holds the applicator dispatch: each kind's service registers its applicator at
  container build (`register_applicator`), so the walk applies any kind without
  naming it
- Owns no operator kind: every kind is instantiated beside the engine that applies it,
  in `udan/operator`'s own plugin modules (`plugins_operator_inserter`,
  `plugins_operator_filter`, `plugins_operator_extender`, `plugins_operator_grouper`,
  `plugins_operator_mapper`, `plugins_operator_replacer`, `plugins_operator_sorter`),
  and the chain routing hands each kind's chain groups to that module's service -
  never to the engine

**Why the engine exists when it owns no kind**: the extraction moved kind ownership,
not the machinery. Three things no kind can own keep it in place:

1. **The walk** - one algorithm serving every kind, because it cannot decompose per
   kind. A filter, a grouper and a mapper in one run are one sequence of stages:
   each stage streaming into the next (`CachedIterable`), the item cap bounding the
   last operator's pull, the introspection short-circuit
   (`OverrideForestException`), the origin marking, the recursion into the tree -
   shared mechanics, not per-kind ones. A kind's applicator receives one node list
   and its resolved arguments; everything around that call is the engine's.
2. **The dispatch** - a descriptor reaches the walk wherever it sits, not only at a
   chain position: nested inside another operator's result, or as a chain item of an
   expanded variable. There the routing is not consulted; the engine reads the
   descriptor's kind from its metadata and calls the applicator that kind's service
   registered. A kind the engine does not declare still applies.
3. **The chain step adapter** (`apply_chain_step`) - every kind service delegates its
   chain groups here: the run is wrapped as `ROOT[*descriptors, *stage.items]` and
   handed to the ordinary walk, so streaming, the item cap and the introspection
   short-circuit behave exactly as in a whole-forest call. One implementation serves
   all seven kind services; without it, each package would carry its own copy.

Without the engine, each package would need descriptor resolution, argument binding,
attribute-dependency resolution, origin marking, the recursion and the cap - seven
copies of one algorithm, drifting. What the extraction drew is the line between the
two halves of "applying an operator": a kind's *rules* (its declaration, its
applicator, its chain groups) live beside the package that owns it; the *machinery*
every kind shares lives in the engine.

### 3. Attribute runtime (`udan/attributes/`)
- Calculates attribute values for items (`calculate_attributes_in_forest`,
  `get_attribute_value` in `udan/attributes/api_attribute_runtime.py`)
- Stores computed attributes in storage
- Retrieves attribute values during filtering/grouping
- A plugin package's service: core names no attribute runtime, the package hands
  it to the context, the injector and the chain routing through its container
  decorations - a host without the package runs chains that compute nothing

### 4. Query processor (`udan/core/impl_query_processor.py`)
- Processes query trees from the parser
- Collects operators, attributes, and render specs
- Handles variable assignment (`:=name`) and reference (`$name`)

### 5. Debug logger (`udan/core/impl_debug_logger.py`)
- Provides debug logging functionality
- Toggled by the `debug` marker in queries, and per execution context

## Query Processing Flow

### 1. User Query -> Parse Tree
The user query is parsed into a parse tree by `QueryParserAPI.parse_text_to_tree()`
(`udan/parsing/impl_query_parser.py`). The leading `# q: ` prefix is optional - the
parser strips it when present. The parser supports:
- Function application syntax: `"fun x y"`
- Parentheses for grouping: `"f (g x) y"`
- Comma-separated chains: `'debug, fruits, grep berry'`
- Statement lists separated by `;` (each statement a ROOT child)
- String literals with escape sequences

The single text-to-tree implementation is `parse_tree()` in
`udan/parsing/impl_utils_parsing.py`; there is no alternative parser.

A parser extra rewrites the query before the parse (`QueryParserExtraAPI` in `udan/parsing/api_query_parser.py`): `register_parser_extra` / `unregister_parser_extra` on the parser transform the query **text** after prefix removal and comment stripping, before udan's own heuristics and before the parse - the text they return is the text the parser parses. Extras are just transformers: registered, applied in registration order (each seeing the previous one's output), unregistered.

The processor's half of the extras is a decoration instead of a registration (the question sugar, `udan/plugins_help_sugar`): the resolver resolves the tree as parsed, and the plugin's private helpers `_decorate_query_processor` / `_unwrap_query_processor` (`plugins_help_sugar.py`) take the running processor and swap in a decorated `resolve_query` - patched so the sugar rewrites question-shaped nodes (`gi`, `git.`, `:?json`, `:name ?`, a glued `word?` argument) into applications of the question tool `?` (the alias the listing family `udan/plugins_tools_core/plugins_help.py` registers) - and a patched `answer_miss`, so a lookup that finds nothing continues: the resolver raises a `QueryMiss` (`udan/core/api_query_processor.py` - the typed fragment, the kind, the reason, no answer of its own), the chain interpreter asks the processor's `answer_miss`, and whatever is decorated in decides what the query continues with; `None` turns the miss into the query error. The decorated resolver is the resolver itself - both decorated points are consulted on the resolver (the swap point asks its own `answer_miss`, a variable assignment re-enters its own `resolve_query`), so a decorated twin would never be asked either question. The PLUGIN's attach/detach decorate and undecorate (attach remembers the replaced methods; detach puts them back). A chain-blind tool declares `wants_item_types` and the walk hands it the chain's item types, the same declaration-driven shape as `overrides_output`. The query language itself names no tool and carries no answer.

### 2. Parse Tree -> Forest with Descriptors
The parse tree is resolved into a forest containing tool descriptors by the query
processor's `resolve_query()` (`udan/core/impl_query_processor.py`). The resolver:
- Traverses the parse tree
- Binds arguments to operators
- Supports nested query structures and complex expressions
- Handles operator aliases via `metadata.meta.get("aliases", [])`
- Uses `metadata.tool_type` to determine tool kind (inserter, filter, extender, render, attribute, ...)

### 3. Descriptor Application
Descriptors in the forest are applied:
- A descriptor names a tool; the tools registry resolves the name or alias to its
  metadata and function - there is no per-operator registry and no `operator:`-prefixed
  identity string
- The operators engine dispatches by kind: it reads the kind off the descriptor's
  metadata and calls the applicator that kind's service registered
- Descriptors are expanded recursively through the tree
- Extender operators support recursive extension based on `max_depth`
  (`OperatorDescriptor.get_max_depth()`, `udan/core/api_operators.py`)
- Result is a forest without operator descriptors, containing only data items

**OperatorContext**: during application, an `OperatorContext` object is passed to
operators (`udan/operator/impl_operator_engine.py`) containing:
- `depth`: current depth in the tree (integer)

**Application order example**: `'debug, fruits, grep berry'`
- The `debug` marker enables debug logging (it is not a tool)
- `fruits` inserter runs: inserts fruit items
- `grep berry` filter runs: keeps the fruits whose name matches

### 4. Final Forest
The applied forest contains only simple items or descriptors, ready for rendering. The forest carries its `ForestTypeDescriptor` (`udan/core/api_type_system.py` - item type per level), which attribute calculation and the type system consume.

## Module Naming Convention

**Important**: Modules use `api_` and `impl_` prefixes for clear separation:

- **`api_*.py` files**: Public API definitions, interfaces, and type definitions
  - `api_exec_context.py` - ExecContextAPI
  - `api_forests.py` - Forest data structure APIs
  - `api_symbols_env.py` - SymbolsEnvAPI
  - `api_logger.py` - LoggerAPI
  - the operator wire format lives in the core: `api_operators.py` there; the engine contract
    is `udan/operator/api_operator_engine.py`
  - `api_*.py` - Other API definitions

- **`impl_*.py` files**: Implementation of APIs
  - `impl_exec_context.py` - ExecContext implementation
  - `impl_symbols_env.py` - SymbolsEnv implementation
  - the operators engine is the `udan/operator` subpackage: `impl_operator_engine.py` there
  - `impl_query_processor.py` - QueryProcessor implementation
  - `impl_types_registry.py` - TypesRegistry implementation
  - `impl_udan_context.py` - UdanContext facade
  - `impl_*.py` - Other implementations

Plugin modules use `plugins_` prefix, one module per domain inside its package:
- `udan/plugins_tools_core/plugins_system.py` - system introspection
- `udan/plugins_tools_examples/plugins_builtins.py` - general-purpose operators
- `udan/plugins_tools_demo/plugins_demo.py` - demo operators
- `udan/plugins_tools_examples/plugins_*.py` - domain plugins (fs, git, org, markdown, ...)
- `udan_plugins_*/plugins_*.py` - external plugin packages

**Key principle**: `api_*` defines interfaces, `impl_*` provides implementations.

## Variables System

Variables allow storing and retrieving query results:

- **Variable assignment**: `:=name (expr)` stores the result of a sub-expression
- **Variable reference**: `$name` retrieves a stored forest
- Implemented in `udan/core/impl_query_processor.py` (QueryProcessor)
- Variables are stored in `SymbolsEnvAPI` (`udan/core/impl_symbols_env.py`)
- Statements in one query are separated by `;`

Example:
```
results := (fruits, sort_by_field id); $results
```

## Configuration System

The configuration system is `udan/core/config.py`, class `UdanConfig`
(pydantic-settings, `env_prefix=""`, `.env` file supported):

- `udan_tools_variables_defaults`: `dict[str, dict[str, Any]]` - default parameter values for tools
  (e.g. `{"insert_fruits": {"pattern": "apple"}}`)
- `udan_tools_preferences_input`: `dict[str, str]` - preferred tool aliases for ambiguous names
  (e.g. `{"diff": "git.insert_diff"}`)
- `udan_plugin_modules`: list of external modules to scan for `plugins_*.py`; defaults to every
  installed `udan_plugins_*` package. `UDAN_PLUGIN_MODULES` replaces the list, so omitting a
  package turns its capability off. udan's own plugin subpackages are scanned with the core and
  are not on this list.
- `udan_default_limit`: auto-limit applied after the chain, before rendering (0 disables it)
- `udan_cache_dir`, `udan_vars_path`, `udan_log_time`, `udan_types_enabled`

Environment variables carry the field names directly (no prefix):
`UDAN_TOOLS_VARIABLES_DEFAULTS`, `UDAN_TOOLS_PREFERENCES_INPUT`, `UDAN_PLUGIN_MODULES`, ...

Plugin packages own their config: a plugin module declares `CONFIG`, the config registry
serves validated instances by plugin name, and the env prefix comes from that declaration -
see `udan/plugins_history/history_config.py` (prefix `UDAN_HISTORY_`).

## Dependency Injection System

The injector is udan.core_tools_loading's (`api_function_injector.py`,
`impl_function_injector.py`): the contract is `FunctionInjectorAPI` - wrap a
function, set a per-query dependency, extend the globals, resolve by type - and
what counts as injected and what answers it are supplied, not guessed. A
function declares what it needs by annotation; the injector hides those
parameters from the signature the tool descriptors read and answers them at
call time: the globals first, the per-query overrides `set_dependency` wrote
second, then the `DependencySource` objects in list order (the first answer
that is not `MISSING` wins). A parameter nothing answers keeps its declared
default, or raises.

Udan's own answer is composition, not a subclass: `udan/core/impl_udan_injector.py` holds
the sources (`ContainerSource` over the container's services, `RegistrySource`
over the providers that stay registry-side, `DeclaredKeysSource` over the
per-query chain context), and `udan/core/impl_ioc.py` composes them into the injector it
serves under the `FunctionInjectorAPI` key.

### Key Components

1. **`@annotated` and `@annotated_dependency`** (`udan/core_tools_loading/api_annotated.py`):
   - `@annotated` declares a tool; `@annotated_dependency` marks a function as a
     dependency provider
   - Provider signature inferred from type annotations
   - Return type = what the provider provides
   - Parameter types = what the provider depends on

2. **`DependenciesRegistry`** (`udan/core/impl_dependencies_registry.py`, API in `api_dependencies_registry.py`):
   - Registers and resolves dependency providers
   - Tracks dependencies between providers
   - Supports singleton caching
   - `get_shared_providers()` lists what a hosting process may resolve

3. **`FunctionInjector`** (`udan/core_tools_loading/impl_function_injector.py`):
   - Classifies a function's parameters by the declared key set
   - Hides the injected parameters from the refined signature and annotations
   - Resolves them at call time: globals, overrides, sources

4. **The udan sources** (`udan/core/impl_udan_injector.py`, composed in `udan/core/impl_ioc.py`):
   - `ContainerSource`: the container's services, answered lazily into its one
     memo - an app-scoped service resolves to the same instance everywhere
   - `RegistrySource`: the dependency registry's remaining providers (the
     per-query ones)
   - `DeclaredKeysSource`: keys that count as injected although nothing answers
     them - the per-query chain context

### Example Usage

```python
# Package contribution (a plugin package's PLUGIN): the module declares the
# class, the scan builds it from nothing, and the CONFIG declaration is what
# makes the composition root synthesize the config factory
class HistoryPlugin(Plugin):
    @provide
    def history_logger(self, config: HistoryConfig) -> HistoryLoggerAPI:
        return create_history_storage(str(config.path))

    @provide
    def saved_storage(self, config: HistoryConfig) -> SavedQueriesAPI:
        return create_saved_storage(str(config.saved_path))

    def detach(self, history_logger: HistoryLoggerAPI, saved_storage: SavedQueriesAPI) -> None:
        history_logger.close()
        saved_storage.close()


DOMAIN = "history"
CONFIG = HistoryConfig
PLUGIN = HistoryPlugin
SUBSCRIBE = {CommandExecutedEvent: HistoryLoggerAPI}

# Inserter with auto-injected dependency
@annotated(meta={"tool_type": "inserter", "supported_renders": ["saved-item"]})
def saved(
    patterns: Annotated[list[str] | None, "vararg"] = None,
    saved_storage: SavedQueriesAPI | None = None,  # Auto-injected from the container
) -> Iterable[dict]:
    """Insert saved queries."""
```

### Resolution Order

1. The injector's global dependencies (the container's singletons)
2. The query-specific dependencies `set_dependency` wrote (the chain context)
3. The sources in list order: the dependency registry, then the declared keys
   (which answer nothing - a declared key falls through to the declared default)

## Main Module Entry Points

The CLI is `udan/parsing/main.py`; the console script is `udan`
(`udan = "udan.parsing.main:main_io"` in `pyproject.toml`).

- **`main(query: str, comment: str = "", debug: bool = False) -> str`**: executes a
  query and returns the rendered output string. No I/O on stdout - it prints nothing
  on success.
  - Composes the container, loads the core, parses, executes:

    ```python
    from udan.core.api_udan_context import UdanContextAPI
    from udan.core.config import UdanConfig
    from udan.core.impl_ioc import create_udan_container
    from udan.parsing.api_query_parser import QueryParserAPI

    container = create_udan_container(UdanConfig())
    ctx = container.get(UdanContextAPI).load_core()
    parser = container.get(QueryParserAPI)
    exec_ctx = ctx.create_exec_context(debug=debug)
    node = parser.parse_text_to_tree(query_text, exec_ctx)
    forest, _, _, out, _ = ctx.execute_query(node, exec_ctx, query_text=query_text)
    ```

  - `execute_query` resolves the tree with `QueryProcessorAPI.resolve_query()`,
    applies the descriptors, auto-limits, calculates attributes, renders with
    `RenderEngineAPI.render_forest()`, finalizes debug and logs history
  - The `# q: ` prefix on the query text is optional
  - On failure the advice goes to **stderr** and the process exits with code 1: a
    failed parse raises (the CLI catches it and prints `ExceptionWithAdvice.advice`,
    or the traceback when there is no advice), a failed resolve returns a `None`
    forest with the message as the output string, which the CLI treats the same way

- **`main_io()`**: reads the command-line arguments (`query`, `--comment`, `--debug`),
  calls `main`, prints the result. Entry point for CLI usage.
  - Example: `udan "debug, fruits, grep berry"`
    (or `uv run python -m udan.parsing.main "debug, fruits, grep berry"`)
