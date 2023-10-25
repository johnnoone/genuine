from __future__ import annotations

import enum
from abc import ABC
from collections import ChainMap, UserDict, defaultdict, deque
from dataclasses import dataclass, field, fields, is_dataclass
from functools import cache, cached_property
from graphlib import CycleError, TopologicalSorter
from inspect import Parameter, signature
from itertools import cycle
from types import MappingProxyType
from typing import (
    Annotated,
    Any,
    Callable,
    Deque,
    Generic,
    Iterable,
    Iterator,
    Mapping,
    Protocol,
    Self,
    TypeAlias,
    TypeVar,
    cast,
)

from typing_extensions import Doc

T = TypeVar("T")
T_contrat = TypeVar("T_contrat", contravariant=True)

MaybeOverrides = Mapping[str, Any] | None

Context: TypeAlias = Mapping[str, Any]
"""
Mix of attributes and transient data
"""

Attributes: TypeAlias = Mapping[str, Any]
"""
Attributes of model object
"""

Name: TypeAlias = type[T] | tuple[type[T], str | None]
"""
Identifier of factory.

Can be only the model class, or a tuple of model class, profile.

For example:

```python
User
(User, "admin")
```

Those two identifier are equivalents:

```python
User
(User, None)
```
"""


class Strategy(enum.Enum):
    """Tell if current object must be created or built."""

    CREATE = enum.auto()
    BUILD = enum.auto()


class Overrides(UserDict[str, Any]):
    storage: Persist[Any] | None
    """When set, overrides the storage
    """
    strategy: Strategy | None
    """When set, overrides the strategy
    """

    def __init__(
        self,
        context: Mapping[str, Any] | None = None,
        *,
        storage: Persist[T] | None = None,
        strategy: Strategy | None = None,
    ) -> None:
        super().__init__(context or {})
        self.storage = storage
        self.strategy = strategy


def Absent() -> AbsentSentinel:
    return AbsentSentinel.DEFAULT


class AbsentSentinel(enum.Enum):
    """Sentinel used to mark absent of a value, when None is meaningfull.

    Use `Absent()` directly
    """

    DEFAULT = enum.auto()


@dataclass(kw_only=True)
class Factory(Generic[T]):
    model: type[T]
    aliases: set[str | None]
    parent: Factory[T] | None = None
    stages: list[Stage] = field(default_factory=list, repr=False)
    bot: FactoryBot = field(repr=False)
    persist: Persist[T] | None = None

    def __post_init__(self) -> None:
        for alias in self.aliases:
            self.bot.factories[self.model, alias] = self

    @cached_property
    def dsl(self) -> FactoryDSL:
        return FactoryDSL(instance=self)


@dataclass(slots=True)
class ValueSetter(Generic[T]):
    value: T

    def __call__(self, context: Context) -> T:
        return self.value


def make_value_setter(value: Any) -> tuple[AttrSetter, list[str]]:
    return ValueSetter(value), []


def make_set_stage(attr: str, *, value: Any, transient: bool = False) -> SetStage:
    setter: AttrSetter
    match value:
        case Computed():
            setter, dependencies = value, list(value.dependencies)
        case Cycle():
            setter, dependencies = value, []
        case Sequence():
            setter, dependencies = value, list(value.dependencies)
        case _:
            setter, dependencies = make_value_setter(value)
    stage = SetStage(attr, setter=setter, dependencies=dependencies, transient=transient)
    return stage


@dataclass(kw_only=True, slots=True)
class FactoryDSL:
    instance: Factory[Any]

    def set(self, attr: str, /, value: Any) -> None:
        stage = make_set_stage(attr, value=value, transient=False)
        self.instance.stages.append(stage)

    def add_hook(self, name: str, callback: UserHook) -> None:
        stage: HookStage[Any] = HookStage(name, callback)
        self.instance.stages.append(stage)

    def hook(self, name: str) -> Callable[[UserHook], None]:
        def inner(callback: Hook[T], /) -> None:
            self.add_hook(name, callback)

        return inner

    def transient(self) -> TransientDSL:
        return TransientDSL(factory=self.instance)

    def trait(self, name: str) -> TraitDSL:
        stage = TraitStage(name)
        self.instance.stages.append(stage)
        return stage.dsl

    def associate(
        self,
        attr: str,
        name: Name[Any],
        *traits: str,
        overrides: MaybeOverrides = None,
        strategy: Strategy = Strategy.CREATE,
    ) -> None:
        normalized_name = normalize_name(name)
        assoc = AssociateStage(
            attr, name=normalized_name, traits=list(traits), overrides=Overrides(overrides or {}), strategy=strategy
        )
        self.instance.stages.append(assoc)

    def sub_factory(self, aliases: Iterable[str] | str, storage: Persist[T] | None = None) -> FactoryDSL:
        """Define a sub factory that inherits from current."""
        normalized_aliases = normalize_aliases(aliases)
        if not aliases:
            raise ValueError("aliases is required")
        parent_factory = self.instance
        model = parent_factory.model
        factory = Factory(
            model=model, aliases=normalized_aliases, parent=parent_factory, bot=parent_factory.bot, persist=storage
        )
        return factory.dsl

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@dataclass(kw_only=True, slots=True)
class TransientDSL:
    factory: TraitStage | Factory[Any]

    def set(self, attr: str, /, value: Any) -> None:
        stage = make_set_stage(attr, value=value, transient=True)
        self.factory.stages.append(stage)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@dataclass(kw_only=True, slots=True)
class TraitDSL:
    factory: TraitStage

    def set(self, attr: str, /, value: Any) -> None:
        stage = make_set_stage(attr, value=value, transient=False)
        self.factory.stages.append(stage)

    def add_hook(self, name: str, callback: UserHook) -> None:
        stage: HookStage[Any] = HookStage(name, callback)
        self.factory.stages.append(stage)

    def hook(self, name: str) -> Callable[[UserHook], None]:
        def inner(callback: Hook[T], /) -> None:
            self.add_hook(name, callback)

        return inner

    def transient(self) -> TransientDSL:
        return TransientDSL(factory=self.factory)

    def associate(
        self,
        attr: str,
        name: tuple[type[T], str] | type[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        strategy: Strategy | None = None,
    ) -> None:
        normalized_name = normalize_name(name)
        # FIXME: broken
        stage = AssociateStage(
            attr=attr,
            name=normalized_name,
            traits=list(traits),
            overrides=Overrides(overrides or {}),
            strategy=strategy,
        )
        self.factory.stages.append(stage)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@dataclass(kw_only=True, slots=True)
class FactoryBot:
    factories: dict[Name[Any], Factory[Any]] = field(default_factory=dict)

    def get_factory(self, name: Name[T]) -> Factory[T]:
        try:
            return self.factories[name]
        except KeyError as error:
            raise FactoryNotFound(name) from error

    def define_factory(
        self,
        model: type[T],
        aliases: Iterable[str | None] | str | None = None,
        *,
        storage: Persist[Any] | None = None,
    ) -> FactoryDSL:
        """
        Parameters:
            persist: let define how instances will be persisted when using ``create`` and ``create_many``.
        """
        aliases = normalize_aliases(aliases) or {None}
        factory = Factory(model=model, aliases=aliases, parent=None, bot=self, persist=storage)
        return factory.dsl

    def sub_factory(
        self,
        parent: Name[T],
        aliases: Iterable[str] | str,
        *,
        storage: Persist[T] | None = None,
    ) -> FactoryDSL:
        """
        Parameters:
            persist: let define how instances will be persisted when using ``create`` and ``create_many``.
        """
        normalized_name = normalize_name(parent)
        parent_factory = self.get_factory(normalized_name)
        model = parent_factory.model
        normalized_aliases = normalize_aliases(aliases)
        if not parent:
            raise ValueError("model or parent required")
        factory = Factory(model=model, aliases=normalized_aliases, parent=parent_factory, bot=self, persist=storage)
        return factory.dsl

    def create(
        self,
        name: Name[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
        storage: Persist[T] | None = None,
    ) -> T:
        overrides = Overrides(overrides or {}, storage=storage)
        return next(self._create(1, name, *traits, overrides=overrides, refine=refine))

    def create_many(
        self,
        count: int,
        /,
        name: Name[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
        storage: Persist[T] | None = None,
    ) -> list[T]:
        overrides = Overrides(overrides or {}, storage=storage)
        return list(self._create(count, name, *traits, overrides=overrides, refine=refine))

    def _create(
        self,
        count: int,
        name: Name[T],
        *traits: str,
        overrides: Overrides,
        refine: Refine[T] = lambda instance: None,
    ) -> Iterator[T]:
        normalized_name = normalize_name(name)
        factory: Factory[T] = self.get_factory(normalized_name)
        model, generate_data, hooks = self._construct(factory, *traits, overrides=overrides)
        persist = overrides.storage or self._get_persister(factory)
        for _ in range(count):
            attributes, context = generate_data()
            instance = model(**attributes)
            for hook in hooks["after_build"]:
                hook(instance, context)
            for hook in hooks["before_create"]:
                hook(instance, context)
            persist(instance, context)
            for hook in hooks["after_create"]:
                hook(instance, context)
            refine(instance)
            yield instance

    def _get_persister(self, factory: Factory[T]) -> Persist[T]:
        current = cast(Factory[T] | None, factory)
        while current:
            if persist := current.persist:
                return persist
            current = current.parent
        return lambda x, y: None

    def build(
        self,
        name: Name[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
    ) -> T:
        overrides = Overrides(overrides or {})
        return next(self._build(1, name, *traits, overrides=overrides, refine=refine))

    def build_many(
        self,
        count: int,
        /,
        name: Name[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
    ) -> list[T]:
        overrides = Overrides(overrides or {})
        return list(self._build(count, name, *traits, overrides=overrides, refine=refine))

    def _build(
        self,
        count: int,
        name: Name[T],
        *traits: str,
        overrides: Overrides,
        refine: Refine[T] = lambda instance: None,
    ) -> Iterator[T]:
        normalized_name = normalize_name(name)
        factory: Factory[T] = self.get_factory(normalized_name)
        model, generate_data, hooks = self._construct(factory, *traits, overrides=overrides)
        for _ in range(count):
            attributes, context = generate_data()
            instance = model(**attributes)
            for hook in hooks["after_build"]:
                hook(instance, context)
            refine(instance)
            yield instance

    def attributes_for(
        self,
        name: Name[T],
        *traits: str,
        overrides: MaybeOverrides = None,
    ) -> Attributes:
        """
        Parameters:
            name: trop bien
        """
        normalized_name = normalize_name(name)
        overrides = Overrides(overrides or {})
        factory: Factory[T] = self.get_factory(normalized_name)
        _, generate_data, _ = self._construct(factory, *traits, overrides=overrides)
        attributes, _ = generate_data()
        return attributes

    def _yield_stages(self, factory: Factory[Any], traits: list[str]) -> Iterator[Stage]:
        current = factory
        factories: Deque[Factory[Any]]
        factories = deque([current])

        stages: Deque[Stage]
        stages = deque([])

        while factory.parent:
            factory = factory.parent
            factories.appendleft(factory)

        # prepend attributes_setters with defaults infered from model
        model = cast(type, current.model)
        yield from infer_default_stages_for_model(model)

        while factories:
            factory = factories.popleft()
            stages.extend(factory.stages)

            while stages:
                stage = stages.popleft()
                match stage:
                    case TraitStage(name=trait_name, stages=traits_stages) if trait_name in traits:
                        stages.extend(traits_stages)
                    case TraitStage(name=trait_name, stages=traits_stages):
                        pass
                    case _:
                        yield stage

    def _construct(
        self, factory: Factory[T], *traits: str, overrides: Overrides
    ) -> tuple[type[T], Callable[[], tuple[Attributes, Context]], dict[str, list[Hook[T]]]]:
        model = cast(type, factory.model)

        overrides = Overrides(overrides)
        attributes_setters: dict[str, SetStage | BoundAssociateStage[T]] = {}
        transients_setters: dict[str, SetStage] = {}
        hooks = defaultdict(list)

        for stage in self._yield_stages(factory, list(traits)):
            match stage:
                case SetStage(attr, transient=False) as stage:
                    attributes_setters[attr] = stage
                case SetStage(attr, transient=True) as stage:
                    transients_setters[attr] = stage
                case HookStage(hook, func):
                    # TODO: pop potential override
                    hooks[hook].append(func)
                case AssociateStage(attr):
                    attributes_setters[attr] = stage.bind(self)
                case _:
                    raise NotImplementedError(stage)

        for attr, value in overrides.items():
            if isinstance(value, Overrides):
                if (stage1 := attributes_setters.get(attr)) and isinstance(stage1, LateOverrides):
                    stage1.overrides |= value
                    if value.strategy:
                        stage1.strategy = value.strategy
                    continue
                else:
                    value = dict(value)
            if attr in attributes_setters:
                attributes_setters[attr] = make_set_stage(attr, value=value, transient=False)
                continue
            if attr in transients_setters:
                transients_setters[attr] = make_set_stage(attr, value=value, transient=True)
                continue
        setters: list[S] = list((transients_setters | attributes_setters).values()) # type: ignore
        return model, AttributeGenerator(setters), hooks


@dataclass
class CyclicDependencies(Exception):
    dependencies: Any


@dataclass
class FactoryNotFound(Exception, Generic[T]):
    name: Name[T]

class S(Protocol):
    attr: str
    dependencies: list[str]
    transient: bool
    def setter(self, context: Any) -> Any:
        ...

class AttributeGenerator:
    def __init__(self, setters: Iterable[S]) -> None:
        self.setters = {setter.attr: setter for setter in setters}

    @cached_property
    def graph(self) -> tuple[str, ...]:
        graph: TopologicalSorter[str] = TopologicalSorter()
        for setter in self.setters.values():
            graph.add(setter.attr, *setter.dependencies)
        try:
            return tuple(graph.static_order())
        except CycleError as error:
            deps = {setter.attr: set(setter.dependencies) for setter in self.setters.values()}
            raise CyclicDependencies(dependencies=deps) from error

    def __call__(self) -> tuple[Attributes, Context]:
        setters = self.setters
        # setter: S
        attributes: dict[str, Any] = {}
        transients: dict[str, Any] = {}
        context: Context = MappingProxyType(ChainMap(transients, attributes))
        for attr in self.graph:
            setter = setters[attr]
            value = setter.setter(context)
            if setter.transient is True:
                transients[attr] = value
            else:
                attributes[attr] = value
        return attributes, dict(context)


@cache
def infer_default_stages_for_model(model: type) -> list[SetStage]:
    return list(_infer_default_stages_for_model(model))


def _infer_default_stages_for_model(model: type) -> Iterator[SetStage]:
    if is_dataclass(model):
        for field in fields(model):  # noqa: F402
            yield make_set_stage(field.name, value=None, transient=False)


class SetError(Exception):
    pass


@dataclass
class SetStage:
    attr: str
    setter: AttrSetter
    dependencies: list[str] = field(default_factory=list)
    transient: bool = False


@dataclass
class TraitStage:
    name: str
    stages: list[Stage] = field(default_factory=list)

    @cached_property
    def dsl(self) -> TraitDSL:
        return TraitDSL(factory=self)


@dataclass
class AssociateStage(Generic[T]):
    attr: str
    name: Name[T]
    traits: list[str]
    overrides: Overrides = field(default_factory=Overrides)
    strategy: Strategy | None = None

    def bind(self, bot: FactoryBot, strategy: Strategy | None = None) -> BoundAssociateStage[T]:
        return BoundAssociateStage(
            bot=bot,
            attr=self.attr,
            name=self.name,
            traits=list(self.traits),
            overrides=Overrides(self.overrides),
            strategy=strategy or self.strategy,
        )


@dataclass
class BoundAssociateStage(Generic[T]):
    bot: FactoryBot
    attr: str
    name: Name[T]
    traits: list[str]
    overrides: Overrides
    strategy: Strategy | None = None

    @property
    def dependencies(self) -> list[str]:
        return []

    @property
    def transient(self) -> bool:
        return False

    def setter(self, context: Context) -> T:
        if self.strategy == Strategy.BUILD:
            return self.bot.build(self.name, *self.traits, overrides=self.overrides)
        else:
            return self.bot.create(self.name, *self.traits, overrides=self.overrides)


class LateOverrides(ABC):
    overrides: Overrides
    strategy: Strategy | None


LateOverrides.register(BoundAssociateStage)


@dataclass
class HookStage(Generic[T]):
    hook: str
    func: Hook[T]


# class Hook(Protocol[T_contrat]):
#     def __call__(self, instance: T_contrat, context: Context) -> None:
#         ...
Hook: TypeAlias = Callable[[T, Context], Any]

# class Refine(Protocol[T_contrat]):
#     def __call__(self, instance: T_contrat) -> None:
#         ...

UserHook = Annotated[
    Callable[[Any, Any], Any],
    Doc(
        """
        Any callable that has 2 parameters: instance and context.

        For example:

        ```python
        @factory.add_hook("after_create", lambda instance, context: instance.tags.append("new-tag"))
        ```
        """
    ),
]
Refine: TypeAlias = Callable[[T], Any]

Stage = SetStage | TraitStage | AssociateStage | HookStage


class AttrSetter(Protocol):
    def __call__(self, context: Context) -> Any:
        ...


@dataclass
class Cycle(Generic[T]):
    values: Iterable[T]

    def __post_init__(self) -> None:
        self.it = cycle(self.values)
        self.dependencies: list[str] = []

    def __call__(self, context: Context) -> T:
        return next(self)

    def __next__(self) -> T:
        return next(self.it)


@dataclass
class Computed(Generic[T]):
    wrapped: Callable[..., T]

    def __post_init__(self) -> None:
        params = signature(self.wrapped).parameters
        if Parameter.VAR_POSITIONAL in params.values():
            raise ValueError("cannot do *args")
        if Parameter.VAR_KEYWORD in params.values():
            raise ValueError("cannot do *kwargs")

        self.dependencies = tuple(params)

    def __call__(self, context: Context) -> T:
        values = [context.get(param) for param in self.dependencies]
        return self.wrapped(*values)


UserSequenceFunc = Annotated[
    Callable[..., T],
    Doc(
        """
        Any callable where first argument is the index of the sequence counter, and other arguments are members of Context.
        """
    ),
]


@dataclass
class Sequence(Generic[T]):
    wrapped: Annotated[
        Callable[..., T],
        Doc(
            """
            Any callable where first argument is the index of the sequence counter, and other arguments are members of `Context`.

            For example, a simple counter:

            ```python
            seq = Sequence(lambda i: f"rank#{i}")
            assert seq() == "rank#0"
            assert seq() == "rank#1"
            assert seq() == "rank#2"
            ```

            Generate email based on instance.name and counter index:

            ```python
            seq = Sequence(lambda i, name: f"{name}.{i}@example.com".lower)
            assert seq({"name": "John"}) == "john.0@example.com"
            assert seq({"name": "John"}) == "john.1@example.com"
            assert seq({"name": "Dave"}) == "dave.2@example.com"
            ```

            """
        ),
    ]
    i: int = 0

    def __post_init__(self) -> None:
        params = signature(self.wrapped).parameters
        if Parameter.VAR_POSITIONAL in params.values():
            raise ValueError("cannot do *args")
        if Parameter.VAR_KEYWORD in params.values():
            raise ValueError("cannot do *kwargs")

        _, *names = params
        self.dependencies = tuple(names)

    def __call__(self, context: Context | None = None) -> T:
        try:
            context = context or {}
            values = [context.get(param) for param in self.dependencies]
            return self.wrapped(self.i, *values)
        finally:
            self.i += 1


class Persist(Protocol[T_contrat]):
    def __call__(self, instance: T_contrat, context: Context) -> None:
        ...


def normalize_name(name: Name[T]) -> Name[T]:
    if isinstance(name, tuple):
        return name
    else:
        return name, None


def normalize_aliases(aliases: Iterable[str | None] | Iterable[str] | str | None) -> set[str | None]:
    if aliases is None:
        return {None}
    elif isinstance(aliases, str):
        return {aliases}
    else:
        return set(aliases)
