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
    TypeVarTuple,
    Unpack,
    cast,
)

T = TypeVar("T")
T_contrat = TypeVar("T_contrat", contravariant=True)
Ts = TypeVarTuple("Ts")

MaybeOverrides = Mapping[str, Any] | None

Context: TypeAlias = Mapping[str, Any]
"""
Mix of attributes and transient data
"""

Attributes: TypeAlias = Mapping[str, Any]
"""
Attributes of model object
"""

Name: TypeAlias = type[T] | tuple[type[T], str]
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
    """Tell if current object must be created or built.
    """

    CREATE = enum.auto()
    BUILD = enum.auto()


class Overrides(UserDict):
    storage: Persist | None
    """When set, overrides the storage
    """
    strategy: Strategy | None
    """When set, overrides the strategy
    """

    def __init__(
        self, context: Mapping[str, Any] | None = None, *, storage: Persist | None = None, strategy: Strategy | None = None
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
    aliases: set[str]
    parent: Factory | None = None
    stages: list[Stage] = field(default_factory=list, repr=False)
    bot: FactoryBot = field(repr=False)
    persist: Persist | None = None

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
            setter, dependencies = value, value.dependencies
        case Cycle():
            setter, dependencies = value, []
        case Sequence():
            setter, dependencies = value, value.dependencies
        case _:
            setter, dependencies = make_value_setter(value)
    stage = SetStage(attr, setter=setter, dependencies=dependencies, transient=transient)
    return stage


@dataclass(kw_only=True, slots=True)
class FactoryDSL(Generic[T]):
    instance: Factory[T]

    def set(self, attr: str, /, value) -> None:
        stage = make_set_stage(attr, value=value, transient=False)
        self.instance.stages.append(stage)

    def add_hook(self, name: str, callback: Hook[T]) -> None:
        stage: HookStage[T] = HookStage(name, callback)
        self.instance.stages.append(stage)

    def hook(self, name: str) -> Callable[[Hook[T]], None]:
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
        name: tuple[type[T], str] | type[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        strategy: Strategy = Strategy.CREATE,
    ) -> None:
        name = normalize_name(name)
        assoc = AssociateStage(attr, name=name, traits=list(traits), overrides=overrides or {}, strategy=strategy)
        self.instance.stages.append(assoc)

    def sub_factory(self, aliases: Sequence[str] | str, storage: Persist | None = None) -> FactoryDSL:
        """Define a sub factory that inherits from current."""
        aliases = normalize_aliases(aliases)
        if not aliases:
            raise ValueError("aliases is required")
        parent_factory = self.instance
        model = parent_factory.model
        factory = Factory(model=model, aliases=aliases, parent=parent_factory, bot=parent_factory.bot, persist=storage)
        return factory.dsl

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args):
        pass


@dataclass(kw_only=True, slots=True)
class TransientDSL:
    factory: TraitStage | Factory

    def set(self, attr: str, /, value) -> None:
        stage = make_set_stage(attr, value=value, transient=True)
        self.factory.stages.append(stage)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args):
        pass


@dataclass(kw_only=True, slots=True)
class TraitDSL:
    factory: TraitStage

    def set(self, attr: str, /, value) -> None:
        stage = make_set_stage(attr, value=value, transient=False)
        self.factory.stages.append(stage)

    def add_hook(self, name: str, callback: Hook[T]) -> None:
        stage: HookStage[T] = HookStage(name, callback)
        self.factory.stages.append(stage)

    def hook(self, name: str) -> Callable[[Hook[T]], None]:
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
        name = normalize_name(name)
        # FIXME: broken
        stage = AssociateStage(
            attr=attr,
            name=name,
            traits=list(traits),
            overrides=overrides or {},
            strategy=strategy,
        )
        self.factory.stages.append(stage)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args):
        pass


@dataclass(kw_only=True, slots=True)
class FactoryBot:
    factories: dict[str, Factory] = field(default_factory=dict)

    def get_factory(self, name: tuple[type[T], str | None]) -> Factory[T]:
        try:
            return self.factories[name]
        except KeyError as error:
            raise FactoryNotFound(name) from error

    def define_factory(
        self,
        model: type[T],
        aliases: Sequence[str] | None = None,
        *,
        storage: Persist | None = None,
    ) -> FactoryDSL[T]:
        """
        Parameters:
            persist: let define how instances will be persisted when using ``create`` and ``create_many``.
        """
        aliases = normalize_aliases(aliases) or {None}
        factory = Factory(model=model, aliases=aliases, parent=None, bot=self, persist=storage)
        return factory.dsl

    def sub_factory(
        self,
        parent: Name,
        aliases: Sequence[str] | str,
        *,
        storage: Persist | None = None,
    ) -> FactoryDSL[T]:
        """
        Parameters:
            persist: let define how instances will be persisted when using ``create`` and ``create_many``.
        """
        parent = normalize_name(parent)
        parent_factory = self.get_factory(parent)
        model = parent_factory.model
        aliases = normalize_aliases(aliases)
        if not parent:
            raise ValueError("model or parent required")
        factory = Factory(model=model, aliases=aliases, parent=parent_factory, bot=self, persist=storage)
        return factory.dsl

    def create(
        self,
        name: Name,
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine = lambda instance: None,
        storage: Persist | None = None,
    ) -> T:
        overrides = Overrides(overrides or {}, storage=storage)
        return next(self._create(1, name, *traits, overrides=overrides, refine=refine))

    def create_many(
        self,
        count: int,
        /,
        name: Name,
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine = lambda instance: None,
        storage: Persist | None = None,
    ) -> list[T]:
        overrides = Overrides(overrides or {}, storage=storage)
        return list(self._create(count, name, *traits, overrides=overrides, refine=refine))

    def _create(
        self,
        count: int,
        name: Name,
        *traits: str,
        overrides: Overrides,
        refine: Refine = lambda instance: None,
    ) -> Iterator[T]:
        name = normalize_name(name)
        factory: Factory[T] = self.get_factory(name)
        model, generate_data, hooks = self._construct(factory, *traits, overrides=Overrides(overrides or {}))
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
        while factory:
            if persist := factory.persist:
                return persist
            factory = factory.parent
        return lambda x, y: None

    def build(
        self,
        name: Name,
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine = lambda instance: None,
    ) -> T:
        overrides = Overrides(overrides or {})
        return next(self._build(1, name, *traits, overrides=overrides, refine=refine))

    def build_many(
        self,
        count: int,
        /,
        name: Name,
        *traits: str,
        overrides: MaybeOverrides = None,
        refine: Refine = lambda instance: None,
    ) -> list[T]:
        overrides = Overrides(overrides or {})
        return list(self._build(count, name, *traits, overrides=overrides, refine=refine))

    def _build(
        self,
        count: int,
        name: Name,
        *traits: str,
        overrides: Overrides,
        refine: Refine = lambda instance: None,
    ) -> Iterator[T]:
        name = normalize_name(name)
        factory: Factory[T] = self.get_factory(name)
        model, generate_data, hooks = self._construct(factory, *traits, overrides=Overrides(overrides or {}))
        for _ in range(count):
            attributes, context = generate_data()
            instance = model(**attributes)
            for hook in hooks["after_build"]:
                hook(instance, context)
            refine(instance)
            yield instance

    def attributes_for(
        self,
        name: Name,
        *traits: str,
        overrides: MaybeOverrides = None,
    ) -> Attributes:
        """
        Parameters:
            name: trop bien
        """
        name = normalize_name(name)
        overrides = Overrides(overrides or {})
        factory: Factory[T] = self.get_factory(name)
        _, generate_data, _ = self._construct(factory, *traits, overrides=Overrides(overrides or {}))
        attributes, _ = generate_data()
        return attributes

    def _yield_stages(self, factory: Factory, traits: list[str]) -> Iterator[Stage]:
        current = factory
        factories: Deque[Factory]
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
    ) -> tuple[type[T], Callable[[], tuple[Attributes, Context]], dict[str, list]]:
        model = cast(type, factory.model)

        overrides = Overrides(overrides)
        attributes_setters: dict[str, SetStage | BoundAssociateStage] = {}
        transients_setters: dict[str, SetStage] = {}
        hooks = defaultdict(list)

        for stage in self._yield_stages(factory, traits):
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
        setters = list((transients_setters | attributes_setters).values())
        return model, AttributeGenerator(setters), hooks


@dataclass
class CyclicDependencies(Exception):
    dependencies: Any


@dataclass
class FactoryNotFound(Exception):
    name: str


class AttributeGenerator:
    def __init__(self, setters: Iterable[SetStage | BoundAssociateStage]) -> None:
        self.setters = {setter.attr: setter for setter in setters}

    @cached_property
    def graph(self):
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
        setter: SetStage | BoundAssociateStage
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
    name: tuple[type[T], str | None]
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
    name: tuple[type[T], str | None]
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


LateOverrides.register(BoundAssociateStage)


@dataclass
class HookStage(Generic[T]):
    hook: str
    func: Hook[T]


class Hook(Protocol[T_contrat]):
    def __call__(self, instance: T_contrat, context: Context) -> None:
        ...


class Refine(Protocol[T]):
    def __call__(self, instance: T) -> None:
        ...


Stage = SetStage | TraitStage | AssociateStage | HookStage


class AttrSetter(Protocol):
    def __call__(self, context: Context) -> Any:
        ...


@dataclass
class Cycle(Generic[T]):
    values: Iterable[T]

    def __post_init__(self):
        self.it = cycle(self.values)
        self.dependencies = []

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


@dataclass
class Sequence(Generic[T]):
    wrapped: Callable[[int, Unpack[Ts]], T]
    i: int = 0

    def __post_init__(self) -> None:
        params = signature(self.wrapped).parameters
        if Parameter.VAR_POSITIONAL in params.values():
            raise ValueError("cannot do *args")
        if Parameter.VAR_KEYWORD in params.values():
            raise ValueError("cannot do *kwargs")

        _, *names = params
        self.dependencies = tuple(names)

    def __call__(self, context: Context) -> T:
        try:
            values = [context.get(param) for param in self.dependencies]
            return self.wrapped(self.i, *values)
        finally:
            self.i += 1


class Persist(Protocol[T]):
    def __call__(self, instance: T, context: Context) -> None:
        ...


def normalize_name(name: Name) -> tuple[type[T], str | None]:
    if isinstance(name, tuple):
        return name
    else:
        return name, None


def normalize_aliases(aliases: Sequence[str] | str | None) -> set[str]:
    if aliases is None:
        return {None}
    elif isinstance(aliases, str):
        return {aliases}
    else:
        return set(aliases)
