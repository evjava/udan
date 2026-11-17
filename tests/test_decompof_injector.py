"""Injector tests: what a factory asks for by type is what it gets.

Framework-free by construction: the factories below are plain functions, the
instances are plain objects, and nothing here imports any udan
component. That is the property under test -- the injector resolves by
annotation, so it needs nothing else to exist.
"""

import pytest

from udan.decompof.injector import (
    AmbiguousDependencyError,
    Injector,
    UnresolvableDependencyError,
)


class Base:
    pass


class Left(Base):
    pass


class Right(Base):
    pass


def no_dependencies() -> None:
    pass


def wants_left(instance: Left) -> Left:
    return instance


def wants_base(instance: Base) -> Base:
    return instance


def wants_missing(instance: dict) -> dict:
    return instance


def wants_optional(instance: Left | None = None) -> Left | None:
    return instance


def wants_two_types(instance: Left | Right) -> Left | Right | None:
    return instance


def wants_unannotated(instance) -> None:
    pass


def wants_positional_star(*instance: Base) -> None:
    pass


def test_provided_instance_is_resolved_by_its_exact_type():
    left = Left()

    assert Injector().provide(left).resolve(Left) is left


def test_the_last_instance_of_a_type_wins():
    first, second = Left(), Left()
    injector = Injector().provide(first, second)

    assert injector.arguments(wants_left) == {"instance": second}


def test_an_ancestor_annotation_is_satisfied_by_an_instance_of_a_subtype():
    left = Left()
    injector = Injector().provide(left)

    assert injector.arguments(wants_base) == {"instance": left}


def test_an_ambiguous_annotation_raises_instead_of_guessing():
    injector = Injector().provide(Left(), Right())

    with pytest.raises(AmbiguousDependencyError, match="Base"):
        injector.arguments(wants_base)


def test_an_unsatisfied_annotation_raises():
    with pytest.raises(UnresolvableDependencyError, match="instance"):
        Injector().arguments(wants_missing)


def test_an_unannotated_parameter_cannot_be_resolved():
    """There is no type to derive from, so an annotation is the price of entry."""
    with pytest.raises(UnresolvableDependencyError, match="instance"):
        Injector().arguments(wants_unannotated)


def test_a_defaulted_parameter_is_left_unset_when_nothing_provides_it():
    assert Injector().arguments(wants_optional) == {}


def test_an_optional_annotation_is_resolved_to_the_type_it_wraps():
    left = Left()

    assert Injector().provide(left).arguments(wants_optional) == {"instance": left}


def test_a_union_of_two_types_resolves_to_neither():
    """Two candidates is a guess, and the injector does not guess."""
    with pytest.raises(UnresolvableDependencyError, match="instance"):
        Injector().provide(Left()).arguments(wants_two_types)


def test_star_parameters_are_never_resolved():
    assert Injector().provide(Left()).arguments(wants_positional_star) == {}


def test_a_factory_needing_nothing_is_called_with_nothing():
    assert Injector().provide(Left()).arguments(no_dependencies) == {}


def test_a_scope_wins_over_the_container():
    """Each extra is offered a plugin of its own, by the type it annotates."""
    injector = Injector().provide(Left())
    scoped = Left()

    assert injector.arguments(wants_left, scope={Left: scoped}) == {"instance": scoped}
    assert injector.arguments(wants_left) == {"instance": injector.resolve(Left)}


def test_call_passes_whatever_arguments_resolved():
    injector = Injector().provide(Left())

    assert injector.call(wants_left) is injector.resolve(Left)


# The source: what builds services, asked for whatever the host does not hold.
# The same framework-free property as above -- the source below is a plain
# callable, and it stands in for the IoC container without any of it existing.


def test_the_source_is_asked_when_nothing_was_provided():
    """The host names the things it has; the source covers the things it builds."""
    built = {}

    assert Injector().served_by(lambda annotation: built).arguments(wants_missing) == {"instance": built}


def test_a_provided_instance_wins_over_the_source():
    """What the host holds is what the host means to hand over."""
    provided, built = {}, {"from": "source"}
    injector = Injector().provide(provided).served_by(lambda annotation: built)

    assert injector.arguments(wants_missing) == {"instance": provided}


def test_a_scope_wins_over_the_source():
    injector = Injector().served_by(lambda annotation: {})
    scoped = {}

    assert injector.arguments(wants_missing, scope={dict: scoped}) == {"instance": scoped}


def test_a_defaulted_parameter_is_served_when_the_source_can_build_it():
    left = Left()

    assert Injector().served_by(lambda annotation: left).arguments(wants_optional) == {"instance": left}
    assert Injector().arguments(wants_optional) == {}  # no source: the default stands


def test_what_the_source_raises_is_what_the_caller_sees():
    """A missing factory says more than a wrapper would -- and the mount fails either way."""

    def source(annotation: type) -> None:
        raise KeyError(annotation)

    with pytest.raises(KeyError):
        Injector().served_by(source).arguments(wants_missing)


def test_an_annotation_that_is_not_a_bare_type_is_never_asked_of_the_source():
    """A union of two types asks for neither, so neither the source nor a guess answers it."""

    def refuse(annotation: type) -> None:
        pytest.fail(f"the source was asked for {annotation!r}")

    with pytest.raises(UnresolvableDependencyError, match="instance"):
        Injector().served_by(refuse).arguments(wants_two_types)
