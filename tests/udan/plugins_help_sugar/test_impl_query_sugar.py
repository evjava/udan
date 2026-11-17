"""Tests for the question sugar: every rewrite of the table, tree by tree, and idempotence."""

import pytest

import udan.attributes.plugins_operators_attribute
import udan.plugins_tools_core.plugins_help
import udan.plugins_tools_core.plugins_system
import udan.plugins_tools_examples.plugins_builtins
import udan.plugins_tools_examples.plugins_fs
import udan.plugins_tools_examples.plugins_json
import udan.renders.plugins_renders
from tests.conftest import make_qp
from udan.core.api_constants import NODE_ROOT_ITEM, NODE_STRING_PREFIX
from udan.core.api_forests import Node
from udan.core.config import UdanConfig
from udan.parsing.impl_query_parser import QueryParser
from udan.parsing.impl_utils_parsing import parse_tree
from udan.plugins_help_sugar.impl_query_sugar import QuerySugar, _named_argument_key, _question_word
from udan.plugins_history import plugins_history
from udan.plugins_tools_demo import plugins_demo, plugins_fruits


@pytest.fixture
def ctx_with_plugins(make_ctx):
    """Context with demo, builtins, system, history, renders, and fs tools."""
    return make_ctx(
        plugins_demo,
        plugins_fruits,
        udan.plugins_tools_examples.plugins_builtins,
        udan.plugins_tools_core.plugins_help,
        udan.plugins_tools_core.plugins_system,
        plugins_history,
        udan.attributes.plugins_operators_attribute,
        udan.renders.plugins_renders,
        udan.plugins_tools_examples.plugins_fs,
        udan.plugins_tools_examples.plugins_json,
    )


@pytest.fixture
def sugar(ctx_with_plugins):
    """The sugar over the same registry the queries run against."""
    return QuerySugar(ctx_with_plugins.registry)


@pytest.fixture
def sugar_with_preference(make_ctx):
    """The sugar over a registry configured with one qualified tool preference."""
    ctx = make_ctx(
        udan.plugins_tools_examples.plugins_builtins,
        udan.plugins_tools_core.plugins_help,
        udan.plugins_tools_core.plugins_system,
        config=UdanConfig(udan_tools_preferences_input={"dif": "git.insert_diff"}),
    )
    return QuerySugar(ctx.registry)


@pytest.fixture
def query_parser():
    """The parser: question syntax only, so the sugar's inputs are what a query produces."""
    return QueryParser()


def lowered(sugar: QuerySugar, query_text: str) -> Node:
    """The single statement a query resolves from: parsed, then run through the sugar."""
    tree = sugar.transform_query_tree(parse_tree(query_text, unwrap_single_roots=False))
    return tree.children[0] if tree.children else tree


# --- The expansion: incomplete tool names typed as chain items


@pytest.mark.parametrize(
    "query_text, expected",
    [
        ("gi", Node.create("?", [Node.leaf("--pattern=gi")])),
        ("re-pl", Node.create("?", [Node.leaf("--pattern=re-pl")])),
        ("git.", Node.create("?", [Node.leaf("--pattern=git.")])),
        ("fs.", Node.create("?", [Node.leaf("--pattern=fs.")])),
    ],
)
def test_expand_incomplete_leaf(sugar, query_text, expected):
    """A short word and a domain dot become the pattern question."""
    assert lowered(sugar, query_text) == expected


@pytest.mark.parametrize(
    "query_text",
    [
        "range",  # an exact key
        "vars",  # an exact key
        "uniq",  # an alias key
        "g",  # a single character is too short
        "g.",  # a single-character domain is too short
        "raiser",  # a 6-char word may be a real tool
        "filter",  # 6 chars
        "123",  # a number is data
        "$var",  # a variable reference
        "git hub.",  # the dot-word is an argument, not a chain item
        "fruits, gi",  # a chain item is the resolver's judge, not the expansion's
        "range 5, sort",  # a question's tail never becomes a question of its own
    ],
)
def test_expand_incomplete_leaf_keeps_other_shapes(sugar, query_text):
    """Exact keys, numbers, single characters, long words and arguments keep their nodes."""
    assert lowered(sugar, query_text) == parse_tree(query_text, unwrap_single_roots=False).children[0]


def test_expand_incomplete_leaf_inside_parens(sugar):
    """A whole-query word inside parens expands too: the parens wrap one statement."""
    assert lowered(sugar, "(gi)") == Node.create(NODE_ROOT_ITEM, [Node.create("?", [Node.leaf("--pattern=gi")])])


def test_expand_incomplete_leaf_keeps_string_literals(sugar):
    """A quoted short word is data: the string marker never becomes a pattern."""
    assert lowered(sugar, '"gi"').item.startswith(NODE_STRING_PREFIX)


def test_expand_prefers_the_preferred_name(sugar_with_preference):
    """A preference key becomes the preferred tool's qualified name, not a question."""
    assert lowered(sugar_with_preference, "dif") == Node.leaf("git.insert_diff")


# --- The render question


def test_lower_render_question(sugar):
    """`:?pattern` becomes the render-filtered question."""
    assert lowered(sugar, ":?fru") == Node.create("?", [Node.leaf("--tool_type=render"), Node.leaf("--pattern=fru")])
    assert lowered(sugar, ":?") == Node.create("?", [Node.leaf("--tool_type=render")])


def test_lower_render_question_lowers_bare_colon(sugar):
    """Bare `:` asks the same question as `:?` - which renders fit here."""
    chain = lowered(sugar, "fruits, :")
    assert chain.children[1] == Node.create("?", [Node.leaf("--tool_type=render")])


def test_lower_render_question_keeps_render_application(sugar):
    """`:render-name` (with or without args) is an application, not a question."""
    chain = lowered(sugar, "fruits, :raw x")
    assert chain.children[1].item == ":raw"


# --- The render docs


def test_lower_render_docs(sugar):
    """`:render ?` becomes the render docs application with the render name."""
    chain = lowered(sugar, "fruits, :raw ?")
    assert chain.children[1] == Node.create("render_help", [Node.leaf("--render_name=raw")])


def test_lower_render_docs_resolves_short_name(sugar):
    """A short render name resolves by unique substring, like the resolver resolves `:name`."""
    assert lowered(sugar, ":forma ?") == Node.create("render_help", [Node.leaf("--render_name=render_format")])


def test_lower_render_docs_keeps_ambiguous_short_name(sugar):
    """A short name matching several render keys keeps the node: the resolver reports them."""
    chain = lowered(sugar, "fruits, :jso ?")

    assert chain.children[1].item == ":jso"


def test_lower_render_docs_keeps_unknown_render(sugar):
    """A `?` after an unknown render name keeps the node: the resolver reports available renders."""
    chain = lowered(sugar, "fruits, :nonexistent_render ?")
    assert chain.children[1].item == ":nonexistent_render"


# --- The argument questions


def test_lower_argument_question_lists_the_word(sugar):
    """A glued `word?` argument asks about the word: the application becomes the question."""
    chain = lowered(sugar, '"src", extend_by_inserter ls_files?')
    assert chain.children[1] == Node.create("?", [Node.leaf("--pattern=ls_files")])


def test_lower_argument_question_shows_tool_docs(sugar):
    """A separated bare `?` argument asks for the application tool's docs, name as typed."""
    assert lowered(sugar, "filter_field ?") == Node.create("introspect_tool", [Node.leaf("--tool_name=filter_field")])


def test_lower_argument_question_resolves_substring(sugar):
    """A bare `?` after a unique substring asks for the docs of the tool it names."""
    assert lowered(sugar, "filter_fiel ?") == Node.create("introspect_tool", [Node.leaf("--tool_name=filter_field")])


def test_lower_argument_question_resolves_dashed_name(sugar):
    """A bare `?` after a dashed name asks for the docs of the underscored tool."""
    assert lowered(sugar, "insert-ls-files ?") == Node.create(
        "introspect_tool", [Node.leaf("--tool_name=insert_ls_files")]
    )


def test_lower_argument_question_lists_ambiguous_name(sugar):
    """Several substring matches are a "which tool did I mean?" question: the listing answers."""
    assert lowered(sugar, "extend ?") == Node.create("?", [Node.leaf("--pattern=extend")])


def test_lower_argument_question_keeps_unknown_name(sugar):
    """A bare `?` after an unknown name keeps the docs application: it reports the miss."""
    assert lowered(sugar, "nonexistent_tool ?") == Node.create(
        "introspect_tool", [Node.leaf("--tool_name=nonexistent_tool")]
    )


def test_lower_argument_question_keeps_render_application(sugar):
    """A render application is not a tool the argument questions could be about."""
    chain = lowered(sugar, 'fruits, :raw "x?"')

    assert chain.children[1].item == ":raw"


# --- The argument filter on chain-level questions


@pytest.mark.parametrize(
    "query_text, expected_children",
    [
        ("? fruits", [Node.leaf("fruits")]),
        ("? --group=type", [Node.leaf("--group=type")]),
        ("? group=type", [Node.leaf("group=type")]),
        ("? a b", [Node.leaf("a")]),
        ("? a b --group=type", [Node.leaf("a"), Node.leaf("--group=type")]),
        ("? (range 3)", []),
        ("? name=apple", [Node.leaf("name=apple")]),
    ],
)
def test_filter_question_arguments(sugar, query_text, expected_children):
    """Only the pattern word and the listing filters survive on a chain-level question."""
    assert lowered(sugar, query_text) == Node.create("?", expected_children)


def test_filter_question_arguments_keeps_argument_position(sugar):
    """An argument-position `?` is not a chain-level question: the filter leaves it in place
    (this application survives the sugar because the render name resolves to nothing)."""
    chain = lowered(sugar, "fruits, :nonexistent_render ?")

    assert chain.children[1].children[-1].item == "?"


# --- Idempotence (the extras re-run per desugared subquery)


@pytest.mark.parametrize(
    "query_text",
    [
        "gi",
        "git.",
        "range 5, extend?",
        "fruits, :",
        "fruits, :raw ?",
        '"src", extend_by_inserter ls_files?',
        "filter_field ?",
        "? fruits --group=type",
        "range? 3",
    ],
)
def test_sugar_is_idempotent(sugar, query_text):
    """Re-running the sugar on its own output changes nothing."""
    once = lowered(sugar, query_text)

    assert sugar.transform_query_tree(once.model_copy(deep=True)) == once


# --- The question resolves through the alias to the same listing


def test_question_form_equals_written_form(ctx_with_plugins):
    """`? filt` and the explicit listing-filtered query produce the same output."""
    qp_with_plugins = make_qp(ctx_with_plugins)
    _, _, _, out_sugar, _ = qp_with_plugins.execute_query_split_debug("? filt")
    _, _, _, out_written, _ = qp_with_plugins.execute_query_split_debug("help --pattern=filt")

    assert out_sugar == out_written
    assert "filter_by_attribute" in out_sugar


# --- The moved helpers


@pytest.mark.parametrize(
    "item, expected",
    [
        ("ls_files?", "ls_files"),
        ("git.diff?", "git.diff"),
        ("re-pl?", "re-pl"),
        # Tokens of other syntax are values, their `?` is data
        ("__STRING__why?", None),
        ("--flag?", None),
        ("name=apple?", None),
        ("$v?", None),
        ("?", None),
        ("extend??", None),
        (123, None),
    ],
)
def test_question_word(item, expected):
    """Only a bare word with a trailing `?` carries a question."""
    assert _question_word(item) == expected


@pytest.mark.parametrize(
    "item, expected",
    [
        ("--group=type", "group"),
        ("--pattern=fil", "pattern"),
        ("group=type", "group"),
        ("name=apple", None),
        ("range", None),
        ("--flag", "flag"),
    ],
)
def test_named_argument_key(item, expected):
    """Dash forms are always named arguments, a bare `key=value` only for a known key."""
    assert _named_argument_key(item, {"group", "pattern"}) == expected
