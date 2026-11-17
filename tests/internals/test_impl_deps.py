"""Tests for resolve_fn_args (function argument resolution, now in operators engine)."""

from functools import partial

from udan.core.utils_binding import resolve_fn_args


def test_kwargs_function_passes_through_user_args():
    """Test that **kwargs functions pass through all user arguments."""

    def func_with_kwargs(**kwargs):
        return kwargs

    user_args = {"query": "Date", "limit": 10}
    result = resolve_fn_args(func_with_kwargs, user_args)

    assert result == {"query": "Date", "limit": 10}


def test_kwargs_function_with_empty_user_args():
    """Test that **kwargs functions handle empty user_args correctly."""

    def func_with_kwargs(**kwargs):
        return kwargs

    user_args = {}
    result = resolve_fn_args(func_with_kwargs, user_args)

    assert result == {}


def test_partial_kwargs_function_passes_through_user_args():
    """Test that partial(**kwargs) functions pass through remaining user arguments."""

    def func_with_kwargs(**kwargs):
        return kwargs

    partial_fn = partial(func_with_kwargs, tool_name="search_notes", server_url="http://localhost:2899/search")
    user_args = {"query": "Date"}
    result = resolve_fn_args(partial_fn, user_args)

    # Should include query but not the pre-filled partial args (those are
    # handled by partial itself)
    assert result == {"query": "Date"}


def test_partial_kwargs_function_with_multiple_user_args():
    """Test partial with **kwargs and multiple user arguments."""

    def func_with_kwargs(**kwargs):
        return kwargs

    partial_fn = partial(func_with_kwargs, tool_name="test", server_url="http://localhost")
    user_args = {"query": "test", "limit": 5, "offset": 10}
    result = resolve_fn_args(partial_fn, user_args)

    assert result == {"query": "test", "limit": 5, "offset": 10}


def test_function_with_regular_params_and_kwargs():
    """Test function with both regular parameters and **kwargs."""

    def func_with_both(required, optional=None, **kwargs):
        return {"required": required, "optional": optional, "kwargs": kwargs}

    user_args = {"required": "value1", "optional": "value2", "extra1": "value3", "extra2": "value4"}
    result = resolve_fn_args(func_with_both, user_args)

    assert result == {
        "required": "value1",
        "optional": "value2",
        "extra1": "value3",
        "extra2": "value4",
    }


def test_kwargs_respects_dep_param_names():
    """Test that dependency parameter names are excluded from kwargs."""

    def func_with_kwargs(**kwargs):
        return kwargs

    user_args = {"attr1": "value1", "attr2": "value2", "other": "value3"}
    dep_param_names = {"attr1", "attr2"}
    result = resolve_fn_args(func_with_kwargs, user_args, dep_param_names=dep_param_names)

    # attr1 and attr2 should be excluded (they're dependency params)
    # but 'other' should be passed through
    assert result == {"other": "value3"}


def test_kwargs_handles_default_values():
    """Test that **kwargs doesn't interfere with default values."""

    def func_with_defaults(required, optional="default_value", **kwargs):
        return {"required": required, "optional": optional, "kwargs": kwargs}

    user_args = {"required": "value1"}
    result = resolve_fn_args(func_with_defaults, user_args)

    assert result == {"required": "value1", "optional": "default_value"}


def test_kwargs_user_value_overrides_default():
    """Test that user-provided values override defaults even with **kwargs."""

    def func_with_defaults(required, optional="default_value", **kwargs):
        return {"required": required, "optional": optional, "kwargs": kwargs}

    user_args = {"required": "value1", "optional": "user_value"}
    result = resolve_fn_args(func_with_defaults, user_args)

    assert result == {"required": "value1", "optional": "user_value"}
