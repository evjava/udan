"""Tests for utils_binding module."""

import pytest

from udan.core.utils_binding import (
    convert_boolean_string,
    convert_string_value,
    convert_value,
)
from udan.parsing.api_query_parser import parse_named_argument


def test_parse_named_argument():
    """Test parse_named_argument function with various inputs."""
    pna = parse_named_argument

    # Basic key-value parsing
    assert pna("--key=value") == ("key", "value")
    assert pna("--my-arg-name=value") == ("my_arg_name", "value")

    # Bug fix: hyphens in values should be preserved
    assert pna("--directory=../udan-feature-render-fixes") == ("directory", "../udan-feature-render-fixes")
    assert pna("--output-file=my-file-name.txt") == ("output_file", "my-file-name.txt")
    assert pna("--my-arg=my-value") == ("my_arg", "my-value")
    assert pna("--my-arg=value-with-hyphens=and=equals") == ("my_arg", "value-with-hyphens=and=equals")

    # Boolean flags (true by default)
    assert pna("--verbose") == ("verbose", "true")
    assert pna("--my-flag") == ("my_flag", "true")
    assert pna("--my_flag") == ("my_flag", "true")
    assert pna("--myFlag=true") == ("myFlag", "true")
    assert pna("--my-flag=true") == ("my_flag", "true")

    # Boolean flags (false with --no- prefix)
    assert pna("--no-verbose") == ("verbose", "false")
    assert pna("--no-dry-run") == ("dry_run", "false")
    assert pna("--noverbose") == ("verbose", "false")
    # Without known_keys the "no" prefix is always stripped (legacy behavior);
    # pass known_keys to keep such names literal (see parse_named_argument)
    assert pna("--no_my_flag") == ("_my_flag", "false")

    # Quote handling
    assert pna("--path='some value'") == ("path", "some value")
    assert pna('--path="some value"') == ("path", "some value")
    assert pna('--directory="../my-feature-dir"') == ("directory", "../my-feature-dir")
    assert pna("--arg='value") == ("arg", "'value")
    assert pna('--arg="value') == ("arg", '"value')

    # Edge cases
    assert pna("--no") is None
    assert pna("--no-") is None
    assert pna("--key=") == ("key", "")
    assert pna("--eq=a==b") == ("eq", "a==b")
    assert pna("--my--arg=value") == ("my__arg", "value")
    assert pna("--key=---") == ("key", "---")
    assert pna("--file=/path/to/file-123.txt") == ("file", "/path/to/file-123.txt")
    assert pna("--file=my_file_name.txt") == ("file", "my_file_name.txt")
    assert pna("--arg='line1\\nline2'") == ("arg", "line1\\nline2")


def test_parse_named_argument_with_known_keys():
    """Test that a leading "no" is stripped only when it produces a known parameter name."""
    pna = parse_named_argument
    known_keys = {"verbose", "has_header", "normalize", "depth"}

    # Names starting with "no" that match a parameter are kept literal
    assert pna("--normalize", known_keys) == ("normalize", "true")
    assert pna("--normalize=false", known_keys) == ("normalize", "false")

    # Negation works when the stripped name is a known parameter
    assert pna("--noverbose", known_keys) == ("verbose", "false")
    assert pna("--no-verbose", known_keys) == ("verbose", "false")
    assert pna("--nohas_header", known_keys) == ("has_header", "false")
    assert pna("--no-depth", known_keys) == ("depth", "false")

    # Names matching no parameter are kept as typed instead of being stripped
    other_keys = {"verbose", "normalize"}
    assert pna("--nodepth", other_keys) == ("nodepth", "true")
    assert pna("--nomatch", other_keys) == ("nomatch", "true")

    # Plain flags are unaffected
    assert pna("--verbose", known_keys) == ("verbose", "true")
    assert pna("--no", known_keys) is None
    assert pna("--no-", known_keys) is None


def test_parse_named_argument_known_keys_shadow_negation():
    """Test that the literal parameter name wins over the negation form."""
    pna = parse_named_argument

    # Signature (a, noa): --a and --noa both name real parameters, so neither is a negation
    known_keys = {"a", "noa"}
    assert pna("--a", known_keys) == ("a", "true")
    assert pna("--noa", known_keys) == ("noa", "true")

    # Explicit values are the way to set them to false
    assert pna("--a=False", known_keys) == ("a", "False")
    assert pna("--noa=0", known_keys) == ("noa", "0")

    # When only the negation target exists, the stripped name wins
    assert pna("--noa", {"a"}) == ("a", "false")


def test_convert_boolean_string():
    """Test convert_boolean_string function."""
    cbs = convert_boolean_string

    # True variations
    assert cbs("true") is True
    assert cbs("True") is True
    assert cbs("TRUE") is True

    # False variations
    assert cbs("false") is False
    assert cbs("False") is False
    assert cbs("FALSE") is False

    # Non-boolean values
    assert cbs("maybe") is None
    assert cbs("random") is None


def test_convert_string_value():
    """Test convert_string_value function."""
    csv = convert_string_value

    # Boolean conversions
    assert csv("true", "boolean") is True
    assert csv("false", "boolean") is False
    assert csv("1", "boolean") is True
    assert csv("0", "boolean") is False
    assert csv("yes", "boolean") is True
    assert csv("no", "boolean") is False
    assert csv("on", "boolean") is True
    assert csv("off", "boolean") is False

    # Invalid boolean conversion
    with pytest.raises(ValueError):
        csv("maybe", "boolean")

    with pytest.raises(ValueError):
        csv("", "boolean")

    # Integer conversions
    assert csv("42", "integer") == 42
    assert csv("0", "integer") == 0
    assert csv("99999", "integer") == 99999
    # Negative integers (limit -1 for unlimited)
    assert csv("-1", "integer") == -1
    assert csv("-42", "integer") == -42

    # Float conversions
    assert csv("3.14", "number") == 3.14
    assert csv("0.0", "number") == 0.0
    assert csv("-2.5", "number") == -2.5
    assert csv("1e10", "number") == 1e10
    assert csv("1.5e-3", "number") == 1.5e-3

    # String default
    assert csv("hello", "string") == "hello"
    assert csv("", "string") == ""
    assert csv("123", "string") == "123"
    assert csv("hello", None) == "hello"

    # Invalid conversions
    with pytest.raises(ValueError):
        csv("not-a-number", "integer")

    with pytest.raises(ValueError):
        csv("not-a-number", "number")


def test_convert_value():
    """Test convert_value function."""
    cv = convert_value

    # Non-string values are preserved
    assert cv({}, "key", 42) == 42
    assert cv({}, "key", True) is True
    assert cv({}, "key", None) is None

    # Integer conversion from schema
    props_int = {"age": {"type": "integer"}}
    assert cv(props_int, "age", "25") == 25
    assert cv(props_int, "age", "0") == 0
    assert cv(props_int, "age", "999999") == 999999
    # Negative integers (limit -1 for unlimited)
    assert cv(props_int, "age", "-1") == -1
    assert cv(props_int, "age", "-42") == -42

    # Invalid integer conversion
    with pytest.raises(ValueError):
        cv(props_int, "age", "not-a-number")

    # Boolean conversion from schema
    props_bool = {"enabled": {"type": "boolean"}}
    assert cv(props_bool, "enabled", "true") is True
    assert cv(props_bool, "enabled", "false") is False
    assert cv(props_bool, "enabled", "True") is True
    assert cv(props_bool, "enabled", "FALSE") is False

    # Invalid boolean conversion
    with pytest.raises(ValueError):
        cv(props_bool, "enabled", "maybe")

    # Any type with boolean strings
    props_any = {"flag": {"type": "any"}}
    assert cv(props_any, "flag", "true") is True
    assert cv(props_any, "flag", "false") is False
    assert cv(props_any, "flag", "hello") == "hello"
    assert cv(props_any, "flag", "123") == "123"

    # anyOf schema
    props_anyof = {"flag": {"anyOf": [{"type": "boolean"}, {"type": "null"}]}}
    assert cv(props_anyof, "flag", "true") is True
    assert cv(props_anyof, "flag", "false") is False

    props_anyof_mixed = {"value": {"anyOf": [{"type": "boolean"}, {"type": "integer"}]}}
    assert cv(props_anyof_mixed, "value", "true") is True
    assert cv(props_anyof_mixed, "value", "42") == 42
    # No anyOf member takes it and the value cannot be a string either:
    # forbidden, not silently passed through (a stray string here is what made
    # e.g. `double 2` do string repetition instead of numeric doubling)
    with pytest.raises(ValueError):
        cv(props_anyof_mixed, "value", "maybe")

    # Missing schema defaults to string
    assert cv({}, "key", "value") == "value"
    assert cv({"other": {"type": "integer"}}, "missing", "value") == "value"

    # Unknown type defaults to string
    assert cv({"value": {"type": "unknown"}}, "value", "hello") == "hello"
    assert cv({"value": {"type": "string"}}, "value", "John") == "John"


def test_convert_value_preserves_types():
    """Test that convert_value preserves non-string types."""
    cv = convert_value

    props_str = {"value": {"type": "string"}}
    assert cv(props_str, "value", None) is None
    assert cv({"value": {"type": "integer"}}, "value", 42) == 42
    assert cv({"value": {"type": "boolean"}}, "value", True) is True
    assert cv({"value": {"type": "boolean"}}, "value", False) is False
    assert cv({"value": {"type": "number"}}, "value", 3.14) == 3.14
