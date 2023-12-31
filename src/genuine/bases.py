from __future__ import annotations

import enum
from abc import ABC
from collections import ChainMap, UserDict, defaultdict, deque
from dataclasses import dataclass, field
from functools import cache, cached_property
from graphlib import CycleError, TopologicalSorter
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

from typing_extensions import Doc  # type: ignore[attr-defined]

from .errors import DerivationError
from .stubs import stub_attributes
from .types import Context
from .values import Computed, Cycle, RandomValue, Sequence, ValueProvider

T = TypeVar("T")
T_contrat = TypeVar("T_contrat", contravariant=True)

MaybeOverrides = Mapping[str, Any] | None


Attributes: TypeAlias = Mapping[str, Any]
"""
Collected attributes of model object.

For example for this object:

```python
@dataclass
class User:
    given_name: str
    family_name: str
    age: int
```

This container should looks like:

```python
{"given_name": "John", "family_name": "Smith", "age": 45}
```
"""

Name: TypeAlias = tuple[type[T], str | None]
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


@dataclass
class Lookup:
    attribute: str


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
    alias: str | None
    parent: Factory[T] | None = None
    stages: list[Stage] = field(default_factory=list, repr=False)
    persist: Persist[T] | None = None


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
        case ValueProvider(dependencies=dependencies):
            setter = value
        case _:
            setter, dependencies = make_value_setter(value)
    stage = SetStage(attr, setter=setter, dependencies=dependencies, transient=transient)
    return stage


@dataclass(kw_only=True, slots=True)
class FactoryDSL:
    gen: Genuine
    factories: list[Factory[Any]]

    def set(self, attr: str, /, value: Any | Computed[Any] | Cycle[Any] | Sequence[Any] | RandomValue[Any]) -> None:
        """Set a value for `attr`.

        Value may be anything.

        Using Computed, it can be based on other attributes or transient data.
        """
        stage = make_set_stage(attr, value=value, transient=False)
        for factory in self.factories:
            factory.stages.append(stage)

    def add_hook(self, name: str, callback: UserHook) -> None:
        """Register a hook
        Example:

        ```python
        factory.add_hook("after_build", lambda instance, context: ...)
        ```
        """

        stage: HookStage[Any] = HookStage(name, callback)
        for factory in self.factories:
            factory.stages.append(stage)

    def hook(self, name: str) -> Callable[[UserHook], None]:
        """Decorator used to register hook

        Returns:
            decorator

        Example:

        ```python
        @factory.hook("after_build")
        def _(instance, context):
            pass
        ```
        """

        def inner(callback: Hook[T], /) -> None:
            self.add_hook(name, callback)

        return inner

    def transient(self) -> TransientDSL:
        """
        Returns:
            The definition of factory
        """
        return TransientDSL(factories=list(self.factories))

    def trait(self, name: str) -> TraitDSL:
        """
        Returns:
            The definition of factory
        """
        stage = TraitStage(name)
        for factory in self.factories:
            factory.stages.append(stage)
        return TraitDSL(factory=stage)

    def associate(
        self,
        attr: str,
        model: type[Any],
        *traits: str,
        overrides: MaybeOverrides = None,
        strategy: Strategy | None = None,
    ) -> None:
        stage = AssociateStage(
            attr,
            model=model,
            traits=list(traits),
            overrides=Overrides(overrides or {}),
            strategy=strategy,
        )
        for factory in self.factories:
            factory.stages.append(stage)

    def derived_factory(
        self, aliases: Iterable[str] | str, /, storage: Persist[T] | None | AbsentSentinel = Absent()
    ) -> FactoryDSL:
        """Define a sub factory that inherits from current.

        Returns:
            The definition of factory
        """
        aliases = cast(set[str], normalize_aliases(aliases) - {None})
        if not aliases:
            raise ValueError("aliases is required")

        factories: list[Factory[Any]] = []
        derive_factory = self.gen.derive_factory
        for parent in self.factories:
            for alias in aliases:
                factory = derive_factory(parent, alias)
                if storage != Absent():
                    factory.persist = storage
                factories.append(factory)

        return FactoryDSL(gen=self.gen, factories=factories)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@dataclass(kw_only=True, slots=True)
class TransientDSL:
    factories: list[TraitStage | Factory[Any]]

    def set(self, attr: str, /, value: Any | Computed[Any] | Cycle[Any] | Sequence[Any]) -> None:
        stage = make_set_stage(attr, value=value, transient=True)
        for factory in self.factories:
            factory.stages.append(stage)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@dataclass(kw_only=True, slots=True)
class TraitDSL:
    factory: TraitStage

    def set(self, attr: str, /, value: Any | Computed[Any] | Cycle[Any] | Sequence[Any]) -> None:
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
        """
        Returns:
            The definition of factory
        """
        return TransientDSL(factories=[self.factory])

    def associate(
        self,
        attr: str,
        model: type[T],
        *traits: str,
        overrides: MaybeOverrides = None,
        strategy: Strategy | None = None,
    ) -> None:
        # FIXME: broken
        stage = AssociateStage(
            attr=attr,
            model=model,
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
class Genuine:
    factories: dict[Name[Any], Factory[Any]] = field(default_factory=dict, repr=False)

    def derive_factory(self, parent: Factory[T], alias: str) -> Factory[T]:
        model = parent.model
        if not alias:
            raise DerivationError("Alias is required")
        key = (model, alias)
        factory: Factory[T] | None = self.factories.get(key)
        if not factory:
            factory = self.factories[model, alias] = Factory(model=model, alias=alias, parent=parent)
        elif factory and factory.parent != parent:
            real = cast(Factory[T], factory.parent)
            raise DerivationError(
                f"Factory {model.__name__} {alias} cannot derive from {parent.alias}: "
                f"it is already derived from {real.alias}"
            )
        return factory

    def get_factory(self, model: type[T], alias: str | None, *, autodefine: bool = False) -> Factory[T]:
        if (model, alias) in self.factories:
            return self.factories[model, alias]
        factory = self.factories.setdefault((model, None), Factory(model=model, alias=None))
        if alias and autodefine:
            # Always derive from main factory
            factory = self.factories[model, alias] = Factory(model=model, alias=alias, parent=factory)
        return factory

    def define_factory(
        self,
        model: type[T],
        aliases: Annotated[
            Iterable[str | None] | str | None,
            Doc(
                """
                Alias attached to this factory.

                For example if you open you definition like this:

                ```python
                with define_factory(User, "account") as factory:
                    ...

                build(User, "account")
                ```

                it will match the previous definition.

                If alias is missing, it will target the main factory.

                You can also define multiple factories at once, using this syntaxe:

                ```python
                with define_factory(User, {"alias1", "alias2", "alias3"}) as factory:
                    ...

                build(User, "alias1")
                build(User, "alias2")
                build(User, "alias3")
                ```

                """
            ),
        ] = None,
        /,
        *,
        storage: Annotated[
            Persist[Any] | None | AbsentSentinel,
            Doc(
                """
                Let define how instances will be persisted when using ``create`` and ``create_many``
                """
            ),
        ] = Absent(),
    ) -> FactoryDSL:
        """
        Returns:
            The definition of factory
        """
        factories = []
        for alias in normalize_aliases(aliases):
            factory: Factory[T] = self.get_factory(model, alias, autodefine=True)
            if storage != Absent():
                factory.persist = storage
            factories.append(factory)
        return FactoryDSL(gen=self, factories=factories)

    def create(
        self,
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
        storage: Annotated[
            Persist[T] | None,
            Doc(
                """
                Tell how the instance is persisted.

                When not set, fallback to the one defined by `define_factory`
                """
            ),
        ] = None,
    ) -> T:
        """Create one model instance.

        ```python
        user = create(User)
        assert isinstance(user, User)
        ```
        """
        overrides = Overrides(overrides or {}, storage=storage)
        return next(self._create(1, model, *specializations, overrides=overrides, refine=refine))

    def create_many(
        self,
        count: int,
        /,
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
        storage: Annotated[
            Persist[T] | None,
            Doc(
                """
                Tell how instances are persisted.

                When not set, fallback to the one defined by `define_factory`
                """
            ),
        ] = None,
    ) -> list[T]:
        """Create many model instances.

        ```python
        user1, user2 = create_many(2, User)
        assert isinstance(user1, User)
        assert isinstance(user2, User)
        ```
        """
        overrides = Overrides(overrides or {}, storage=storage)
        return list(self._create(count, model, *specializations, overrides=overrides, refine=refine))

    def _create(
        self,
        count: int,
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: Overrides,
        refine: Refine[T] = lambda instance: None,
    ) -> Iterator[T]:
        factory: Factory[T]
        if specializations:
            # TODO: find if first arg is part of name or a traits
            factory = self.get_factory(model, specializations[0])
        else:
            factory = self.get_factory(model, None)
        traits = list(specializations)
        if traits and factory.alias == traits[0]:
            traits.pop(0)
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
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
    ) -> T:
        """Build one model instance.

        ```python
        user = build(User)
        assert isinstance(user, User)
        ```
        """
        overrides = Overrides(overrides or {})
        return next(self._build(1, model, *specializations, overrides=overrides, refine=refine))

    def build_many(
        self,
        count: int,
        /,
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: MaybeOverrides = None,
        refine: Refine[T] = lambda instance: None,
    ) -> list[T]:
        """Build many model instances.

        ```python
        user1, user2 = build_many(2, User)
        assert isinstance(user1, User)
        assert isinstance(user2, User)
        ```
        """
        overrides = Overrides(overrides or {})
        return list(self._build(count, model, *specializations, overrides=overrides, refine=refine))

    def _build(
        self,
        count: int,
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: Overrides,
        refine: Refine[T] = lambda instance: None,
    ) -> Iterator[T]:
        factory: Factory[T]
        if specializations:
            # TODO: find if first arg is part of name or a traits
            factory = self.get_factory(model, specializations[0])
        else:
            factory = self.get_factory(model, None)
        traits = list(specializations)
        if traits and factory.alias == traits[0]:
            traits.pop(0)
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
        model: type[T],
        *specializations: Annotated[
            str,
            Doc(
                """
                Where the first value is the factory alias, and the others are traits
                """
            ),
        ],
        overrides: MaybeOverrides = None,
    ) -> Attributes:
        """Get attributes for one model instance"""
        factory: Factory[T]
        if specializations:
            # TODO: find if first arg is part of name or a traits
            factory = self.get_factory(model, specializations[0])
        else:
            factory = self.get_factory(model, None)
        traits = list(specializations)
        if traits and factory.alias == traits[0]:
            traits.pop(0)

        overrides = Overrides(overrides or {})
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
        setters: list[S] = list((transients_setters | attributes_setters).values())  # type: ignore
        return model, AttributeGenerator(setters), hooks


@dataclass
class CyclicDependencies(Exception):
    dependencies: Any


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
    for key, value in stub_attributes(model).items():
        yield make_set_stage(key, value=value, transient=False)


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


@dataclass
class AssociateStage(Generic[T]):
    attr: str
    model: type[T]
    traits: list[str]
    overrides: Overrides = field(default_factory=Overrides)
    strategy: Strategy | None = None

    def bind(self, gen: Genuine, strategy: Strategy | None = None) -> BoundAssociateStage[T]:
        return BoundAssociateStage(
            gen=gen,
            attr=self.attr,
            model=self.model,
            traits=list(self.traits),
            overrides=Overrides(self.overrides),
            strategy=strategy or self.strategy,
        )


@dataclass
class BoundAssociateStage(Generic[T]):
    gen: Genuine
    attr: str
    model: type[T]
    traits: list[str]
    overrides: Overrides
    strategy: Strategy | None = None

    @property
    def dependencies(self) -> list[str]:
        dependencies = []
        for val in self.overrides.values():
            if isinstance(val, Lookup):
                dependencies.append(val.attribute[1:])
        return dependencies

    @property
    def transient(self) -> bool:
        return False

    def setter(self, context: Context) -> T:
        overrides = self.overrides
        for key, val in overrides.items():
            if isinstance(val, Lookup):
                overrides = overrides | {key: context[val.attribute[1:]]}
        if self.strategy == Strategy.BUILD:
            return self.gen.build(self.model, *self.traits, overrides=overrides)
        else:
            return self.gen.create(self.model, *self.traits, overrides=overrides)


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

UserHook = Callable[[Any, Any], Any]
"""
Any callable that has 2 parameters: instance and context.

Parameters:
    instance T: the instance being build
    context Context: the context

Example:

```python
@factory.add_hook("after_create", lambda instance, context: instance.tags.append("new-tag"))
```
"""

Refine: TypeAlias = Callable[[T], Any]

Stage = SetStage | TraitStage | AssociateStage | HookStage


class AttrSetter(Protocol):
    def __call__(self, context: Context) -> Any:
        ...


UserSequenceFunc = Annotated[
    Callable[..., T],
    Doc(
        """
        Any callable where first argument is the index of the sequence counter,
        and other arguments are members of Context.
        """
    ),
]


class Persist(Protocol[T_contrat]):
    def __call__(self, instance: T_contrat, context: Context) -> None:
        ...


def normalize_aliases(aliases: Iterable[str | None] | Iterable[str] | str | None) -> set[str | None]:
    if aliases is None:
        return {None}
    elif isinstance(aliases, str):
        return {aliases}
    elif not aliases:
        return {None}
    else:
        return set(aliases)
