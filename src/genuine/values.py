from dataclasses import dataclass, field
from inspect import Parameter, signature
from itertools import cycle
from random import Random
from typing import Annotated, Callable, Generic, Iterable
from typing import Sequence as TySequence
from typing import TypeVar

from typing_extensions import Doc  # type: ignore[attr-defined]

from .types import Context

T = TypeVar("T")


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
class RandomValue(Generic[T]):
    values: TySequence[T]
    rand: Random = field(default_factory=Random)

    def __post_init__(self) -> None:
        self.dependencies: list[str] = []

    def __call__(self, context: Context) -> T:
        return next(self)

    def __next__(self) -> T:
        return self.rand.choice(self.values)


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
    wrapped: Annotated[
        Callable[..., T],
        Doc(
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
