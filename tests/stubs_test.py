from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Generic, Literal, TypedDict, TypeVar, Union

from pytest_subtests import SubTests

from genuine.stubs import stub, stub_attributes

T = TypeVar("T")


@dataclass
class User:
    name: str
    age: int


@dataclass
class GenericObject(Generic[T]):
    attr: T


class MyDict(TypedDict):
    attr1: str
    attr2: int


def test_stub(subtests: SubTests) -> None:
    value: Any

    # types

    with subtests.test("int type"):
        value = stub(int)
        assert isinstance(value, int)

    with subtests.test("float type"):
        value = stub(float)
        assert isinstance(value, float)

    with subtests.test("str type"):
        value = stub(str)
        assert isinstance(value, str)

    with subtests.test("list type"):
        value = stub(list)
        assert isinstance(value, list)

    with subtests.test("set type"):
        value = stub(set)
        assert isinstance(value, set)

    with subtests.test("dict type"):
        value = stub(dict)
        assert isinstance(value, dict)

    with subtests.test("tuple type"):
        value = stub(tuple)
        assert isinstance(value, tuple)

    with subtests.test("datetime type"):
        value = stub(datetime)
        assert isinstance(value, datetime)

    with subtests.test("date type"):
        value = stub(date)
        assert isinstance(value, date)

    with subtests.test("time type"):
        value = stub(time)
        assert isinstance(value, time)

    with subtests.test("Decimal type"):
        value = stub(Decimal)
        assert isinstance(value, Decimal)

    # values

    with subtests.test("int value"):
        value = stub(42)
        assert isinstance(value, int) and value == 42

    with subtests.test("float value"):
        value = stub(0.1)
        assert isinstance(value, float) and value == 0.1

    with subtests.test("None value"):
        value = stub(None)
        assert value is None

    with subtests.test("str value"):
        value = stub("foo")
        assert isinstance(value, str) and value == "foo"

    with subtests.test("list value"):
        value = stub(list([1, 2, 3]))
        assert isinstance(value, list) and value == [1, 2, 3]

    with subtests.test("set value"):
        value = stub(set([1, 2, 3]))
        assert isinstance(value, set) and value == {1, 2, 3}

    with subtests.test("dict value"):
        value = stub(dict(foo="bar"))
        assert isinstance(value, dict) and value == {"foo": "bar"}

    with subtests.test("tuple value"):
        value = stub(tuple([1, 2, 3]))
        assert isinstance(value, tuple) and value == (1, 2, 3)

    with subtests.test("datetime value"):
        value = stub(datetime.now())
        assert isinstance(value, datetime)

    with subtests.test("date value"):
        value = stub(date.today())
        assert isinstance(value, date)

    with subtests.test("time value"):
        value = stub(time())
        assert isinstance(value, time)

    with subtests.test("Decimal value"):
        value = stub(Decimal("1"))
        assert isinstance(value, Decimal)

    # special forms

    with subtests.test("literal form"):
        value = stub(Literal[1, 2, 3])
        assert value in (1, 2, 3)

    with subtests.test("literal form"):
        value = stub(Union[str, bool])
        assert isinstance(value, str | bool)

    with subtests.test("Any form"):
        value = stub(Any)
        assert isinstance(value, str | int | float | bool | None)

    with subtests.test("Annotated form"):
        value = stub(Annotated[str, 1, 2, 3])
        assert isinstance(value, str)

        value = stub(Annotated[float, 1, 2, 3])
        assert isinstance(value, float)

    with subtests.test("list[str] form"):
        value = stub(list[str])
        assert isinstance(value, list)
        assert all(isinstance(member, str) for member in value)

    with subtests.test("set[str] form"):
        value = stub(set[str])
        assert isinstance(value, set)
        assert all(isinstance(member, str) for member in value)

    with subtests.test("tuple[str] form"):
        value = stub(tuple[str])
        assert isinstance(value, tuple)
        assert all(isinstance(member, str) for member in value)

    with subtests.test("dict[str, int] form"):
        value = stub(dict[str, int])
        assert isinstance(value, dict)
        assert all(isinstance(member, str) for member in value.keys())
        assert all(isinstance(member, int) for member in value.values())

    # Custom dataclasses
    with subtests.test("User dataclass"):
        value = stub(User)
        assert isinstance(value, User)
        assert isinstance(value.name, str)
        assert isinstance(value.age, int)

    with subtests.test("A dataclass with generic not configured"):
        value = stub(GenericObject)
        assert isinstance(value, GenericObject)

    with subtests.test("A dataclass with generic configured"):
        value = stub(GenericObject[str])
        assert isinstance(value, GenericObject)


def test_typed_dict(subtests: SubTests) -> None:
    # Custom dicts
    value = stub(MyDict)
    assert isinstance(value, dict)
    assert isinstance(value["attr1"], str)
    assert isinstance(value["attr2"], int)


def test_stub_attributes() -> None:
    value = stub_attributes(User)
    assert isinstance(value, dict)
    assert isinstance(value["name"], str)
    assert isinstance(value["age"], int)
