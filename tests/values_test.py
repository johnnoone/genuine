from dataclasses import dataclass
from random import Random
from typing import Any

from genuine import build, define_factory
from genuine.values import RandomValue


@dataclass
class Holder:
    value: Any


def test_random(global_rand: Random) -> None:
    global_rand.seed(1)
    generator = RandomValue([1, 2, 3])
    assert next(generator) == 1
    assert next(generator) == 3
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 1
    assert next(generator) == 2


def test_random_with_custom_seed() -> None:
    rand = Random(123)
    generator = RandomValue([1, 2, 3], random=rand)
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 1
    assert next(generator) == 2
    assert next(generator) == 2
    assert next(generator) == 1


def test_factory(global_rand: Random) -> None:
    global_rand.seed(1)
    with define_factory(Holder) as factory:
        factory.set("value", RandomValue(["foo", "bar", "baz"]))
    assert build(Holder).value == "foo"
    assert build(Holder).value == "baz"
    assert build(Holder).value == "foo"
    assert build(Holder).value == "bar"
