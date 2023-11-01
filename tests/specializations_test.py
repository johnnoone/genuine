import pytest
from genuine import define_factory, build, DerivationError
from dataclasses import dataclass
# from typing import Any


@dataclass
class User:
    spec: str
    tr1: str | None = None
    tr2: str | None = None
    tr3: str | None = None


def test_specialization() -> None:
    with define_factory(User) as factory:
        factory.set("spec", "main")
        factory.set("tr1", None)
        factory.set("tr2", None)
        factory.set("tr3", None)

        factory.trait("tr1").set("tr1", "main")
        factory.trait("tr2").set("tr2", "main")
        factory.trait("tr3").set("tr3", "main")

        with factory.derived_factory("derived1") as derived1:
            derived1.set("spec", "derived1")
            derived1.trait("tr2").set("tr2", "derived1")

            with derived1.derived_factory("derived2") as derived2:
                derived2.set("spec", "derived2")
                derived2.trait("tr1").set("tr1", "derived2")
                derived2.trait("tr3").set("tr3", "derived2")

    assert build(User) == User(spec="main", tr1=None, tr2=None, tr3=None)
    assert build(User, "derived1") == User(spec="derived1", tr1=None, tr2=None, tr3=None)
    assert build(User, "derived2") == User(spec="derived2", tr1=None, tr2=None, tr3=None)

    assert build(User, "tr1") == User(spec="main", tr1="main", tr2=None, tr3=None)
    assert build(User, "tr2") == User(spec="main", tr1=None, tr2="main", tr3=None)
    assert build(User, "tr3") == User(spec="main", tr1=None, tr2=None, tr3="main")

    assert build(User, "derived1", "tr1") == User(spec="derived1", tr1="main", tr2=None, tr3=None)
    assert build(User, "derived1", "tr2") == User(spec="derived1", tr1=None, tr2="derived1", tr3=None)
    assert build(User, "derived1", "tr3") == User(spec="derived1", tr1=None, tr2=None, tr3="main")

    assert build(User, "derived2", "tr1") == User(spec="derived2", tr1="derived2", tr2=None, tr3=None)
    assert build(User, "derived2", "tr2") == User(spec="derived2", tr1=None, tr2="derived1", tr3=None)
    assert build(User, "derived2", "tr3") == User(spec="derived2", tr1=None, tr2=None, tr3="derived2")

    assert build(User, "tr1", "tr2") == User(spec="main", tr1="main", tr2="main", tr3=None)
    assert build(User, "tr2", "tr3") == User(spec="main", tr1=None, tr2="main", tr3="main")

    assert build(User, "derived1", "tr1", "tr2") == User(spec="derived1", tr1="main", tr2="derived1", tr3=None)
    assert build(User, "derived1", "tr2", "tr3") == User(spec="derived1", tr1=None, tr2="derived1", tr3="main")

    assert build(User, "derived2", "tr1", "tr2") == User(spec="derived2", tr1="derived2", tr2="derived1", tr3=None)
    assert build(User, "derived2", "tr2", "tr3") == User(spec="derived2", tr1=None, tr2="derived1", tr3="derived2")


def test_recursion() -> None:
    with define_factory(User) as main:
        with main.derived_factory("derived1") as derived1:
            with derived1.derived_factory("derived2") as derived2:
                derived2.derived_factory("derived3")

        with pytest.raises(DerivationError):
            main.derived_factory("derived2")

        with pytest.raises(DerivationError):
            main.derived_factory("derived3")
