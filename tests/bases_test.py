from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any, cast

import pytest

from genuine.bases import (
    Computed,
    Cycle,
    CyclicDependencies,
    FactoryBot,
    Overrides,
    Sequence,
    Strategy,
)


@dataclass
class User:
    name: str
    email: str | None = None


@dataclass
class Comment:
    author: User
    post: Post | None = None


@dataclass
class Post:
    author: User
    title: str
    status: str


@pytest.fixture(name="fb")
def fb_fixture() -> FactoryBot:
    return FactoryBot()


def test_defined(fb: FactoryBot) -> None:
    assert not fb.factories

    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")

    assert fb.factories


def test_attributes_for(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")

    assert fb.attributes_for(User) == {"name": "John Smith", "email": None}


def test_value(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")

    instance = fb.build(User)
    assert instance == User("John Smith")


def test_computed(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", Computed(lambda: "John Smith"))

    instance = fb.build(User)
    assert instance == User("John Smith")


def test_computed_dependencies(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")
        factory.set("email", Computed(lambda name: f"{name}@example.com"))

    instance = fb.build(User)
    assert instance == User("John Smith", email="John Smith@example.com")


def test_value_overrides(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")

    instance = fb.build(User, overrides={"name": "Mickey Mouse"})
    assert instance == User("Mickey Mouse")


def test_transient(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", Computed(lambda upcased: "JOHN SMITH" if upcased else "John Smith"))
        factory.transient().set("upcased", True)

    assert fb.build(User) == User("JOHN SMITH")
    assert fb.build(User, overrides={"upcased": False}) == User("John Smith")


def test_trait(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")
        with factory.trait("fbi") as trait:
            trait.set("email", "john.smith@fbi.com")

    assert fb.build(User) == User("John Smith")
    assert fb.build(User, "fbi") == User("John Smith", email="john.smith@fbi.com")


def test_trait_with_hooks(fb: FactoryBot) -> None:
    PERSISTED = []

    def persist(instance: Any, context: Any) -> None:
        PERSISTED.append(instance)

    fb.define_factory(Comment, storage=persist)
    with fb.define_factory(Post) as factory:
        factory.set("title", "An awesome post")

        with factory.trait("published") as trait:
            trait.set("status", "published")

        with factory.trait("unpublished") as trait:
            trait.set("status", "draft")

        with factory.trait("with_comments") as trait:
            trait.add_hook(
                "after_create",
                lambda instance, _context: fb.create_many(2, Comment, overrides={"post": instance}),
            )
    assert fb.create(Post, "published").status == "published"
    assert not PERSISTED

    assert fb.create(Post, "unpublished").status == "draft"
    assert not PERSISTED

    assert fb.create(Post, "published", "with_comments").status == "published"
    assert PERSISTED


def test_trait_transient(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", Computed(lambda upcased: "JOHN SMITH" if upcased else "John Smith"))
        factory.transient().set("upcased", True)

        with factory.trait("fbi") as trait:
            trait.set("email", "john.smith@fbi.com")
            trait.transient().set("upcased", False)

    assert fb.build(User) == User("JOHN SMITH")
    assert fb.build(User, "fbi") == User("John Smith", email="john.smith@fbi.com")
    assert fb.build(User, "fbi", overrides={"upcased": True}) == User("JOHN SMITH", email="john.smith@fbi.com")


def test_aliases(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John Smith")

    instance = fb.build(User)
    assert instance == User("John Smith")

    instance = fb.build((User, "author"))
    assert instance == User("John Smith")


def test_associations(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John Smith")

    with fb.define_factory(Comment) as factory:
        factory.associate("author", name=(User, "author"))

    instance: Comment = fb.build(Comment)
    assert instance.author == User("John Smith")

    # override
    instance = fb.build(Comment, overrides={"author": Overrides({"name": "Dave"})})
    assert instance.author == User("Dave")

    # replacement
    instance = fb.build(Comment, overrides={"author": {"name": "Dave"}})
    assert cast(dict[str, Any], instance.author) == {"name": "Dave"}


def test_many(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John Smith")
    assert fb.build_many(3, User) == [User("John Smith"), User("John Smith"), User("John Smith")]
    assert fb.build_many(3, User, overrides={"name": Cycle(["foo", "bar"])}) == [
        User("foo"),
        User("bar"),
        User("foo"),
    ]


def test_computed_cycle(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", Cycle(["John", "Dave"]))
    assert fb.build(User) == User("John")
    assert fb.build(User) == User("Dave")
    assert fb.build(User) == User("John")


def test_computed_cycle_in_overrides(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
    assert fb.build_many(3, User, overrides={"name": Cycle(["John", "Dave"])}) == [
        User(name="John"),
        User(name="Dave"),
        User(name="John"),
    ]


def test_computed_sequence(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Dave")
        factory.set("email", Sequence(lambda i, name: f"{name.lower()}.{i}@example.com"))
    assert fb.build(User) == User("Dave", email="dave.0@example.com")
    assert fb.build(User) == User("Dave", email="dave.1@example.com")
    assert fb.build(User) == User("Dave", email="dave.2@example.com")


def test_computed_sequence_in_overrides(fb: FactoryBot) -> None:
    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Dave")

    assert fb.build_many(2, User, overrides={"email": Sequence(lambda i, name: f"{name}.{i}.xx")}) == [
        User(name="Dave", email="Dave.0.xx"),
        User(name="Dave", email="Dave.1.xx"),
    ]


def test_sub_factory_inner(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")
        factory.sub_factory("admin").set("email", "admin@example.com")

    assert fb.build(User) == User("John Smith")
    assert fb.build((User, "admin")) == User(name="John Smith", email="admin@example.com")


def test_sub_factory_sibling(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("name", "John Smith")
    with fb.sub_factory(User, "admin") as factory:
        factory.set("email", "admin@example.com")

    assert fb.build(User) == User("John Smith")
    assert fb.build((User, "admin")) == User(name="John Smith", email="admin@example.com")


def test_refinement(fb: FactoryBot) -> None:
    def refinement(x: User) -> None:
        x.name = x.name + x.name

    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
    assert fb.build(User, refine=refinement) == User("JohnJohn")


def test_build_hooks(fb: FactoryBot) -> None:
    LOGS = []

    def hook(instance: Any, context: Any, pos: Any) -> None:
        LOGS.append((pos, instance, context))

    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.transient().set("foo", "bar")
        factory.add_hook("after_build", partial(hook, pos="after_build"))
        factory.add_hook("before_create", partial(hook, pos="before_create"))
        factory.add_hook("after_create", partial(hook, pos="after_create"))
    fb.build(User)
    assert LOGS == [("after_build", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"})]


def test_create_hooks(fb: FactoryBot) -> None:
    LOGS = []

    def hook(instance: Any, context: Any, pos: Any) -> None:
        LOGS.append((pos, instance, context))

    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.transient().set("foo", "bar")
        factory.add_hook("after_build", partial(hook, pos="after_build"))
        factory.add_hook("before_create", partial(hook, pos="before_create"))
        factory.add_hook("after_create", partial(hook, pos="after_create"))
    fb.create(User)
    assert LOGS == [
        ("after_build", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
        ("before_create", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
        ("after_create", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
    ]


def test_build_traits_hooks(fb: FactoryBot) -> None:
    LOGS = []

    def hook(instance: Any, context: Any, pos: Any) -> None:
        LOGS.append((pos, instance, context))

    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.transient().set("foo", "bar")
        factory.add_hook("after_build", partial(hook, pos="after_build main"))
        factory.add_hook("before_create", partial(hook, pos="before_create main"))
        factory.add_hook("after_create", partial(hook, pos="after_create main"))

        with factory.trait("admin") as trait:
            trait.add_hook("after_build", partial(hook, pos="after_build trait"))
            trait.add_hook("before_create", partial(hook, pos="before_create trait"))
            trait.add_hook("after_create", partial(hook, pos="after_create trait"))
    fb.build(User)
    assert LOGS == [("after_build main", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"})]
    LOGS.clear()

    fb.build(User, "admin")
    assert LOGS == [
        ("after_build main", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
        ("after_build trait", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
    ]
    LOGS.clear()


def test_persist(fb: FactoryBot) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with fb.define_factory(User, {"author", None}, storage=persist) as factory:
        factory.set("name", "John")

    instance = fb.build(User)
    assert instance not in SAVED

    instance = fb.create(User)
    assert instance in SAVED


def test_persist_sub_defaults_to_parent(fb: FactoryBot) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with fb.define_factory(User, {"author", None}, storage=persist) as factory:
        factory.set("name", "John")

        with factory.sub_factory("admin") as sub:
            sub.set("email", "admin")

    instance = fb.build((User, "admin"))
    assert instance not in SAVED

    instance = fb.create((User, "admin"))
    assert instance in SAVED


def test_persist_sub_defines_its_persistance(fb: FactoryBot) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with fb.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")

        with factory.sub_factory("admin", storage=persist) as sub:
            sub.set("email", "admin")

    instance = fb.create(User)
    assert instance not in SAVED

    instance = fb.build((User, "admin"))
    assert instance not in SAVED

    instance = fb.create((User, "admin"))
    assert instance in SAVED


def test_persist_associations_default_strategy(fb: FactoryBot) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with fb.define_factory(User, storage=persist) as factory:
        factory.set("name", "John Smith")

    with fb.define_factory(Comment, storage=persist) as factory:
        factory.associate("author", User)

    instance: Comment = fb.build(Comment)
    assert instance not in SAVED
    assert instance.author in SAVED


def test_persist_associations_force_build_strategy(fb: FactoryBot) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with fb.define_factory(User, storage=persist) as factory:
        factory.set("name", "John Smith")

    with fb.define_factory(Comment, storage=persist) as factory:
        factory.associate("author", User, strategy=Strategy.BUILD)

    instance: Comment = fb.create(Comment)
    assert instance in SAVED
    assert instance.author not in SAVED


def test_dependant_attributes(fb: FactoryBot) -> None:
    with fb.define_factory(User) as factory:
        factory.set("email", Computed(lambda name: f"{name.replace(' ', '.')}@example.com".lower()))
        factory.set("name", "John Doe")

    assert fb.build(User, overrides={"name": "Foo Bar"}).email == "foo.bar@example.com"
    assert fb.build(User, overrides={"name": "Foo Bar", "email": "🐈@🐈"}).email == "🐈@🐈"


def test_dag(fb: FactoryBot) -> None:
    @dataclass
    class Anniversary:
        age: int
        date_of_birth: date

    with fb.define_factory(Anniversary) as factory:
        with factory.transient() as transient:
            transient.set("ref_date", value=date(2023, 10, 20))
        factory.set("age", Computed(lambda ref_date, date_of_birth: (ref_date - date_of_birth).days // 365))
        factory.set("date_of_birth", value=date(1991, 12, 31))

    assert fb.build(Anniversary) == Anniversary(age=31, date_of_birth=date(1991, 12, 31))


def test_cyclic_dependencies(fb: FactoryBot) -> None:
    @dataclass
    class Anniversary:
        age: int
        date_of_birth: date

    with fb.define_factory(Anniversary) as factory:
        factory.set("age", Computed(lambda date_of_birth: 21))
        factory.set("date_of_birth", Computed(lambda age: date(1991, 12, 31)))

    with pytest.raises(CyclicDependencies) as excinfo:
        assert fb.build(Anniversary)
    assert excinfo.value.dependencies == {"age": {"date_of_birth"}, "date_of_birth": {"age"}}
