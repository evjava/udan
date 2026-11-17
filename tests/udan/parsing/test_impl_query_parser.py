"""Tests for question mark introspection in query parsing (`word?` and `?word` -> `? word`)."""

import pytest
from lark.exceptions import UnexpectedCharacters

import udan.attributes.plugins_operators_attribute
import udan.plugins_tools_core.plugins_help
import udan.plugins_tools_core.plugins_system
import udan.plugins_tools_examples.plugins_builtins
import udan.plugins_tools_examples.plugins_fs
import udan.renders.plugins_renders
from tests.conftest import make_qp
from udan.core.api_constants import NODE_STRING_PREFIX
from udan.core.api_exceptions import ExceptionWithAdvice
from udan.core.api_forests import Node
from udan.core.impl_debug_logger import DebugLogger
from udan.core.impl_exec_context import ExecContext
from udan.parsing.impl_query_parser import QueryParser, _move_postfix_questions, _strip_comments
from udan.plugins_history import plugins_history
from udan.plugins_tools_demo import plugins_demo, plugins_fruits


@pytest.mark.parametrize(
    "query_text, expected",
    [
        ("extend?", "? extend"),
        ("range 5, extend?", "range 5, ? extend"),
        ("range?, sort?", "? range, ? sort"),
        ("git.diff?", "? git.diff"),
        ("re-pl?", "? re-pl"),
        ("a1?", "? a1"),
        ("extend?,", "? extend,"),
        ("(extend?)", "(? extend)"),
        ("extend?; range 3", "? extend; range 3"),
        # Question mark glued to the next word is separated
        ("?filt", "? filt"),
        ("?git.diff", "? git.diff"),
        ("range 5, ?extend", "range 5, ? extend"),
        ("fruits, :nolimit, ?filt", "fruits, :nolimit, ? filt"),
        # Already-prefix and standalone forms are unchanged
        ("? extend", "? extend"),
        ("?", "?"),
        ("range 5, ?", "range 5, ?"),
        # Embedded question marks are not moved
        ("foo?bar", "foo?bar"),
        ("$v?filt", "$v?filt"),
        ("name=apple?filt", "name=apple?filt"),
        ("extend??", "extend??"),
        ("123?", "123?"),
        (":json?x", ":json?x"),
        # Tokens of other syntax are not moved
        ('grep "berry?"', 'grep "berry?"'),
        ("grep 'why?'", "grep 'why?'"),
        (":raw ?", ":raw ?"),
        ("$v?", "$v?"),
        ("name=apple?", "name=apple?"),
        ("--flag?", "--flag?"),
        ("--path=/a?b", "--path=/a?b"),
        # A render spec moves its question mark to the front (UDAN-319)
        (":json?", ":?json"),
        ("fruits, :json?", "fruits, :?json"),
        ("(:json?)", "(:?json)"),
        ("range 5, :fmt?", "range 5, :?fmt"),
        # An argument keeps its question mark glued: the question is about the word
        ("extend_by_inserter ls_files?", "extend_by_inserter ls_files?"),
        ('"src", extend_by_inserter ls_files?', '"src", extend_by_inserter ls_files?'),
        ("grep berry?", "grep berry?"),
        # After a subexpression the arguments are chain items, so the question moves again
        ("(range 3) extend?", "(range 3) ? extend"),
    ],
)
def test_move_postfix_questions(query_text, expected):
    assert _move_postfix_questions(query_text) == expected


@pytest.mark.parametrize(
    "query_text, expected",
    [
        ("fruits # the demo data", "fruits "),
        ("fruits # note; not a statement", "fruits "),
        ("range 5 # numbers\nsort", "range 5 \nsort"),
        ("a; # note\nb", "a; \nb"),
        ("# only a comment", ""),
        ("#", ""),
        ("", ""),
        # A `#` inside a string literal is data, not a comment
        ('grep "#tag"', 'grep "#tag"'),
        ("grep '#ha#sh'", "grep '#ha#sh'"),
        ('grep "berry" # only berries', 'grep "berry" '),
    ],
)
def test_strip_comments(query_text, expected):
    assert _strip_comments(query_text) == expected


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
    )


def test_postfix_question_searches_tools(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`extend?` is interpreted as `? extend` and lists matching tools."""
    _, _, _, out_postfix, _ = qp_with_plugins.execute_query_split_debug("extend?")
    _, _, _, out_prefix, _ = qp_with_plugins.execute_query_split_debug("? extend")

    assert out_postfix == out_prefix
    assert "extend_by_attribute" in out_postfix
    assert "fs.extend_file_lines" in out_postfix


def test_postfix_question_in_chain(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range 5, extend?` is interpreted as `range 5, ? extend`."""
    _, _, _, out_postfix, _ = qp_with_plugins.execute_query_split_debug("range 5, extend?")
    _, _, _, out_prefix, _ = qp_with_plugins.execute_query_split_debug("range 5, ? extend")

    assert out_postfix == out_prefix
    assert "extend_by_attribute" in out_postfix


def test_postfix_question_no_bare_literal_error(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`extend?` no longer fails with the bare literal error."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("extend?")

    assert "Bare literal" not in out


def test_glued_question_searches_tools(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`?filt` is interpreted as `? filt` and lists tools containing filt."""
    _, _, _, out_glued, _ = qp_with_plugins.execute_query_split_debug("?filt")
    _, _, _, out_prefix, _ = qp_with_plugins.execute_query_split_debug("? filt")

    assert out_glued == out_prefix
    assert "filter_by_attribute" in out_glued
    assert "filter_field" in out_glued


def test_glued_question_no_bare_literal_error(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`?filt` no longer fails with the bare literal error."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("?filt")

    assert "Bare literal" not in out


def test_glued_question_in_chain(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`fruits, :nolimit, ?filt` lists tools containing filt (UDAN-243)."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("fruits, :nolimit, ?filt")

    assert "Bare literal" not in out
    assert "filter_by_attribute" in out
    assert "filter_field" in out


def test_postfix_render_question_searches_renders(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`fruits, :attr?` is interpreted as `fruits, :?attr` and lists matching renders (UDAN-319)."""
    _, _, _, out_postfix, _ = qp_with_plugins.execute_query_split_debug("fruits, :attr?")
    _, _, _, out_prefix, _ = qp_with_plugins.execute_query_split_debug("fruits, :?attr")

    assert out_postfix == out_prefix
    assert "renders.render_attr" in out_postfix


def test_standalone_question_still_lists_all(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`?` and `range 5, ?` keep listing all tools."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("range 5, ?")

    assert "domain=builtins" in out
    assert "domain=demo" in out


def test_question_after_source_hides_inserters(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range 5, ?` lists no inserters: a second data source in one chain is invalid."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("range 5, ?")

    assert "- demo.range ::" not in out
    assert "- fruits.insert_fruits ::" not in out
    assert "- raiser ::" not in out
    assert "- plugins ::" not in out
    # help is not an inserter: it replaces the chain (the engine runs only
    # it), so it fits any position - `range 5, help` is valid and lists.
    assert "- help.help ::" in out


def test_question_after_source_hides_unfit_contracts(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range 5, ?` lists only tools whose item contract fits the int items."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("range 5, ?")

    assert "- unique ::" in out
    assert "- demo.extend_multiply ::" in out
    # filter_field and sort_by_field declare "any": universal, they fit int items too
    assert "- filter_field ::" in out
    assert "- sort_by_field ::" in out
    assert "- renders.render_attr ::" not in out
    # extenders derive item_type from the item annotation: these take paths, not ints
    assert "- fs.extend_file_lines ::" not in out


def test_question_after_dict_source_lists_fitting_contracts(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`fruits, ?` keeps the field tools (they fit dicts and objects) and still hides inserters."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("fruits, ?")

    assert "- fruits.insert_fruits ::" not in out
    assert "- filter_field ::" in out
    assert "- sort_by_field ::" in out
    assert "- renders.render_attr ::" in out
    assert "- demo.extend_multiply ::" not in out
    # attributes derive item_type from the item annotation: is_even takes int, not dict
    assert "- demo.is_even ::" not in out


def test_question_after_int_source_lists_int_attributes(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range 5, ?` keeps the attributes whose derived item contract is int."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("range 5, ?")

    assert "- demo.is_even ::" in out
    assert "- demo.div_3 ::" in out


def test_question_on_fresh_chain_lists_inserters(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """A bare `?` has no chain: inserters are suggested."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("?")

    assert "- demo.range ::" in out
    assert "- filter_field ::" in out


def test_question_after_semicolon_lists_inserters(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`;` starts a fresh chain: inserters are suggested again after `range 5;`."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("range 5; ?")

    assert "- demo.range ::" in out
    assert "- fruits.insert_fruits ::" in out


@pytest.fixture
def exec_ctx():
    """Execution context for query-time logging."""
    return ExecContext(logger=DebugLogger(log_time=False))


@pytest.fixture
def query_parser():
    """The parser: question syntax only, the question's meaning lives in the sugar."""
    return QueryParser()


@pytest.mark.parametrize(
    "query_text, reason, previous_tokens",
    [
        (
            'fruits "apple',
            "No terminal matches '\"' in the current parser context, at line 1 col 8",
            "Previous tokens: Token('ATOM', 'fruits')",
        ),
        (
            "a,, b",
            "Unexpected token Token('COMMA', ',') at line 1, column 3.",
            "Previous tokens: [Token('COMMA', ',')]",
        ),
    ],
)
def test_parse_error_advice_keeps_larks_detail(query_parser, exec_ctx, query_text, reason, previous_tokens):
    """A parse failure without debug keeps lark's detail (position, expectations), no traceback."""
    with pytest.raises(ExceptionWithAdvice) as exc:
        query_parser.parse_text_to_tree(query_text, exec_ctx)

    lines = exc.value.advice.splitlines()
    assert lines[0] == f"Query parse error: {reason}"
    assert "Expected one of:" in exc.value.advice
    assert previous_tokens in exc.value.advice
    assert "Traceback" not in exc.value.advice


def test_parse_error_advice_points_at_the_excerpt(query_parser, exec_ctx):
    """The advice shows the query line with the caret under the offending position."""
    with pytest.raises(ExceptionWithAdvice) as exc:
        query_parser.parse_text_to_tree('fruits "apple', exec_ctx)

    assert exc.value.advice.splitlines()[2:4] == ['fruits "apple', "       ^"]


def test_parse_error_reraises_raw_with_debug(query_parser, exec_ctx):
    """With debug on, the parse failure propagates as the raw lark error."""
    exec_ctx.is_debug = True

    with pytest.raises(UnexpectedCharacters):
        query_parser.parse_text_to_tree('fruits "apple', exec_ctx)


@pytest.mark.parametrize("query_text", ["?fruits", "fruits?", "? fruits"])
def test_question_forms_parse_as_the_question(query_parser, exec_ctx, query_text):
    """Every question spelling parses into the same tree: the question application."""
    expected = query_parser.parse_text_to_tree("? fruits", exec_ctx)

    assert query_parser.parse_text_to_tree(query_text, exec_ctx) == expected


def test_render_question_forms_parse_as_written(query_parser, ctx_with_plugins, exec_ctx):
    """The postfix render question parses into the same tree as the glued prefix form (UDAN-319)."""
    expected = query_parser.parse_text_to_tree("fruits, :?json", exec_ctx)

    assert query_parser.parse_text_to_tree("fruits, :json?", exec_ctx) == expected


def test_mid_chain_question_stays_the_atom(query_parser, exec_ctx):
    """`range 5, extend?` parses to the question atom mid-chain; the sugar lowers it."""
    tree = query_parser.parse_text_to_tree("range 5, extend?", exec_ctx)

    chain = tree.children[0]
    assert chain.item == "CHAIN"
    assert chain.children[1] == Node.create("?", [Node.leaf("extend")])


def test_render_question_leaf_keeps_its_glued_text(query_parser, exec_ctx):
    """The prefix render-question leaf parses to one leaf carrying the pattern text."""
    tree = query_parser.parse_text_to_tree(":?fru", exec_ctx)

    assert tree.children[0].item == ":?fru"


def test_render_application_stays_an_application(query_parser, exec_ctx):
    """`:render-name` keeps its item: the parser turns no render into a question."""
    tree = query_parser.parse_text_to_tree("fruits, :raw", exec_ctx)

    chain = tree.children[0]
    assert chain.children[1].item == ":raw"


def test_argument_question_stays_glued(query_parser, exec_ctx):
    """`filter_field ?` parses with its `?` argument intact: the sugar turns it into tool docs."""
    tree = query_parser.parse_text_to_tree("filter_field ?", exec_ctx)

    application = tree.children[0]
    assert application.item == "filter_field"
    assert application.children[0].item == "?"


def test_glued_question_equals_explicit_help(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`?filt` and the explicit `help --pattern=filt` produce the same listing."""
    _, _, _, out_sugar, _ = qp_with_plugins.execute_query_split_debug("?filt")
    _, _, _, out_explicit, _ = qp_with_plugins.execute_query_split_debug("help --pattern=filt")

    assert out_sugar == out_explicit
    assert "filter_by_attribute" in out_sugar


def test_written_form_narrows_like_the_question(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range 5, help` and `range 5, ?` narrow the same way: the chain types go
    to the tool that asks for them (its `wants_item_types` declaration), however it
    was written."""
    _, _, _, out_question, _ = qp_with_plugins.execute_query_split_debug("range 5, ?")
    _, _, _, out_written, _ = qp_with_plugins.execute_query_split_debug("range 5, help")

    assert out_written == out_question
    assert "- unique ::" in out_written


RANGE_HELP_FIRST_LINE = "- demo.range (inserter) [src/udan/plugins_tools_demo/plugins_demo.py:20]"


def test_question_with_tail_shows_word_help(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range? 3` and `? range 3` show the `range` help, as if written `range?` (UDAN-351)."""
    _, _, _, out_word, _ = qp_with_plugins.execute_query_split_debug("range?")
    _, _, _, out_postfix_tail, _ = qp_with_plugins.execute_query_split_debug("range? 3")
    _, _, _, out_prefix_tail, _ = qp_with_plugins.execute_query_split_debug("? range 3")

    lines = out_word.splitlines()
    assert lines[0] == RANGE_HELP_FIRST_LINE
    assert out_postfix_tail == out_word
    assert out_prefix_tail == out_word


def test_question_with_unknown_named_filter_shows_word_help(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range? --unknown=1` shows the `range` help: the filter is not a listing filter."""
    _, _, _, out_word, _ = qp_with_plugins.execute_query_split_debug("range?")
    _, _, _, out_filter, _ = qp_with_plugins.execute_query_split_debug("range? --unknown=1")

    assert out_filter == out_word
    assert out_filter.splitlines()[0] == RANGE_HELP_FIRST_LINE


def test_question_with_keyval_tail_shows_word_listing(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`fruits, filter? name=apple` lists the `filter` tools (UDAN-351)."""
    _, _, _, out_word, _ = qp_with_plugins.execute_query_split_debug("fruits, filter?")
    _, _, _, out_tail, _ = qp_with_plugins.execute_query_split_debug("fruits, filter? name=apple")

    assert out_tail == out_word
    assert "- attributes_ops.filter_by_attribute ::" in out_word


def test_argument_question_shows_word_help(ctx_with_plugins):
    """A question glued to an argument asks about the argument, not the tool (UDAN-390)."""
    qp_with_plugins = make_qp(ctx_with_plugins)
    _, _, _, out_word, _ = qp_with_plugins.execute_query_split_debug("ls_files?")
    _, _, _, out_argument, _ = qp_with_plugins.execute_query_split_debug('"src", extend_by_inserter ls_files?')

    assert out_argument == out_word
    assert (
        out_argument.splitlines()[0]
        == "- fs.insert_ls_files (inserter) [src/udan/plugins_tools_examples/plugins_fs.py:78]"
    )


def test_separated_question_shows_tool_docs(ctx_with_plugins):
    """`spec arg ?` still asks about the tool: only the glued `?` asks about the word."""
    qp_with_plugins = make_qp(ctx_with_plugins)
    _, _, _, out_docs, _ = qp_with_plugins.execute_query_split_debug("extend_by_inserter ls_files ?")

    assert (
        out_docs.splitlines()[0]
        == "- extend_by_inserter (extender) [src/udan/plugins_tools_examples/plugins_builtins.py:224]"
    )


def test_question_with_trailing_chain_item_shows_question_listing(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`range 5, extend? , sort` shows the `extend` listing, as if written `range 5, extend?`."""
    _, _, _, out_word, _ = qp_with_plugins.execute_query_split_debug("range 5, extend?")
    _, _, _, out_tail, _ = qp_with_plugins.execute_query_split_debug("range 5, extend? , sort")

    assert out_tail == out_word
    assert "- attributes_ops.extend_by_attribute ::" in out_word


def test_question_keeps_named_filters(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """A listing filter on the question keeps working: it narrows or groups the listing."""
    _, _, _, out_grouped, _ = qp_with_plugins.execute_query_split_debug("? range --group=type")
    _, _, _, out_explicit, _ = qp_with_plugins.execute_query_split_debug("help range --group=type")

    assert out_grouped == out_explicit
    assert out_grouped.splitlines()[0] == RANGE_HELP_FIRST_LINE

    _, _, _, out_bare, _ = qp_with_plugins.execute_query_split_debug("? group=type")
    _, _, _, out_bare_explicit, _ = qp_with_plugins.execute_query_split_debug("help group=type")

    assert out_bare == out_bare_explicit
    assert "- type=attribute ::" in out_bare


def test_question_ends_statement_before_rest(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`extend?; range 3` shows the `extend` listing: the question's listing is the output."""
    _, _, _, out_word, _ = qp_with_plugins.execute_query_split_debug("extend?")
    _, _, _, out_statement, _ = qp_with_plugins.execute_query_split_debug("extend?; range 3")

    assert out_statement == out_word
    assert "- attributes_ops.extend_by_attribute ::" in out_word


def test_question_with_subquery_shows_listing(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`? (range 3)` lists tools: the subquery is query text being written, not a filter."""
    _, _, _, out, _ = qp_with_plugins.execute_query_split_debug("? (range 3)")

    assert "- demo.range ::" in out
    assert "- attributes_ops.extend_by_attribute ::" in out


def test_render_question_equals_explicit_help(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`:?raw` and the explicit render-filtered query produce the same listing."""
    _, _, _, out_sugar, _ = qp_with_plugins.execute_query_split_debug(":?raw")
    _, _, _, out_explicit, _ = qp_with_plugins.execute_query_split_debug("help --tool_type=render --pattern=raw")

    assert out_sugar == out_explicit
    assert "renders.render_raw" in out_sugar


def test_render_docs_sugar_stays_an_application(query_parser, exec_ctx):
    """`:render ?` parses as the render application with its `?` argument; the sugar lowers it."""
    tree = query_parser.parse_text_to_tree("fruits, :raw ?", exec_ctx)

    chain = tree.children[0]
    assert chain.children[1].item == ":raw"
    assert chain.children[1].children[-1].item == "?"


def test_render_application_with_arguments_stays_an_application(query_parser, exec_ctx):
    """`:render` without the `?` argument stays a render application."""
    tree = query_parser.parse_text_to_tree("fruits, :raw x", exec_ctx)

    chain = tree.children[0]
    assert chain.children[1].item == ":raw"


def test_render_docs_unknown_render_stays_an_application(query_parser, exec_ctx):
    """A `?` after an unknown render name parses as the application: the sugar leaves it
    for the resolver's render path, which reports available renders."""
    tree = query_parser.parse_text_to_tree("fruits, :nonexistent_render ?", exec_ctx)

    chain = tree.children[0]
    assert chain.children[1].item == ":nonexistent_render"


def test_render_docs_sugar_equals_explicit_help(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """`:raw ?` and the explicit render docs query produce the same output."""
    _, _, _, out_sugar, _ = qp_with_plugins.execute_query_split_debug("fruits, :raw ?")
    _, _, _, out_explicit, _ = qp_with_plugins.execute_query_split_debug("fruits, render_help --render_name=raw")

    assert out_sugar == out_explicit
    assert "raw" in out_sugar


def test_comment_is_stripped_from_query(query_parser, exec_ctx):
    """`fruits # the demo data` parses as `fruits`."""
    assert query_parser.parse_text_to_tree("fruits # the demo data", exec_ctx) == query_parser.parse_text_to_tree(
        "fruits", exec_ctx
    )


def test_comment_hides_rest_of_statement(query_parser, exec_ctx):
    """Everything after `#` is skipped, including query syntax like `,` and `;`."""
    assert query_parser.parse_text_to_tree(
        "fruits # , grep berry; range 3", exec_ctx
    ) == query_parser.parse_text_to_tree("fruits", exec_ctx)


def test_multi_line_comment_keeps_next_line(query_parser, exec_ctx):
    """A comment ends at the line end: the next line still parses."""
    tree = query_parser.parse_text_to_tree("fruits,  # the demo data\n:raw", exec_ctx)

    chain = tree.children[0]
    assert chain.item == "CHAIN"
    assert chain.children[1].item == ":raw"


def test_hash_in_string_literal_is_data(query_parser, exec_ctx):
    """A `#` inside a string literal stays part of the argument."""
    tree = query_parser.parse_text_to_tree('grep "#tag"', exec_ctx)

    application = tree.children[0]
    assert application.item == "grep"
    assert application.children[0].item == f"{NODE_STRING_PREFIX}#tag"


def test_only_comment_query_falls_back_to_default_operator(query_parser, exec_ctx):
    """A query that is only a comment parses as the default `?` operator."""
    assert query_parser.parse_text_to_tree("# nothing but a note", exec_ctx) == query_parser.parse_text_to_tree(
        "?", exec_ctx
    )


def test_query_marker_prefix_with_comment(query_parser, exec_ctx):
    """The `# q:` dump marker is still removed before comment stripping."""
    assert query_parser.parse_text_to_tree("# q: fruits # the demo data", exec_ctx) == query_parser.parse_text_to_tree(
        "fruits", exec_ctx
    )


def test_comment_query_execution_matches_clean_query(ctx_with_plugins):
    qp_with_plugins = make_qp(ctx_with_plugins)
    """An annotated query runs like the clean one (UDAN-314)."""
    _, _, _, out_annotated, _ = qp_with_plugins.execute_query_split_debug("fruits, grep berry # the demo data")
    _, _, _, out_clean, _ = qp_with_plugins.execute_query_split_debug("fruits, grep berry")

    assert out_annotated == out_clean
