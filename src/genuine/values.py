from dataclasses import dataclass, field
from inspect import Parameter, signature
from itertools import cycle
from random import Random
from typing import Callable, Generic, Iterable
from typing import Sequence as TySequence
from typing import TypeVar
from abc import abstractmethod

from .random import random
from .types import Context

T = TypeVar("T")


@dataclass
class ValueProvider(Generic[T]):
    random: Random = field(kw_only=True, default=random)
    dependencies: list[str] = field(kw_only=True, default_factory=list)

    @abstractmethod
    def __call__(self, context: Context | None = None) -> T:
        raise NotImplementedError


@dataclass
class Cycle(ValueProvider[T]):
    values: Iterable[T]

    def __post_init__(self) -> None:
        self.it = cycle(self.values)

    def __call__(self, context: Context | None = None) -> T:
        return next(self)

    def __next__(self) -> T:
        return next(self.it)


@dataclass
class RandomValue(ValueProvider[T]):
    values: TySequence[T]

    def __call__(self, context: Context | None = None) -> T:
        return next(self)

    def __next__(self) -> T:
        return self.random.choice(self.values)


@dataclass
class Computed(ValueProvider[T]):
    wrapped: Callable[..., T]

    def __post_init__(self) -> None:
        params = signature(self.wrapped).parameters
        if Parameter.VAR_POSITIONAL in params.values():
            raise ValueError("cannot do *args")
        if Parameter.VAR_KEYWORD in params.values():
            raise ValueError("cannot do *kwargs")

        self.dependencies = list(params)

    def __call__(self, context: Context | None = None) -> T:
        context = context or {}
        values = [context.get(param) for param in self.dependencies]
        return self.wrapped(*values)


@dataclass
class Sequence(ValueProvider[T]):
    wrapped: Callable[..., T] = field(default=lambda x: x)
    """
    Any callable where first argument is the index of the sequence counter,
    and other arguments are members of `Context`.

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

    i: int = 0

    def __post_init__(self) -> None:
        params = signature(self.wrapped).parameters
        if Parameter.VAR_POSITIONAL in params.values():
            raise ValueError("cannot do *args")
        if Parameter.VAR_KEYWORD in params.values():
            raise ValueError("cannot do *kwargs")

        self.dependencies = list(params)[1:]

    def __call__(self, context: Context | None = None) -> T:
        try:
            context = context or {}
            values = [context.get(dependency) for dependency in self.dependencies]
            return self.wrapped(self.i, *values)
        finally:
            self.i += 1
