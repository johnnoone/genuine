from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from random import Random
from types import NoneType, UnionType, GenericAlias
from typing import (  # type: ignore[attr-defined]
    Any,
    TypeVar,
    _LiteralGenericAlias,
    _GenericAlias,
    Union,
    TypeGuard,
    get_args,
    get_origin,
    get_type_hints,
    overload,
    is_typeddict,
)
from collections.abc import Mapping, Sequence, Set
from typing_extensions import _AnnotatedAlias

Metadata = tuple[Any, ...]
Slots = tuple[Any, ...]
AnyScalar = str | int | float | bool | None
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


@overload
def stub(model: type[T], *, random: Random | None = None) -> T:
    ...


@overload
def stub(model: T, *, random: Random | None = None) -> T:
    ...


def stub(model: T | type[T], *, random: Random | None = None) -> T:
    random = random or Random()
    metadata: Metadata = ()
    return _stub(model, metadata=metadata, random=random)  # type: ignore[no-any-return]


def stub_attributes(model: type[T], *, random: Random | None = None) -> dict[str, Any]:
    assert is_dataclass(model)
    annos = get_type_hints(model, include_extras=True)
    return {field.name: stub(annos[field.name]) for field in fields(model)}


def _stub(model: Any, *, metadata: Metadata = (), random: Random) -> Any:
    """
    Parameters:
        metadata: data from top annotated
    """
    random = random or Random()
    # instances
    if not isinstance(model, type) and isinstance(
        model, str | float | int | Decimal | list | dict | set | tuple | NoneType | tuple | datetime | date | time
    ):
        # assume an instance of something
        return model
    # special forms
    if model is Any:
        return _stub(AnyScalar, metadata=metadata, random=random)
    if is_annotated(model):
        return stub_annotated(model, metadata=metadata, random=random)
    if is_literal(model):
        return stub_literal(model, metadata=metadata, random=random)
    if is_dataclass(model):
        return stub_dataclass(model, metadata=metadata, random=random)
    if is_union(model):
        return stub_union(model, metadata=metadata, random=random)
    if isinstance(model, TypeVar):
        return stub_TypeVar(model, metadata=metadata, random=random)

    # structures
    if is_typeddict(model):
        return stub_typeddict(model, metadata=metadata, random=random)
    if is_generic_alias(model):
        return stub_generic_alias(model, metadata=metadata, random=random)
    if isinstance(model, type) and issubclass(model, Mapping | dict):
        return stub_mapping(model, metadata=metadata, random=random)
    if isinstance(model, type) and issubclass(model, Set):
        return stub_set(model, metadata=metadata, random=random)
    if isinstance(model, type) and issubclass(model, Sequence) and not issubclass(model, str):
        return stub_sequence(model, metadata=metadata, random=random)

    # regular scalar types
    if isinstance(model, type):
        if issubclass(model, str):
            return stub_str(model, metadata=metadata, random=random)
        if issubclass(model, NoneType):
            return stub_none(model, metadata=metadata, random=random)
        if issubclass(model, datetime):
            return stub_datetime(model, metadata=metadata, random=random)
        if issubclass(model, date):
            return stub_date(model, metadata=metadata, random=random)
        if issubclass(model, time):
            return stub_time(model, metadata=metadata, random=random)
        if issubclass(model, bool):
            return stub_bool(model, metadata=metadata, random=random)
        if issubclass(model, int):
            return stub_int(model, metadata=metadata, random=random)
        if issubclass(model, float):
            return stub_float(model, metadata=metadata, random=random)
        if issubclass(model, Decimal):
            return stub_decimal(model, metadata=metadata, random=random)

    else:
        return None


def is_generic_alias(model: Any) -> TypeGuard[GenericAlias]:
    if isinstance(model, _GenericAlias):
        return True
    if isinstance(model, GenericAlias):
        return True
    return False


def is_annotated(model: Any) -> bool:
    return isinstance(model, _AnnotatedAlias)


def is_literal(model: Any) -> bool:
    return isinstance(model, _LiteralGenericAlias)


def is_union(model: Any) -> TypeGuard[UnionType]:
    origin = get_origin(model)
    return origin in [Union, UnionType]


def stub_annotated(model: _AnnotatedAlias, *, metadata: Metadata, random: Random) -> Any:
    """Annotated"""
    return _stub(model.__origin__, metadata=model.__metadata__, random=random)


def stub_literal(model: _LiteralGenericAlias, *, metadata: Metadata, random: Random) -> Any:
    """Literal"""
    choice = random.choice(get_args(model))
    return _stub(choice, metadata=metadata, random=random)


def stub_dataclass(model: type, *, metadata: Metadata, random: Random) -> object:
    annos = get_type_hints(model, include_extras=True)
    return model(**{field.name: _stub(annos[field.name], random=random) for field in fields(model)})


def stub_typeddict(model: type, *, metadata: Metadata, random: Random) -> object:
    annos = get_type_hints(model, include_extras=True)
    result = model(**{key: _stub(val, random=random) for key, val in annos.items()})
    return result


def stub_none(model: type, *, metadata: Metadata, random: Random) -> None:
    return None


def stub_union(model: UnionType, *, metadata: Metadata, random: Random) -> Any:
    choice = random.choice(get_args(model))
    return _stub(choice, metadata=(), random=random)


def stub_TypeVar(model: TypeVar, *, metadata: Metadata, random: Random) -> Any:
    choice = random.choice(model.__constraints__ or (AnyScalar,))
    return _stub(choice, metadata=(), random=random)


def stub_str(model: type[str], *, metadata: Metadata, random: Random) -> str:
    return model("string")


def stub_datetime(model: type[datetime], *, metadata: Metadata, random: Random) -> datetime:
    return model.now(timezone.utc)


def stub_date(model: type[date], *, metadata: Metadata, random: Random) -> date:
    return model.today()


def stub_time(model: type[time], *, metadata: Metadata, random: Random) -> time:
    return model(tzinfo=timezone.utc)


def stub_bool(model: type[bool], *, metadata: Metadata, random: Random) -> bool:
    choice = random.choice([True, False])
    return model(choice)


def stub_int(model: type[int], *, metadata: Metadata, random: Random) -> int:
    return model(1)


def stub_float(model: type[float], *, metadata: Metadata, random: Random) -> float:
    return model(0.1)


def stub_decimal(model: type[Decimal], *, metadata: Metadata, random: Random) -> Decimal:
    return model("0.1")


def stub_sequence(
    model: type[Sequence[T]], *, metadata: Metadata, random: Random, slots: Slots = (AnyScalar,)
) -> Sequence[T]:
    element_model = slots[0]
    elements = []
    for _ in range(3):
        elements.append(_stub(element_model, metadata=(), random=random))
    return model(elements)  # type: ignore[call-arg]


def stub_mapping(
    model: type[Mapping[K, V]], *, metadata: Metadata, random: Random, slots: Slots = (str, AnyScalar)
) -> Mapping[K, V]:
    key_model = slots[0]
    val_model = slots[1]
    members = []
    for _ in range(3):
        members.append(
            (
                _stub(key_model, metadata=(), random=random),
                _stub(val_model, metadata=(), random=random),
            )
        )
    return model(members)  # type: ignore[call-arg]


def stub_set(model: type[Set[T]], *, metadata: Metadata, random: Random, slots: Slots = (AnyScalar,)) -> Set[T]:
    slots = slots or (AnyScalar,)
    element_model = slots[0]
    elements = []
    for _ in range(3):
        elements.append(_stub(element_model, metadata=(), random=random))
    return model(elements)  # type: ignore[call-arg]


def stub_generic_alias(model: GenericAlias, *, metadata: Metadata, random: Random) -> Any:
    origin = get_origin(model)
    slots = get_args(model)

    if issubclass(origin, Sequence):
        return stub_sequence(origin, metadata=metadata, random=random, slots=slots)
    if issubclass(origin, Mapping):
        return stub_mapping(origin, metadata=metadata, random=random, slots=slots)
    if issubclass(origin, Set):
        return stub_set(origin, metadata=metadata, random=random, slots=slots)
    # a custom class?
    return _stub(origin, metadata=metadata, random=random)

    raise NotImplementedError
