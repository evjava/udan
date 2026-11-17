from udan.core.api_constants import NODE_STRING_PREFIX
from udan.core.api_forests import Item, Node
from udan.parsing.impl_utils_parsing import parse_tree

N = Node.create


PseudoNode = Item | dict[Item, list["PseudoNode"]]


def pseudonode_to_node(pseudo: PseudoNode) -> Node:
    """Convert a PseudoNode (Item or dict) to a Node."""
    if isinstance(pseudo, dict):
        if len(pseudo) != 1:
            raise ValueError(f"PseudoNode dict must have exactly one key, got {len(pseudo)}")
        item, children = next(iter(pseudo.items()))
        # Handle case where children is not a list (e.g., string)
        if not isinstance(children, list):
            children = [children]
        return N(item, [pseudonode_to_node(child) for child in children])
    else:
        return N(pseudo)


def test_pseudo_node_simple():
    conv = pseudonode_to_node
    assert conv("ROOT") == N("ROOT")
    assert conv({"ROOT": ["a", "b"]}) == N("ROOT", [N("a"), N("b")])


def check_pseudo(node_expected, pseudo_node):
    node_actual = pseudonode_to_node(pseudo_node)
    assert node_expected == node_actual


def test_parse_tree_simple():
    pt = parse_tree
    e = pseudonode_to_node

    assert pt("a") == e({"ROOT": ["a"]})
    # Comma-separated items are now grouped in a CHAIN node
    assert pt("a, b") == e({"ROOT": [{"CHAIN": ["a", "b"]}]})
    assert pt("fun x") == e({"ROOT": [{"fun": ["x"]}]})
    assert pt("f x y") == e({"ROOT": [{"f": ["x", "y"]}]})
    # Comma separates chains: f x y is one chain, g z is another
    assert pt("f x y, g z") == e({"ROOT": [{"CHAIN": [{"f": ["x", "y"]}, {"g": ["z"]}]}]})
    assert pt("f (g x) y") == e({"ROOT": [{"f": [{"g": ["x"]}, "y"]}]})
    # String literals are now marked with NODE_STRING_PREFIX
    assert pt('f (g x) "a b"') == e({"ROOT": [{"f": [{"g": "x"}, f"{NODE_STRING_PREFIX}a b"]}]})
    # Comma-separated chain: debug, ls ~/1, fi sync != git
    assert pt("debug, ls ~/1, fi sync != git") == e(
        {"ROOT": [{"CHAIN": ["debug", {"ls": ["~/1"]}, {"fi": ["sync", "!=", "git"]}]}]}
    )


def test_empty_string_as_arg():
    """Test that empty string '' is parsed as an empty string item.

    This is important for cases like 'grep '' where we want to search
    for empty strings, not ignore the argument.
    """
    pt = parse_tree
    e = pseudonode_to_node
    # String literals are now marked with NODE_STRING_PREFIX
    assert pt("grep ''") == e({"ROOT": [{"grep": [f"{NODE_STRING_PREFIX}"]}]})
    assert pt("grep '  '") == e({"ROOT": [{"grep": [f"{NODE_STRING_PREFIX}{'  '}"]}]})


def test_assign():
    pt = parse_tree
    e = pseudonode_to_node
    # Assignment syntax: :=a b (assign result of b to variable a)
    assert pt("a := b") == e({"ROOT": [{":=a": ["b"]}]})
    # Assignment with parenthesized expression: :=a (b c)
    # The parens create a subexpr which wraps in ROOT, then unwrapped
    assert pt("a := (b c)") == e({"ROOT": [{":=a": {"b": ["c"]}}]})

    # Semicolon-separated statements: b := (...); b
    # This tests the full TODO query pattern with assignment and variable
    # reference
    assert pt('b := ("file.txt", extend_file_lines, sgrep depth=1); b') == e(
        {
            "ROOT": [
                {":=b": [{"CHAIN": [f"{NODE_STRING_PREFIX}file.txt", "extend_file_lines", {"sgrep": ["depth=1"]}]}]},
                "b",
            ]
        }
    )

    # Multiple semicolon-separated statements
    assert pt("a := x; b := y; c") == e({"ROOT": [{":=a": ["x"]}, {":=b": ["y"]}, "c"]})


def test_string_arg_with_parens():
    """Test that string arguments can contain parentheses."""
    pt = parse_tree
    e = pseudonode_to_node
    # String with parens should not be treated as grouping
    # String literals are now marked with NODE_STRING_PREFIX
    assert pt('grep "(test)"') == e({"ROOT": [{"grep": [f"{NODE_STRING_PREFIX}(test)"]}]})
    assert pt('grep "(test) (nested)"') == e({"ROOT": [{"grep": [f"{NODE_STRING_PREFIX}(test) (nested)"]}]})


def test_string_literals_single_quotes():
    """Test that single-quoted strings are marked with NODE_STRING_PREFIX."""
    pt = parse_tree
    e = pseudonode_to_node

    # Single-quoted strings should be marked with NODE_STRING_PREFIX
    assert pt("'a'") == e({"ROOT": [f"{NODE_STRING_PREFIX}a"]})
    assert pt("'hello world'") == e({"ROOT": [f"{NODE_STRING_PREFIX}hello world"]})
    assert pt("'test with spaces'") == e({"ROOT": [f"{NODE_STRING_PREFIX}test with spaces"]})

    # Empty string
    assert pt("''") == e({"ROOT": [f"{NODE_STRING_PREFIX}"]})


def test_string_literals_double_quotes():
    """Test that double-quoted strings are marked with NODE_STRING_PREFIX."""
    pt = parse_tree
    e = pseudonode_to_node

    # Double-quoted strings should also be marked with NODE_STRING_PREFIX
    assert pt('"a"') == e({"ROOT": [f"{NODE_STRING_PREFIX}a"]})
    assert pt('"hello world"') == e({"ROOT": [f"{NODE_STRING_PREFIX}hello world"]})
    assert pt('"test with spaces"') == e({"ROOT": [f"{NODE_STRING_PREFIX}test with spaces"]})

    # Empty string
    assert pt('""') == e({"ROOT": [f"{NODE_STRING_PREFIX}"]})


def test_string_literals_with_tools():
    """Test that string literals work with tools."""
    pt = parse_tree
    e = pseudonode_to_node

    # String literal followed by tool (chain)
    assert pt("'a', :list") == e({"ROOT": [{"CHAIN": [f"{NODE_STRING_PREFIX}a", ":list"]}]})
    assert pt('"hello", :list') == e({"ROOT": [{"CHAIN": [f"{NODE_STRING_PREFIX}hello", ":list"]}]})

    # Multiple strings with tool (chain)
    assert pt("'a', 'b', 'c', :list") == e(
        {"ROOT": [{"CHAIN": [f"{NODE_STRING_PREFIX}a", f"{NODE_STRING_PREFIX}b", f"{NODE_STRING_PREFIX}c", ":list"]}]}
    )

    # String as argument to function
    assert pt("grep 'pattern'") == e({"ROOT": [{"grep": [f"{NODE_STRING_PREFIX}pattern"]}]})
    assert pt('f "arg1" "arg2"') == e({"ROOT": [{"f": [f"{NODE_STRING_PREFIX}arg1", f"{NODE_STRING_PREFIX}arg2"]}]})


def test_string_literals_with_escape_sequences():
    """Test that string literals handle escape sequences."""
    pt = parse_tree
    e = pseudonode_to_node

    # Escape sequences in strings are interpreted by the parser
    # \n becomes a newline, \t becomes a tab, etc.
    # Use double backslash in f-string to get literal backslash-n
    assert pt(r"'\n'") == e({"ROOT": [rf"{NODE_STRING_PREFIX}\n"]})
    assert pt(r"'\t'") == e({"ROOT": [rf"{NODE_STRING_PREFIX}\t"]})
    assert pt(r"'\\'") == e({"ROOT": [rf"{NODE_STRING_PREFIX}\\"]})

    # Note: The parser interprets escape sequences in string literals
    # So '\n' becomes an actual newline character, not the string '\n'


def test_string_literals_vs_identifiers():
    """Test that string literals are distinguished from identifiers."""
    pt = parse_tree
    e = pseudonode_to_node

    # String literal should be marked
    assert pt("'a'") == e({"ROOT": [f"{NODE_STRING_PREFIX}a"]})

    # Identifier should NOT be marked (raw value)
    assert pt("a") == e({"ROOT": ["a"]})

    # They should produce different trees
    assert pt("'a'") != pt("a")


def test_string_literals_with_special_chars():
    """Test that string literals can contain special characters."""
    pt = parse_tree
    e = pseudonode_to_node

    # Special characters that would be interpreted differently as identifiers
    assert pt("'test:with:colons'") == e({"ROOT": [f"{NODE_STRING_PREFIX}test:with:colons"]})
    assert pt("'test-with-dashes'") == e({"ROOT": [f"{NODE_STRING_PREFIX}test-with-dashes"]})
    assert pt("'test/with/slashes'") == e({"ROOT": [f"{NODE_STRING_PREFIX}test/with/slashes"]})
    assert pt("'test@with@at'") == e({"ROOT": [f"{NODE_STRING_PREFIX}test@with@at"]})


def test_parentheses_with_comma_chained_operators():
    """Test that parentheses can contain comma-chained operators."""
    pt = parse_tree
    e = pseudonode_to_node

    # Simple case: (a, b) -> comma-separated items form a CHAIN (after unwrapping)
    assert pt("(a, b)") == e({"ROOT": [{"CHAIN": ["a", "b"]}]})
    assert pt("(a, b, c)") == e({"ROOT": [{"CHAIN": ["a", "b", "c"]}]})

    # With function calls: (f x, g y) -> chain inside parens
    assert pt("(f x, g y)") == e({"ROOT": [{"CHAIN": [{"f": ["x"]}, {"g": ["y"]}]}]})

    # With string literals: (f x, "arg", g y) -> chain inside parens
    assert pt('(f x, "arg", g y)') == e({"ROOT": [{"CHAIN": [{"f": ["x"]}, f"{NODE_STRING_PREFIX}arg", {"g": ["y"]}]}]})

    # With render specs: (f x, :list) -> chain inside parens
    assert pt("(f x, :list)") == e({"ROOT": [{"CHAIN": [{"f": ["x"]}, ":list"]}]})

    # Nested: (f (g x), y) -> chain with application and leaf
    assert pt("(f (g x), y)") == e({"ROOT": [{"CHAIN": [{"f": [{"g": ["x"]}]}, "y"]}]})

    # Assignment with parenthesized chain: a := (f x, g y) -> chain in assignment RHS
    assert pt("a := (f x, g y)") == e({"ROOT": [{":=a": [{"CHAIN": [{"f": ["x"]}, {"g": ["y"]}]}]}]})

    # The original issue from TODO: a := (ls_files tests test_*.py, file_name, :attr file_name)
    # Note: :attr file_name is parsed as an application, so it becomes {:attr,
    # [file_name]}
    assert pt("a := (ls_files tests test_*.py, file_name, :attr file_name)") == e(
        {"ROOT": [{":=a": [{"CHAIN": [{"ls_files": ["tests", "test_*.py"]}, "file_name", {":attr": ["file_name"]}]}]}]}
    )

    # KEYVAL arguments in parentheses: (sgrep depth=1)
    # This was the main issue - KEYVAL was matching "depth=1)" including the
    # closing paren
    assert pt("(sgrep depth=1)") == e({"ROOT": [{"sgrep": ["depth=1"]}]})

    # Multiple KEYVAL args: (sgrep depth=1 pattern=test*)
    assert pt("(sgrep depth=1 pattern=test*)") == e({"ROOT": [{"sgrep": ["depth=1", "pattern=test*"]}]})

    # Mixed args in parentheses: (f x, sgrep depth=1, g y) -> chain
    assert pt("(f x, sgrep depth=1, g y)") == e(
        {"ROOT": [{"CHAIN": [{"f": ["x"]}, {"sgrep": ["depth=1"]}, {"g": ["y"]}]}]}
    )

    # Assignment with KEYVAL in parentheses: b := ("file.txt",
    # extend_file_lines, sgrep depth=1) -> chain in assignment RHS
    assert pt('b := ("file.txt", extend_file_lines, sgrep depth=1)') == e(
        {"ROOT": [{":=b": [{"CHAIN": [f"{NODE_STRING_PREFIX}file.txt", "extend_file_lines", {"sgrep": ["depth=1"]}]}]}]}
    )


def test_parameterized_attribute_syntax():
    """Test that parameterized attribute syntax (attr_name arg) is parsed correctly.

    This tests the (attr_name arg) syntax for attributes that take parameters
    beyond just 'item', like has_tag(item, tag).

    Note: The grammar doesn't have a special rule for parameterized attributes.
    Instead, (attr_name arg) is parsed as a regular application (function call).
    The interpretation layer handles the distinction between operators and attributes.
    """
    pt = parse_tree
    e = pseudonode_to_node

    # Simple parameterized attribute: (has_tag python)
    # Parsed as a regular application: has_tag(python)
    assert pt("(has_tag python)") == e({"ROOT": [{"has_tag": ["python"]}]})

    # Parameterized attribute with filter_by_attribute: filter_by_attribute
    # (has_tag python) == True
    assert pt("filter_by_attribute (has_tag python) == True") == e(
        {"ROOT": [{"filter_by_attribute": [{"has_tag": ["python"]}, "==", "True"]}]}
    )

    # Multiple parameterized attributes in comma-separated list (chain)
    assert pt("(attr_a arg_a), (attr_b arg_b)") == e(
        {"ROOT": [{"CHAIN": [{"attr_a": ["arg_a"]}, {"attr_b": ["arg_b"]}]}]}
    )

    # Parameterized attribute in expression: filter_by_attribute (has_tag
    # python) == True, :list
    assert pt("filter_by_attribute (has_tag python) == True, :list") == e(
        {"ROOT": [{"CHAIN": [{"filter_by_attribute": [{"has_tag": ["python"]}, "==", "True"]}, ":list"]}]}
    )

    # Nested: (f (has_tag python))
    assert pt("(f (has_tag python))") == e({"ROOT": [{"f": [{"has_tag": ["python"]}]}]})

    # Parameterized attribute with string argument: (has_tag "python tag")
    assert pt('(has_tag "python tag")') == e({"ROOT": [{"has_tag": [f"{NODE_STRING_PREFIX}python tag"]}]})

    # Complex: notes, filter_by_attribute (has_tag python) == True (chain)
    assert pt("notes, filter_by_attribute (has_tag python) == True") == e(
        {
            "ROOT": [
                {
                    "CHAIN": [
                        "notes",
                        {"filter_by_attribute": [{"has_tag": ["python"]}, "==", "True"]},
                    ]
                }
            ]
        }
    )


def test_named_arg_with_dotted_value():
    """A dotted named-arg value stays one argument of its application.

    The comma is what ends an argument - the chain separator - so the dotted
    form is the one a hierarchical path uses (--position=1.2).
    """
    pt = parse_tree
    e = pseudonode_to_node

    assert pt("f x --position=1.2") == e({"ROOT": [{"f": ["x", "--position=1.2"]}]})
    assert pt("f x --position=1.2, g y") == e({"ROOT": [{"CHAIN": [{"f": ["x", "--position=1.2"]}, {"g": ["y"]}]}]})
