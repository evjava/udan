"""udan.plugins_help_sugar: the question sugar.

The `?` question has two halves. The syntax is the query language's: the atom,
its postfix move and the incomplete-query completions live in
``udan.parsing.impl_query_parser``, which names no tool. The meaning is this
package's, in the two shapes the resolver meets it:

- ``impl_query_sugar``, the tree transformer that turns every question-shaped
  node (`gi`, `git.`, `:?json`, `:name ?`, a glued `word?` argument, an
  argument's bare `?`) into the application that answers it, before the
  resolver's main work;
- ``impl_miss_answers``, the answerer that continues a lookup that found
  nothing (an ambiguous name, an unknown render, a missing `at_d`) with the
  question narrowed to what the query typed.

``plugins_help_sugar``'s decorate/undecorate pair patches both onto the
query processor - the sugar onto ``resolve_query``'s input, the answerer onto
``answer_miss`` - and the PLUGIN's attach/detach applies and removes it. What
the question resolves *to* is not decided here: the `?`
atom is the alias of the listing family in
``udan.plugins_tools_core.plugins_help`` (which also declares that it wants the
chain's item types), and the docs lowerings name the per-tool docs tools in
``udan.plugins_tools_core.plugins_system``.
"""
