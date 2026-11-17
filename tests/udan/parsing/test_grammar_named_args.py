"""Test grammar support for named args in subexpressions."""

from udan.core.api_constants import NODE_ROOT_ITEM
from udan.parsing.impl_utils_parsing import parse_tree


def test_subexpr_with_named_arg():
    """Subexpression with named_arg parses correctly."""
    tree = parse_tree("(file_assignments --prefix=EXCLUSIONS)", unwrap_single_roots=False)
    actual = str(tree)
    print(f"\nActual:\n{actual}\n")
    # Structure: ROOT -> ROOT -> application(file_assignments, --prefix=EXCLUSIONS)
    assert tree.children[0].item == NODE_ROOT_ITEM
    app = tree.children[0].children[0]
    assert app.item == "file_assignments"
    assert app.children[0].item == "--prefix=EXCLUSIONS"


def test_nested_subexpr_with_named_arg():
    """Nested subexpression: a (b (c --d=e))"""
    tree = parse_tree("a (b (c --d=e))", unwrap_single_roots=False)
    actual = str(tree)
    print(f"\nActual:\n{actual}\n")
    # Structure: ROOT -> application(a, ROOT -> application(b, ROOT -> application(c, --d=e)))
    app_a = tree.children[0]
    assert app_a.item == "a"
    subexpr_b = app_a.children[0]
    assert subexpr_b.item == NODE_ROOT_ITEM
    app_b = subexpr_b.children[0]
    assert app_b.item == "b"
    subexpr_c = app_b.children[0]
    assert subexpr_c.item == NODE_ROOT_ITEM
    app_c = subexpr_c.children[0]
    assert app_c.item == "c"
    assert app_c.children[0].item == "--d=e"


def test_subexpr_with_two_named_args():
    """Subexpression with multiple named_args."""
    tree = parse_tree("(some_func --arg1=val1 --arg2=val2)", unwrap_single_roots=False)
    actual = str(tree)
    print(f"\nActual:\n{actual}\n")
    app = tree.children[0].children[0]
    assert app.item == "some_func"
    assert len(app.children) == 2
    assert app.children[0].item == "--arg1=val1"
    assert app.children[1].item == "--arg2=val2"


def test_subexpr_with_atom_and_named_arg():
    """Subexpression with mixed atom and named_arg."""
    tree = parse_tree("(some_func foo --arg=val)", unwrap_single_roots=False)
    actual = str(tree)
    print(f"\nActual:\n{actual}\n")
    app = tree.children[0].children[0]
    assert app.item == "some_func"
    assert len(app.children) == 2
    assert app.children[0].item == "foo"
    assert app.children[1].item == "--arg=val"
