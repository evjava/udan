"""The question sugar: what the question atom means, as one query-tree transformer.

The parser owns question *syntax* - the `?` atom, its postfix move, the
incomplete-query completions - and names no tool; this module owns question
*meaning*: that `gi` asks for the tools containing `gi`, that `:?json` asks which
renders fit, that `:name ?` asks a render's docs, that a glued `word?` argument
asks about the word. Every rewrite lands on the same node shape - an application
of the question tool `?` (the alias the listing family in
``plugins_tools_core.plugins_help`` registers), or of the per-tool docs tools in
``plugins_tools_core.plugins_system`` - so the resolver reads ordinary applications,
and the chain-types annotation reaches every question for free.

The package's PLUGIN wraps it on the query processor (the decorator's
``resolve_query`` patch), and it runs before the resolver's main work.
Resolution recurses (a variable assignment resolves its right-hand side through
the same entry point), so the sugar runs more than once per query; every
rewrite is shape-matched and re-running the walk on its own output changes
nothing.
"""

import re
from collections.abc import Callable

from udan.core.api_constants import NODE_ROOT_ITEM, NODE_STRING_PREFIX, QUESTION_OPERATOR
from udan.core.api_forests import Node
from udan.core_tools_loading.api_tools_registry import ToolsRegistryAPI
from udan.parsing.api_query_parser import parse_named_argument
from udan.renders.api_renders import RENDER

# The per-tool docs the argument-position questions name (plugins_tools_core family).
_TOOL_DOCS_OPERATOR = "introspect_tool"
_RENDER_DOCS_OPERATOR = "render_help"

_MIN_DOMAIN_LENGTH = 2
_MIN_OPERATOR_CHARS = 2
_MAX_OPERATOR_CHARS = 5
_IDENTIFIER_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_-]*$"

# A bare word with a trailing question mark, the glued question the parser leaves
# in argument position (see _replace_postfix_question in impl_query_parser).
_QUESTION_WORD_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_.\-]*\?")


def _is_argument_child(parent: Node | None) -> bool:
    """Is the node an argument of an application rather than a chain item?

    Chain items live under ROOT, CHAIN or an assignment; everything else that
    holds a node is an application head. The chain-level rewrites (the expansion,
    the render question, the argument filter) match only there; an
    argument-position question belongs to the per-tool docs lowering instead.

    Args:
        parent: Parent of the node, or None at the tree root

    Returns:
        True when the node is an application argument
    """
    if parent is None or not isinstance(parent.item, str):
        return False
    return not (parent.item in (NODE_ROOT_ITEM, "CHAIN") or parent.item.startswith(":="))


def _named_argument_key(item: str, known_keys: set[str]) -> str | None:
    """Parameter name of a named-argument leaf, None for positional text.

    Dash forms (`--key=value`, `--flag`) are named arguments whatever the key is -
    the resolver reports the unknown ones as an error. A bare `key=value`
    counts only when the key is a known parameter, otherwise it stays positional
    text (e.g. the `name=apple` filter the user is typing for the tool the
    question is about).

    Args:
        item: The argument text from the tree leaf
        known_keys: Parameter names of the tool

    Returns:
        The parameter name, or None when the argument is positional text
    """
    if not item.startswith("--"):
        key = item.partition("=")[0].strip()
        return key if "=" in item and key in known_keys else None
    parsed = parse_named_argument(item, known_keys)
    return None if parsed is None else parsed[0]


def _question_word(item: object) -> str | None:
    """The word a glued `?` asks about, None when the argument is not one.

    A `word?` in argument position does not move to the prefix question form,
    so it reaches the tree glued, and the word it carries is the question. Only a
    bare word asks: string literals (`__STRING__why?`), named arguments
    (`--flag?`), keyvals (`name=apple?`) and variable references (`$v?`) are values
    whose `?` is data, and a bare `?` is the per-tool docs form.

    Args:
        item: The query node item

    Returns:
        The word without its question mark, or None when the item is not a glued question
    """
    if not isinstance(item, str) or item.startswith(NODE_STRING_PREFIX):
        return None
    match = _QUESTION_WORD_PATTERN.fullmatch(item)
    return match.group(0)[:-1] if match else None


def _question_arguments(children: list[Node], known_keys: set[str]) -> list[Node]:
    """Pick the question arguments the listing understands.

    A question means "I am writing this tool - show its help": the
    pattern word and the listing filters (`--group=type`, `--pattern=fil`)
    describe the listing, so they are kept. The text typed after the question
    word is the rest of the query the user is about to run (`range? 3`,
    `filter? name=apple`); handing it to the listing would only turn it into
    filters that silently empty it, so it is dropped, and the listing is the one
    the written `range?` shows.

    Args:
        children: Argument nodes of the question
        known_keys: Parameter names the listing accepts

    Returns:
        Nodes to build the question application from
    """
    kept: list[Node] = []
    pattern_kept = False
    for child in children:
        if child.children:
            continue  # a subquery the user is writing, not a listing filter
        item = child.item
        key = _named_argument_key(item, known_keys) if isinstance(item, str) else None
        if key is not None:
            if key in known_keys:
                kept.append(child)
            continue
        if not pattern_kept:
            kept.append(child)
            pattern_kept = True
    return kept


def _apply_transformers(
    node: Node,
    transformers: list[Callable[[Node, Node | None], Node]],
    parent: Node | None = None,
) -> Node:
    """Apply tree transformers to a node, then recursively to the children of the result.

    Transformers run in list order on every node, so a transformer sees the nodes
    produced by the earlier ones; each receives the node's parent, which lets it
    match on position as well as shape.

    Args:
        node: The tree to transform
        transformers: List of (node, parent) -> node transforms, applied in order
        parent: Parent of the whole tree, or None

    Returns:
        Transformed tree
    """
    for transform in transformers:
        node = transform(node, parent)
    node.children = [_apply_transformers(child, transformers, node) for child in node.children]
    return node


class QuerySugar:
    """The question's meaning: every question-shaped node becomes the application that answers it."""

    def __init__(self, registry: ToolsRegistryAPI) -> None:
        """Initialize the sugar.

        Args:
            registry: Tools registry - read for the question tool's parameters
                (the argument filter), the render keys (the docs lowering), and
                the exact keys and preferences (the expansion)
        """
        self._registry = registry
        # The rewrites of 3.5, in order: the docs lowering must precede the
        # argument questions (an application cannot be both), and the argument
        # filter runs last so it also reads the applications the earlier
        # rewrites produced.
        self._transformers: list[Callable[[Node, Node | None], Node]] = [
            self._expand_incomplete_leaf,
            self._lower_render_question,
            self._lower_render_docs,
            self._lower_argument_question,
            self._filter_question_arguments,
        ]

    def transform_query_tree(self, query_tree: Node) -> Node:
        """Rewrite every question-shaped node into the application that answers it.

        Args:
            query_tree: The parsed query tree, the parser's question syntax intact

        Returns:
            The rewritten tree (the new root; may rebuild or mutate in place)
        """
        return _apply_transformers(query_tree, self._transformers)

    def _question_parameter_names(self) -> set[str]:
        """Parameter names the question tool accepts from the query text.

        The argument filter keeps only the arguments that describe the listing,
        and those are the same parameters the descriptor factory binds for the
        written `?` form.

        Returns:
            Set of parameter names, empty when the question tool is not registered
        """
        metadata = self._registry.get_metadata(QUESTION_OPERATOR)
        if metadata is None:
            return set()
        return set(metadata.parameters.get("properties", {}))

    def _expand_incomplete_leaf(self, node: Node, parent: Node | None) -> Node:
        """Expand an incomplete tool name typed as the whole query into its question.

        `gi` asks for the tools containing `gi`, and `git.` for the git domain,
        so both become `? --pattern=...` - the same listing the written `? gi`
        shows. A preference key is a "this text means that tool" note, so the
        leaf becomes the qualified preferred name and the resolver resolves it
        like any written tool name. Exact keys, numbers and everything else keep
        their nodes: a number is data, an exact key is already a tool, and a
        longer or punctuated word is a query or a value the resolver judges.

        The word must be the query by itself: inside a chain or a statement list
        the word is judged by the resolver instead - its substring matches, its
        preference notes and its miss listings answer a bare word there, which
        keeps a question's tail (`range 5, extend? , sort`) from becoming a
        question of its own.

        Args:
            node: The tree node to transform
            parent: Parent of the node, or None at the tree root

        Returns:
            The question application (or the preferred name), or the node
            unchanged when it is not the matched shape
        """
        if node.children or _is_argument_child(parent):
            return node
        # The statement-list root with one child is a whole-query word; anything
        # else (a chain item, a statement beside others) is judged by the resolver
        if parent is not None and not (
            isinstance(parent.item, str) and parent.item == NODE_ROOT_ITEM and len(parent.children) == 1
        ):
            return node
        item = node.item
        if not isinstance(item, str) or item.startswith(NODE_STRING_PREFIX):
            return node
        # A preference key: the leaf becomes the preferred tool's qualified name
        # (unqualified preferences are left for the resolver's ambiguity report)
        preferred = self._registry.get_preferences().get(item)
        if preferred is not None and "." in preferred:
            return Node.leaf(preferred)
        if item in self._registry.get_tools():
            return node  # an exact key (or alias) is already addressable as-is
        if item.endswith("."):
            domain = item[:-1]
            # The dot asks for a domain's tools: 2+ identifier characters make
            # the prefix meaningful ("git." lists git, "g." stays for the resolver)
            if len(domain) >= _MIN_DOMAIN_LENGTH and re.match(_IDENTIFIER_PATTERN, domain):
                return Node.create(QUESTION_OPERATOR, [Node.leaf(f"--pattern={item}")])
        # A short identifier word is full-text search: 2-5 characters keeps known
        # longer tool names ("raiser") and data words from becoming listings
        if re.match(_IDENTIFIER_PATTERN, item) and _MIN_OPERATOR_CHARS <= len(item) <= _MAX_OPERATOR_CHARS:
            return Node.create(QUESTION_OPERATOR, [Node.leaf(f"--pattern={item}")])
        return node

    def _lower_render_question(self, node: Node, parent: Node | None) -> Node:
        """Lower the `:` / `:?pattern` render-question sugar to the render-filtered question.

        `:`, `:?` and `:?pattern` become `? --tool_type=render` with the glued
        text as the pattern, in any chain position: bare `:` and `:?` ask the same
        question ("which renders fit here?"), so they lower to the same tree and
        the resolver answers both through the pipeline. Render application
        (`:render-name`) is not touched (`:name?` is rewritten to `:?name` by the
        parser's postfix move before parsing); an argument-position `:` keeps its
        node (see `_is_argument_child`) and reaches the resolver's bare-`:` report.

        Args:
            node: The tree node to transform
            parent: Parent of the node, or None at the tree root

        Returns:
            The lowered node, or the node unchanged when it is not the matched shape
        """
        if _is_argument_child(parent):
            return node
        item = node.item
        if not (isinstance(item, str) and item.startswith(":")):
            return node
        pattern = item[1:]
        if pattern and not pattern.startswith("?"):
            return node  # :name - a render application, not a render question
        args = [Node.leaf("--tool_type=render")]
        pattern = pattern[1:]
        if pattern:
            args.append(Node.leaf(f"--pattern={pattern}"))
        return Node.create(QUESTION_OPERATOR, args)

    def _lower_render_docs(self, node: Node, parent: Node | None) -> Node:
        """Lower the render docs sugar `:render-name ?` to the render docs operator.

        The `?` argument means "show me this render's parameters", so it never
        reaches the render's argument handling in the resolver. A short render
        name is resolved to its render key by unique substring (matching the
        ":name" resolution in the resolver); a name that stays ambiguous or
        unknown is left for the resolver's render path, which reports it with
        the available renders.

        Args:
            node: The tree node to transform
            parent: Parent of the node, or None at the tree root (unused; kept
                for the transformer signature)

        Returns:
            The lowered node, or the node unchanged when it is not the matched shape
        """
        del parent
        item = node.item
        if not (isinstance(item, str) and item.startswith(":") and len(item) > 1 and not item.startswith(":?")):
            return node
        if not node.children or node.children[-1].item != "?":
            return node
        render_name = item[1:]
        renders = self._registry.get_tools(kind=RENDER)
        if render_name not in renders:
            # Short render name: resolve it like ":name" in the resolver --
            # unique substring among render keys. Ambiguous or unknown names are
            # left for the resolver's render path to report.
            matched = [tool_key for tool_key in renders if render_name in tool_key]
            if len(matched) != 1:
                return node
            render_name = matched[0]
        return Node.create(_RENDER_DOCS_OPERATOR, [Node.leaf(f"--render_name={render_name}")])

    def _lower_argument_question(self, node: Node, parent: Node | None) -> Node:
        """Replace an application that asks a question with the application that answers it.

        A glued `word?` argument asks about the word (`extend_by_inserter
        ls_files?`), not about the tool the argument belongs to: the listing of
        the word replaces the application, like the chain-level `? word` does. A
        separated bare `?` asks for the docs of the application's tool
        (`filter_field ?`); this runs before the resolver, so the tool name is
        still the typed one and `_tool_docs_application` resolves it.

        Args:
            node: The tree node to transform
            parent: Parent of the node, or None at the tree root (unused; kept
                for the transformer signature)

        Returns:
            The answering application, or the node unchanged when it asks for none
        """
        del parent
        if not node.children or not isinstance(node.item, str):
            return node
        item = node.item
        # Structural heads (statements, chains, assignments), render applications
        # and string literals are not tools the questions below could be about
        if item in (NODE_ROOT_ITEM, "CHAIN") or item.startswith((":=", ":", NODE_STRING_PREFIX)):
            return node
        asked = next((word for child in node.children if (word := _question_word(child.item)) is not None), None)
        if asked is not None:
            return Node.create(QUESTION_OPERATOR, [Node.leaf(f"--pattern={asked}")])
        if any(child.item == "?" for child in node.children):
            return self._tool_docs_application(item)
        return node

    def _tool_docs_application(self, typed_name: str) -> Node:
        """The docs application for a tool asked by name as typed.

        An exact key, an alias or a unique substring asks for its docs (the same
        page either way); several substring matches are a "which tool did I
        mean?" question, answered by the listing narrowed to the typed name. A
        name matching nothing keeps the docs application: the docs tool reports
        the unknown name, like the resolver does for a written unknown tool.

        Args:
            typed_name: The tool name as the query typed it

        Returns:
            The application answering the docs question
        """
        matches = self._name_matches(typed_name)
        if len(matches) == 1:
            return Node.create(_TOOL_DOCS_OPERATOR, [Node.leaf(f"--tool_name={matches[0]}")])
        if len(matches) > 1:
            return Node.create(QUESTION_OPERATOR, [Node.leaf(f"--pattern={typed_name}")])
        return Node.create(_TOOL_DOCS_OPERATOR, [Node.leaf(f"--tool_name={typed_name}")])

    def _name_matches(self, typed_name: str) -> list[str]:
        """Registry keys the typed name names, in resolution order.

        An exact key or alias is the whole answer; otherwise the
        domain-qualified form ("domain.name") matches its tool; otherwise the
        canonical keys containing the typed name do. Only canonical names are
        collected: an alias key would duplicate its tool's match. The typed
        name's underscored spelling is tried when the typed one matches nobody,
        the resolver's dash sugar (`insert-diff` names `insert_diff`); a
        hyphenated name of its own is never rewritten.

        Args:
            typed_name: The tool name as the query typed it

        Returns:
            Canonical registry keys, one when the name is unambiguous
        """
        matches = self._spelled_name_matches(typed_name)
        sugared = typed_name.replace("-", "_")
        if not matches and sugared != typed_name:
            matches = self._spelled_name_matches(sugared)
        return matches

    def _spelled_name_matches(self, typed_name: str) -> list[str]:
        """Registry keys one spelling of the typed name names, in resolution order.

        Args:
            typed_name: The tool name as the spelling writes it

        Returns:
            Canonical registry keys, one when the name is unambiguous
        """
        metadata = self._registry.get_metadata(typed_name)
        if metadata is not None:
            return [metadata.name]
        base, separator, name = typed_name.rpartition(".")
        if separator:
            qualified = self._registry.get_metadata(name)
            if qualified is not None and qualified.meta.get("domain") == base:
                return [qualified.name]
        return [
            key
            for key in self._registry.get_tools()
            if typed_name in key
            and (key_metadata := self._registry.get_metadata(key)) is not None
            and key_metadata.name == key
        ]

    def _filter_question_arguments(self, node: Node, parent: Node | None) -> Node:
        """Keep in a chain-level `?` application only the arguments the listing understands.

        The question tool's own arguments are bound by the resolver like any
        tool's, so an argument the listing does not declare would bind into one
        of its filters and silently empty it; see `_question_arguments` for what
        is kept and why the rest is dropped. Argument-position `?` nodes are
        other features (the per-tool docs, the render docs) and keep their nodes
        (see `_is_argument_child`).

        Args:
            node: The tree node to transform
            parent: Parent of the node, or None at the tree root

        Returns:
            The filtered application, or the node unchanged when it is not the matched shape
        """
        if _is_argument_child(parent) or not isinstance(node.item, str) or node.item != QUESTION_OPERATOR:
            return node
        known_keys = self._question_parameter_names()
        return Node.create(QUESTION_OPERATOR, _question_arguments(node.children, known_keys))
