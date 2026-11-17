"""Tests for the udan.decompof container: the declaration DSL and the resolution engine."""

import pytest

from udan.decompof import (
    ContainerError,
    Declaration,
    DeclarationError,
    DependencyCycleError,
    DuplicateProviderError,
    Provider,
    UnresolvableKeyError,
    decorate,
    make_container,
    provide,
)


class Config:
    """A stand-in configuration service."""


class Logger:
    """A stand-in logging service."""


class Engine:
    """A stand-in service with dependencies, built through provide(source=...)."""

    def __init__(self, logger: Logger, config: Config):
        self.logger = logger
        self.config = config


class Plain:
    """A stand-in service with no dependencies at all."""


class Missing:
    """A stand-in service no provider offers, for the missing-key tests."""


class CountingLogger(Logger):
    """A stand-in decoration wrapping a Logger."""

    def __init__(self, logger: Logger):
        self.logger = logger


class TimedLogger(Logger):
    """A stand-in second decoration, wrapping whatever came before it."""

    def __init__(self, logger: Logger, config: Config):
        self.logger = logger
        self.config = config


class CountingConfig(Config):
    """A stand-in decoration wrapping a Config."""

    def __init__(self, config: Config):
        self.config = config


class CycleLeft:
    """A stand-in service that asks for CycleRight, completing a two-service cycle."""

    def __init__(self, right: CycleRight):
        self.right = right


class CycleRight:
    """A stand-in service that asks for CycleLeft back."""

    def __init__(self, left: CycleLeft):
        self.left = left


class VerbPlugin:
    """A stand-in plugin: two verbs naming their dependencies by annotation."""

    def __init__(self) -> None:
        self.attached = None
        self.detached = []

    def attach(self, logger: Logger) -> None:
        self.attached = logger

    def detach(self, logger: Logger, config: Config) -> None:
        self.detached = [logger, config]

    def wants_missing(self, service: Missing) -> None:
        self.attached = service


class AppProvider(Provider):
    @provide
    def config(self) -> Config:
        return Config()

    @provide
    def logger(self, config: Config) -> Logger:
        return Logger()

    engine = provide(source=Engine, provides=Engine)

    plain = provide(source=Plain, provides=Plain)


class LoggerProvider(Provider):
    @provide
    def logger(self, config: Config) -> Logger:
        return Logger()


class CountingProvider(Provider):
    @decorate
    def counted(self, logger: Logger) -> Logger:
        return CountingLogger(logger)


class CountingAndTimingProvider(Provider):
    @decorate
    def counted(self, logger: Logger) -> Logger:
        return CountingLogger(logger)

    @decorate
    def timed(self, logger: Logger, config: Config) -> Logger:
        return TimedLogger(logger, config)


def test_get_builds_the_dependency_chain():
    assert isinstance(make_container(AppProvider()).get(Engine), Engine)


def test_get_builds_lazily_so_a_service_is_untouched_until_asked_for():
    built: list[str] = []

    class LazyProvider(Provider):
        @provide
        def plain(self) -> Plain:
            built.append("plain")
            return Plain()

        @provide
        def config(self) -> Config:
            return Config()

    container = make_container(LazyProvider())
    assert built == []

    container.get(Plain)
    assert built == ["plain"]


def test_get_memoizes_so_a_key_is_built_once():
    container = make_container(AppProvider())

    assert container.get(Logger) is container.get(Logger)


def test_context_instance_wins_over_a_factory():
    config = Config()

    class RaisingProvider(Provider):
        @provide
        def config(self) -> Config:
            raise AssertionError("a context value must win over the factory")

    container = make_container(RaisingProvider(), context={Config: config})

    assert container.get(Config) is config


def test_context_instance_reaches_dependent_factories():
    config = Config()

    assert make_container(AppProvider(), context={Config: config}).get(Engine).config is config


def test_keys_are_exact_types():
    """A key is the type its factory provides, not a type it could satisfy."""
    container = make_container(AppProvider())

    assert type(container.get(Logger)) is Logger


def test_duplicate_keys_fail_the_build():
    with pytest.raises(
        DuplicateProviderError, match=r"Logger is provided by both AppProvider \(logger\) and LoggerProvider"
    ):
        make_container(AppProvider(), LoggerProvider())


def test_unresolvable_dependency_fails_the_build_and_names_the_asking_factory():
    """A factory asking for a key nothing provides is a build error, not a get() away."""

    class WantsUnknown(Provider):
        @provide
        def engine(self, missing: Missing) -> Engine:
            return Engine()

    with pytest.raises(UnresolvableKeyError, match="nothing provides Missing: 'missing' of Engine asks for it"):
        make_container(WantsUnknown())


def test_build_error_reports_who_wants_the_asking_factory():
    """The report reaches the roots: the asker's own dependents are named too."""

    class Middle:
        def __init__(self, missing: Missing):
            self.missing = missing

    class Top:
        def __init__(self, middle: Middle):
            self.middle = middle

    class MiddleProvider(Provider):
        @provide
        def middle(self, missing: Missing) -> Middle:
            return Middle(missing)

    class TopProvider(Provider):
        @provide
        def top(self, middle: Middle) -> Top:
            return Top(middle)

    with pytest.raises(
        UnresolvableKeyError, match="nothing provides Missing: 'missing' of Middle asks for it; Middle is wanted by Top"
    ):
        make_container(MiddleProvider(), TopProvider())


def test_missing_key_fails_the_get_and_reports_that_no_factory_asks_for_it():
    """A get() can only miss for a key the wiring never declares, so the asker is the caller."""
    with pytest.raises(
        UnresolvableKeyError,
        match=(
            r"nothing provides Missing: nothing in the wiring asks for it, "
            r"so a get\(\) call asked for it directly; the container provides: Config, Engine, Logger, Plain"
        ),
    ):
        make_container(AppProvider()).get(Missing)


def test_circular_dependencies_fail_the_get():
    class LeftProvider(Provider):
        @provide
        def left(self, right: CycleRight) -> CycleLeft:
            return CycleLeft(right)

    class RightProvider(Provider):
        @provide
        def right(self, left: CycleLeft) -> CycleRight:
            return CycleRight(left)

    with pytest.raises(DependencyCycleError, match="CycleLeft -> CycleRight -> CycleLeft"):
        make_container(LeftProvider(), RightProvider()).get(CycleLeft)


def test_source_class_dependencies_are_read_off_its_init():
    declaration = Declaration(Engine, provides=Engine)

    assert declaration.provides is Engine
    assert declaration.parameters == {"logger": Logger, "config": Config}


def test_source_class_without_init_asks_for_nothing():
    assert Declaration(Plain, provides=Plain).parameters == {}


def test_declaration_of_a_bare_decorator_reads_the_annotations():
    declaration = AppProvider.__dict__["config"]

    assert declaration.provides is Config
    assert declaration.parameters == {}


def test_declaration_without_return_annotation_raises():
    def unannotated(self):
        return None

    with pytest.raises(DeclarationError, match="no return annotation, so no key to provide"):
        Declaration(unannotated)


def test_declaration_of_a_parameterised_annotation_raises():
    """X | None asks for neither X nor None, so it is a definition error, not a silent miss."""

    with pytest.raises(DeclarationError, match="annotates.*which is not a type key"):

        class OptionalProvider(Provider):
            @provide
            def engine(self, logger: Logger | None = None) -> Engine:
                return Engine()


def test_declaration_of_an_unannotated_parameter_raises():
    with pytest.raises(DeclarationError, match="has no annotation, so it names no key"):

        class UnannotatedProvider(Provider):
            @provide
            def engine(self, logger) -> Engine:
                return Engine()


def test_a_decoration_that_builds_fresh_instead_of_wrapping_raises():
    """A decoration must ask for the key it provides - otherwise it is a provide."""
    with pytest.raises(DeclarationError, match="a decoration does not ask for Logger, so it looks like provide"):

        class IndependentProvider(Provider):
            @decorate
            def fresh(self) -> Logger:
                return Logger()


def test_provide_source_without_provides_raises():
    with pytest.raises(DeclarationError, match=r"provide\(source=...\) needs provides=<key>"):
        provide(source=Engine)


def test_provide_with_both_factory_and_source_raises():
    with pytest.raises(DeclarationError, match="not both"):
        provide(Engine, source=Engine, provides=Engine)


def test_provide_with_neither_factory_nor_source_raises():
    with pytest.raises(DeclarationError, match="not neither"):
        provide()


def test_decorate_source_without_provides_raises():
    with pytest.raises(DeclarationError, match=r"decorate\(source=...\) needs provides=<key>"):
        decorate(source=CountingLogger)


def test_decorate_with_both_factory_and_source_raises():
    with pytest.raises(DeclarationError, match="not both"):
        decorate(CountingLogger, source=CountingLogger, provides=Logger)


def test_decorate_with_neither_factory_nor_source_raises():
    with pytest.raises(DeclarationError, match="not neither"):
        decorate()


def test_provider_declarations_are_read_base_classes_first():
    class Base(Provider):
        @provide
        def config(self) -> Config:
            return Config()

    class Child(Base):
        @provide
        def logger(self, config: Config) -> Logger:
            return Logger()

    container = make_container(Child())

    assert isinstance(container.get(Config), Config)
    assert isinstance(container.get(Logger), Logger)


def test_dependents_share_the_instance_the_container_built():
    container = make_container(AppProvider())

    assert container.get(Engine).logger is container.get(Logger)


def test_decorate_wraps_the_instance_a_factory_builds():
    container = make_container(AppProvider(), CountingProvider())

    decorated = container.get(Logger)

    assert type(decorated) is CountingLogger
    assert type(decorated.logger) is Logger


def test_decorations_apply_in_declaration_order():
    container = make_container(AppProvider(), CountingAndTimingProvider())

    timed = container.get(Logger)

    assert type(timed) is TimedLogger
    assert type(timed.logger) is CountingLogger
    assert type(timed.logger.logger) is Logger


def test_a_decorated_key_is_still_a_singleton():
    container = make_container(AppProvider(), CountingProvider())

    assert container.get(Logger) is container.get(Logger)


def test_dependents_get_the_decorated_instance():
    container = make_container(AppProvider(), CountingProvider())

    assert container.get(Engine).logger is container.get(Logger)


def test_a_decoration_resolves_its_other_dependencies():
    config = Config()
    container = make_container(AppProvider(), CountingAndTimingProvider(), context={Config: config})

    timed = container.get(Logger)

    assert timed.config is config
    assert type(timed.logger) is CountingLogger


def test_decorate_source_class_wraps_through_its_init():
    class SourceDecoratorProvider(Provider):
        counted = decorate(source=CountingLogger, provides=Logger)

    container = make_container(AppProvider(), SourceDecoratorProvider())

    assert type(container.get(Logger)) is CountingLogger


def test_a_decoration_asking_for_a_missing_key_fails_the_build():
    class WantsMissingDecoratorProvider(Provider):
        @decorate
        def counted(self, logger: Logger, missing: Missing) -> Logger:
            return CountingLogger(logger)

    with pytest.raises(
        UnresolvableKeyError,
        match="nothing provides Missing: 'missing' of Logger asks for it; Logger is wanted by Engine",
    ):
        make_container(AppProvider(), WantsMissingDecoratorProvider())


def test_decorating_a_key_nothing_provides_fails_the_build():
    class OrphanDecoratorProvider(Provider):
        @decorate
        def counted(self, logger: Logger) -> Logger:
            return CountingLogger(logger)

    with pytest.raises(UnresolvableKeyError, match="nothing provides Logger: nothing for the decoration to wrap"):
        make_container(OrphanDecoratorProvider())


def test_decorating_a_context_value_fails_the_build():
    class ConfigCountingProvider(Provider):
        @decorate
        def counted(self, config: Config) -> Config:
            return CountingConfig(config)

    with pytest.raises(ContainerError, match="cannot decorate Config: it is a context value, not a factory's instance"):
        make_container(ConfigCountingProvider(), context={Config: Config()})


def test_a_decoration_asking_for_its_own_key_through_another_service_is_a_cycle():
    class Loop:
        def __init__(self, logger: Logger):
            self.logger = logger

    class LoopProvider(Provider):
        @provide
        def logger(self) -> Logger:
            return Logger()

        @provide
        def loop(self, logger: Logger) -> Loop:
            return Loop(logger)

        @decorate
        def counted(self, logger: Logger, loop: Loop) -> Logger:
            return CountingLogger(logger)

    with pytest.raises(DependencyCycleError, match="Logger -> Loop -> Logger"):
        make_container(LoopProvider()).get(Logger)


def test_keyword_only_parameter_is_as_good_a_dependency_as_a_positional_one():
    class KwOnlyEngine:
        def __init__(self, *, logger: Logger):
            self.logger = logger

    class KwOnlyProvider(Provider):
        engine = provide(source=KwOnlyEngine, provides=KwOnlyEngine)

    container = make_container(KwOnlyProvider(), context={Logger: Logger()})

    assert container.get(KwOnlyEngine).logger is container.get(Logger)


def test_call_resolves_the_annotated_parameters_and_invokes():
    """A verb gets its dependencies from the container: the singletons it already built."""
    plugin = VerbPlugin()

    make_container(AppProvider()).get(Logger)
    container = make_container(AppProvider())

    container.call(plugin.attach)

    assert type(plugin.attached) is Logger


def test_call_builds_a_never_built_dependency():
    """A verb's dependency is built on the call when nothing asked for it before."""
    plugin = VerbPlugin()

    make_container(AppProvider()).call(plugin.detach)

    assert [type(service).__name__ for service in plugin.detached] == ["Logger", "Config"]


def test_check_lets_a_resolvable_verb_pass():
    """A verb whose dependencies the wiring declares passes the check silently."""
    plugin = VerbPlugin()

    make_container(AppProvider()).check(plugin.attach)


def test_check_fails_the_build_when_a_verb_asks_for_an_unprovided_key():
    """The verbs join the wiring validation: a missing key is a build error, not a call-time one."""
    plugin = VerbPlugin()

    with pytest.raises(UnresolvableKeyError, match="nothing provides Missing: 'service' of VerbPlugin.wants_missing"):
        make_container(AppProvider()).check(plugin.wants_missing)


def test_a_verb_parameter_without_annotation_names_no_key():
    """The same reading rules a factory's declaration applies: an unannotated parameter is a definition error."""

    def attach(logger) -> None:
        return None

    with pytest.raises(DeclarationError, match="has no annotation, so it names no key"):
        make_container(AppProvider()).check(attach)


def test_a_verb_asking_for_a_parameterised_annotation_raises():
    """`X | None` names neither X nor None, so a verb's union parameter is a definition error too."""

    def detach(logger: Logger | None = None) -> None:
        return None

    with pytest.raises(DeclarationError, match="annotates.*which is not a type key"):
        make_container(AppProvider()).check(detach)


def test_introspection_sees_what_the_container_wires():
    """plugins_system's udan_ioc_deps reads declarations off the provider classes."""

    graph = {
        declaration.provides.__name__: [dep.__name__ for dep in declaration.parameters.values()]
        for _, declaration in AppProvider().declarations()
    }

    assert graph == {"Config": [], "Logger": ["Config"], "Engine": ["Logger", "Config"], "Plain": []}


def test_introspection_lists_decorations_apart_from_the_factories():
    """A decoration provides no key of its own, so it is not a node of the dependency graph."""
    provider = CountingAndTimingProvider()
    factories = {name: declaration for name, declaration in provider.declarations() if not declaration.is_decorator}

    assert factories == {}
    assert [name for name, _ in provider.decorations()] == ["counted", "timed"]
    assert [declaration.provides for _, declaration in provider.decorations()] == [Logger, Logger]
