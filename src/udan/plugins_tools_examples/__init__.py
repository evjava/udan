"""udan.plugins_tools_examples: the file-format, source and built-in operator plugin families.

Owns the operators a udan host almost always wants beside the engine, one
family per module:

- ``plugins_json`` / ``plugins_yaml`` / ``plugins_csv`` / ``plugins_sql``:
  reading data files and databases as items (JSON/JSONL, jq-like YAML
  paths, CSV rows, sqlite tables)
- ``plugins_org`` (+ ``plugins_org_parser``) / ``plugins_markdown``: reading
  org-mode files and markdown outlines as items, with duplicate-heading
  detection shared through the dev family
- ``plugins_dev``: tree-sitter based code queries and the ``Duplication``
  helper the org and markdown families reuse
- ``plugins_test_tracing``: the trace-test functions the tracing tests run
  against
- ``plugins_fs`` / ``plugins_git`` / ``plugins_web`` / ``plugins_shell`` /
  ``plugins_peval``: the environment families - filesystem, git and web
  sources, the shell and the python-expression pipe
- ``plugins_builtins`` (+ ``plugins_builtins_set_operations``): the built-in
  operators (help, grep, sgrep, unique) with the essential renders
  (``raw``, ``introspect-item``) and the set operations over variables
- ``plugins_tags`` / ``plugins_dot`` / ``plugins_mock``: tag grouping, DOT
  (Graphviz) diagrams and the mock tools the rename-workflow tests
  simulate with

``utils_file_line`` holds the file:line helper; ``utils_tables`` (the row helper
these families share with the render engine) moved to the core beside the other
``utils_*`` modules when the render engine did. ``api_types`` holds ``ASTChunk``, the code-chunk
item type the source-analysis families extract and render - the python
plugin's AST extractors answer with it too.

A host that leaves this package out builds a container whose format queries
fail with the advice that says what is missing: the chain still applies and
computes, nothing reads a file or a database.
"""
