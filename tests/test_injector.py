"""Tests for udan.core_tools_loading's generic injector.

Framework-free by construction, the test_decompof_injector.py register: the
dependencies are plain classes, the sources are plain objects, and nothing here
imports a udan component beyond udan.core_tools_loading. The properties under test are the
injector's contract - what counts as injected, what answers it, and what the
wrapper does with the rest.
"""

from typing import Any

import pytest

from udan.core_tools_loading.api_function_injector import MISSING
from udan.core_tools_loading.impl_function_injector import FunctionInjector


class Service:
    pass


class Other:
    pass


class Declared:
    """A key nothing answers: declared so its parameters classify as injected."""


class ServiceDescriptor:
    """A type nobody declared: the injector leaves its parameter to the caller."""


class MappingSource:
    """The simplest source: a dict of instances."""

    def __init__(self, instances: dict[type, Any]) -> None:
        self._instances = instances

    def keys(self) -> set[type]:
        return set(self._instances)

    def get(self, dep_type: type) -> Any:
        return self._instances.get(dep_type, MISSING)


class RefusingSource:
    """Declares keys it never answers: the value comes from elsewhere or not at all."""

    def __init__(self, keys: set[type]) -> None:
        self._keys = keys

    def keys(self) -> set[type]:
        return set(self._keys)

    def get(self, dep_type: type) -> Any:
        return MISSING


def wants_service(service: Service) -> Service:
    return service


def wants_optional(service: Service | None = None) -> Service | None:
    return service


def wants_two_real_types(service: Service | Other) -> Service | Other:
    return service


def wants_union_with_other(service: Other | dict) -> Other | dict:
    return service


def wants_declared(instance: Declared) -> Declared:
    return instance


def wants_descriptor(instance: ServiceDescriptor) -> ServiceDescriptor:
    return instance


def wants_both(service: Service, declared: Declared) -> tuple[Service, Declared]:
    return (service, declared)


def wants_ctx(ctx: str | None = None, service: Service | None = None) -> Any:
    return ctx


def takes_service_and_ctx(service: Service, ctx: str | None = None) -> Any:
    return ctx


def takes_plain(item: str) -> str:
    return item


def make_injector(**kwargs: Any) -> FunctionInjector:
    return FunctionInjector(dependencies={Service: Service()}, **kwargs)


def test_a_global_dependency_is_injected():
    injector = make_injector()

    assert injector.wrap_function(wants_service)() is injector.dependencies[Service]


def test_a_source_answer_is_injected():
    answered = Service()
    injector = make_injector(sources=[MappingSource({Other: answered})])

    assert injector.wrap_function(wants_union_with_other)(service=None) is answered


def test_a_declared_key_without_an_answer_keeps_the_default():
    injector = make_injector(sources=[RefusingSource({Declared})])

    def wants_declared_optional(instance: Declared | None = None) -> Declared | None:
        return instance

    assert injector.wrap_function(wants_declared_optional)() is None


def test_a_declared_key_without_an_answer_and_without_a_default_raises():
    injector = make_injector(sources=[RefusingSource({Declared})])

    with pytest.raises(RuntimeError, match="Could not inject dependency"):
        injector.wrap_function(wants_declared)()


def test_a_parameter_no_key_covers_is_left_to_the_caller():
    injector = make_injector()
    mine = ServiceDescriptor()

    assert injector.wrap_function(wants_descriptor)(instance=mine) is mine


def test_the_globals_win_over_a_source():
    mine = Service()

    def wants_service(service: Service) -> Service:
        return service

    injector = FunctionInjector(
        dependencies={Service: mine},
        sources=[MappingSource({Service: Service()})],
    )

    assert injector.wrap_function(wants_service)() is mine


def test_a_source_does_not_win_over_the_query_override():
    override = Service()
    injector = make_injector(sources=[MappingSource({Other: Other()})])
    injector.set_dependency(Other, override)

    def wants_other(other: Other) -> Other:
        return other

    assert injector.wrap_function(wants_other)() is override


def test_the_first_source_that_answers_wins():
    first, second = Other(), Other()
    injector = make_injector(sources=[MappingSource({Other: first}), MappingSource({Other: second})])

    def wants_other(other: Other) -> Other:
        return other

    assert injector.wrap_function(wants_other)() is first


class FailingSource:
    """Declares a key and fails answering it: the error is the caller's to see."""

    def keys(self) -> set[type]:
        return {Other}

    def get(self, dep_type: type) -> Any:
        raise ValueError(f"no provider for {dep_type}")


def test_a_source_that_raises_reports_the_error():
    injector = make_injector(sources=[FailingSource()])

    def wants_other(other: Other) -> Other:
        return other

    with pytest.raises(ValueError, match="no provider"):
        injector.wrap_function(wants_other)()


def test_a_query_override_wins_over_a_later_source_but_not_the_globals():
    """The globals answer first, the overrides second, the sources last."""
    override, answered = Service(), Service()
    injector = make_injector(sources=[MappingSource({Service: answered})])
    injector.set_dependency(Service, override)

    assert injector.wrap_function(wants_service)() is injector.dependencies[Service]


def test_a_caller_supplied_keyword_wins():
    injector = make_injector()
    mine = Service()

    assert injector.wrap_function(wants_service)(service=mine) is mine


def test_a_caller_supplied_positional_wins():
    injector = make_injector()
    mine = Service()

    assert injector.wrap_function(wants_service)(mine) is mine


def test_a_caller_supplied_none_is_replaced_by_the_dependency():
    injector = make_injector()

    assert injector.wrap_function(wants_optional)(service=None) is injector.dependencies[Service]


def test_an_optional_annotation_is_injected_by_the_type_it_wraps():
    injector = make_injector()

    assert injector.wrap_function(wants_optional)() is injector.dependencies[Service]


def test_a_union_answers_by_its_first_covered_member():
    injector = make_injector()

    assert injector.wrap_function(wants_two_real_types)() is injector.dependencies[Service]


def test_a_union_no_member_covers_is_left_to_the_caller():
    injector = make_injector()
    other = Other()

    assert injector.wrap_function(wants_union_with_other)(service=other) is other


def test_two_parameters_are_injected_independently():
    injector = make_injector(sources=[RefusingSource({Declared})])
    declared = Declared()

    assert injector.wrap_function(wants_both)(declared=declared) == (
        injector.dependencies[Service],
        declared,
    )


def test_the_refined_signature_hides_only_the_injected_parameters():
    injector = make_injector(sources=[RefusingSource({Declared})])
    wrapped = injector.wrap_function(wants_both)

    assert list(wrapped.__signature__.parameters) == []


def test_the_refined_annotations_exclude_the_injected_parameters():
    injector = make_injector(sources=[RefusingSource({Declared})])
    wrapped = injector.wrap_function(wants_both)

    assert list(wrapped.__annotations__) == ["return"]


def test_wrapping_twice_returns_the_same_function():
    injector = make_injector()
    wrapped = injector.wrap_function(wants_service)

    assert injector.wrap_function(wrapped) is wrapped


def test_the_wrapped_function_keeps_the_original_metadata():
    injector = make_injector()
    wrapped = injector.wrap_function(wants_service)

    assert wrapped.__name__ == "wants_service"
    assert wrapped.__wrapped__ is wants_service


def test_the_engine_argument_is_dropped_when_the_target_does_not_declare_it():
    injector = make_injector(context_param="ctx")

    assert injector.wrap_function(takes_plain)(item="x", ctx="engine") == "x"


def test_the_engine_argument_is_forwarded_when_the_target_declares_it():
    injector = make_injector(context_param="ctx")

    assert injector.wrap_function(takes_service_and_ctx)(ctx="engine") == "engine"


def test_the_engine_argument_is_not_read_by_by_a_host_without_the_convention():
    injector = make_injector()

    assert injector.wrap_function(takes_plain)(item="x") == "x"


def test_a_ctx_annotated_parameter_is_not_injected():
    injector = make_injector(context_param="ctx")

    assert injector.wrap_function(wants_ctx)(ctx="engine", service=None) == "engine"


def test_the_annotations_of_a_function_declaring_ctx_keep_it():
    injector = make_injector(context_param="ctx")

    assert list(injector.wrap_function(wants_ctx).__annotations__) == ["ctx", "return"]


def test_with_global_dependency_extends_the_globals():
    injector = make_injector()
    other = Other()
    extended = injector.with_global_dependency(Other, other)

    assert extended.dependencies == {**injector.dependencies, Other: other}
    assert extended is not injector


def test_with_global_dependency_answers_the_new_type():
    mine = Other()
    injector = make_injector().with_global_dependency(Other, mine)

    def wants_other(other: Other) -> Other:
        return other

    assert injector.wrap_function(wants_other)() is mine


def test_a_key_that_enters_after_the_wrap_is_not_retroactive():
    """Classification happens at wrap time: a later declaration needs a later wrap."""
    injector = make_injector()
    wrapped = injector.wrap_function(wants_descriptor)
    injector.with_global_dependency(ServiceDescriptor, ServiceDescriptor())

    assert list(wrapped.__signature__.parameters) == ["instance"]


def test_a_function_without_annotations_is_left_alone():
    injector = make_injector()

    def plain(*args: Any, **kwargs: Any) -> Any:
        return args

    assert injector.wrap_function(plain)("x") == ("x",)
