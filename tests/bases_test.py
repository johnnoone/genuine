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
    Genuine,
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


@pytest.fixture(name="gen")
def gen_fixture() -> Genuine:
    return Genuine()


def test_defined(gen: Genuine) -> None:
    assert not gen.factories

    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)

    assert gen.factories


def test_attributes_for(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)

    assert gen.attributes_for(User) == {"name": "Billy Pangolin", "email": None}


def test_value(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)

    instance = gen.build(User)
    assert instance == User("Billy Pangolin")


def test_computed(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", Computed(lambda: "Billy Pangolin"))
        factory.set("email", None)

    instance = gen.build(User)
    assert instance == User("Billy Pangolin")


def test_computed_dependencies(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", Computed(lambda name: f"{name}@example.com"))

    instance = gen.build(User)
    assert instance == User("Billy Pangolin", email="Billy Pangolin@example.com")


def test_value_overrides(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)

    instance = gen.build(User, overrides={"name": "Mickey Mouse"})
    assert instance == User("Mickey Mouse")


def test_transient(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", Computed(lambda upcased: "JOHN SMITH" if upcased else "Billy Pangolin"))
        factory.set("email", None)
        factory.transient().set("upcased", True)

    assert gen.build(User) == User("JOHN SMITH")
    assert gen.build(User, overrides={"upcased": False}) == User("Billy Pangolin")


def test_trait(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)
        with factory.trait("fbi") as trait:
            trait.set("email", "john.smith@fbi.com")

    assert gen.build(User) == User("Billy Pangolin")
    assert gen.build(User, "fbi") == User("Billy Pangolin", email="john.smith@fbi.com")


def test_trait_with_hooks(gen: Genuine) -> None:
    PERSISTED = []

    def persist(instance: Any, context: Any) -> None:
        PERSISTED.append(instance)

    gen.define_factory(Comment, storage=persist)
    with gen.define_factory(Post) as factory:
        factory.set("title", "An awesome post")

        with factory.trait("published") as trait:
            trait.set("status", "published")

        with factory.trait("unpublished") as trait:
            trait.set("status", "draft")

        with factory.trait("with_comments") as trait:
            trait.add_hook(
                "after_create",
                lambda instance, _context: gen.create_many(2, Comment, overrides={"post": instance}),
            )
    assert gen.create(Post, "published").status == "published"
    assert not PERSISTED

    assert gen.create(Post, "unpublished").status == "draft"
    assert not PERSISTED

    assert gen.create(Post, "published", "with_comments").status == "published"
    assert PERSISTED


def test_trait_transient(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", Computed(lambda upcased: "JOHN SMITH" if upcased else "Billy Pangolin"))
        factory.set("email", None)
        factory.transient().set("upcased", True)

        with factory.trait("fbi") as trait:
            trait.set("email", "john.smith@fbi.com")
            trait.transient().set("upcased", False)

    assert gen.build(User) == User("JOHN SMITH")
    assert gen.build(User, "fbi") == User("Billy Pangolin", email="john.smith@fbi.com")
    assert gen.build(User, "fbi", overrides={"upcased": True}) == User("JOHN SMITH", email="john.smith@fbi.com")


def test_aliases(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)

    instance = gen.build(User)
    assert instance == User("Billy Pangolin")

    instance = gen.build((User, "author"))
    assert instance == User("Billy Pangolin")


def test_associations(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)

    with gen.define_factory(Comment) as factory:
        factory.associate("author", name=(User, "author"))

    instance: Comment = gen.build(Comment)
    assert instance.author == User("Billy Pangolin")

    # override
    instance = gen.build(Comment, overrides={"author": Overrides({"name": "Dave"})})
    assert instance.author == User("Dave")

    # replacement
    instance = gen.build(Comment, overrides={"author": {"name": "Dave"}})
    assert cast(dict[str, Any], instance.author) == {"name": "Dave"}


def test_many(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)
    assert gen.build_many(3, User) == [User("Billy Pangolin"), User("Billy Pangolin"), User("Billy Pangolin")]
    assert gen.build_many(3, User, overrides={"name": Cycle(["foo", "bar"])}) == [
        User("foo"),
        User("bar"),
        User("foo"),
    ]


def test_computed_cycle(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", Cycle(["John", "Dave"]))
        factory.set("email", None)
    assert gen.build(User) == User("John")
    assert gen.build(User) == User("Dave")
    assert gen.build(User) == User("John")


def test_computed_cycle_in_overrides(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.set("email", None)
    assert gen.build_many(3, User, overrides={"name": Cycle(["John", "Dave"])}) == [
        User(name="John"),
        User(name="Dave"),
        User(name="John"),
    ]


def test_computed_sequence(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Dave")
        factory.set("email", Sequence(lambda i, name: f"{name.lower()}.{i}@example.com"))
    assert gen.build(User) == User("Dave", email="dave.0@example.com")
    assert gen.build(User) == User("Dave", email="dave.1@example.com")
    assert gen.build(User) == User("Dave", email="dave.2@example.com")


def test_computed_sequence_in_overrides(gen: Genuine) -> None:
    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "Dave")
        factory.set("email", None)

    assert gen.build_many(2, User, overrides={"email": Sequence(lambda i, name: f"{name}.{i}.xx")}) == [
        User(name="Dave", email="Dave.0.xx"),
        User(name="Dave", email="Dave.1.xx"),
    ]


def test_sub_factory_inner(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)
        factory.sub_factory("admin").set("email", "admin@example.com")

    assert gen.build(User) == User("Billy Pangolin")
    assert gen.build((User, "admin")) == User(name="Billy Pangolin", email="admin@example.com")


def test_sub_factory_sibling(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("name", "Billy Pangolin")
        factory.set("email", None)
    with gen.sub_factory(User, "admin") as factory:
        factory.set("email", "admin@example.com")

    assert gen.build(User) == User("Billy Pangolin")
    assert gen.build((User, "admin")) == User(name="Billy Pangolin", email="admin@example.com")


def test_refinement(gen: Genuine) -> None:
    def refinement(x: User) -> None:
        x.name = x.name + x.name

    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.set("email", None)
    assert gen.build(User, refine=refinement) == User("JohnJohn")


def test_build_hooks(gen: Genuine) -> None:
    LOGS = []

    def hook(instance: Any, context: Any, pos: Any) -> None:
        LOGS.append((pos, instance, context))

    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.set("email", None)
        factory.transient().set("foo", "bar")
        factory.add_hook("after_build", partial(hook, pos="after_build"))
        factory.add_hook("before_create", partial(hook, pos="before_create"))
        factory.add_hook("after_create", partial(hook, pos="after_create"))
    gen.build(User)
    assert LOGS == [("after_build", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"})]


def test_create_hooks(gen: Genuine) -> None:
    LOGS = []

    def hook(instance: Any, context: Any, pos: Any) -> None:
        LOGS.append((pos, instance, context))

    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.set("email", None)
        factory.transient().set("foo", "bar")
        factory.add_hook("after_build", partial(hook, pos="after_build"))
        factory.add_hook("before_create", partial(hook, pos="before_create"))
        factory.add_hook("after_create", partial(hook, pos="after_create"))
    gen.create(User)
    assert LOGS == [
        ("after_build", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
        ("before_create", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
        ("after_create", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
    ]


def test_build_traits_hooks(gen: Genuine) -> None:
    LOGS = []

    def hook(instance: Any, context: Any, pos: Any) -> None:
        LOGS.append((pos, instance, context))

    with gen.define_factory(User, {"author", None}) as factory:
        factory.set("name", "John")
        factory.set("email", None)
        factory.transient().set("foo", "bar")
        factory.add_hook("after_build", partial(hook, pos="after_build main"))
        factory.add_hook("before_create", partial(hook, pos="before_create main"))
        factory.add_hook("after_create", partial(hook, pos="after_create main"))

        with factory.trait("admin") as trait:
            trait.add_hook("after_build", partial(hook, pos="after_build trait"))
            trait.add_hook("before_create", partial(hook, pos="before_create trait"))
            trait.add_hook("after_create", partial(hook, pos="after_create trait"))
    gen.build(User)
    assert LOGS == [("after_build main", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"})]
    LOGS.clear()

    gen.build(User, "admin")
    assert LOGS == [
        ("after_build main", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
        ("after_build trait", User(name="John", email=None), {"name": "John", "email": None, "foo": "bar"}),
    ]
    LOGS.clear()


def test_persist(gen: Genuine) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with gen.define_factory(User, {"author", None}, storage=persist) as factory:
        factory.set("name", "John")

    instance = gen.build(User)
    assert instance not in SAVED

    instance = gen.create(User)
    assert instance in SAVED


def test_persist_sub_defaults_to_parent(gen: Genuine) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with gen.define_factory(User, storage=persist) as factory:
        factory.set("name", "John")

        with factory.sub_factory("admin") as sub:
            sub.set("email", "admin")

    instance = gen.build((User, "admin"))
    assert instance not in SAVED

    instance = gen.create((User, "admin"))
    assert instance in SAVED


def test_persist_sub_defines_its_persistance(gen: Genuine) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with gen.define_factory(User) as factory:
        factory.set("name", "John")

        with factory.sub_factory("admin", storage=persist) as sub:
            sub.set("email", "admin")

    instance = gen.create(User)
    assert instance not in SAVED

    instance = gen.build((User, "admin"))
    assert instance not in SAVED

    instance = gen.create((User, "admin"))
    assert instance in SAVED


def test_persist_associations_default_strategy(gen: Genuine) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with gen.define_factory(User, storage=persist) as factory:
        factory.set("name", "Billy Pangolin")

    with gen.define_factory(Comment, storage=persist) as factory:
        factory.associate("author", User)

    instance: Comment = gen.build(Comment)
    assert instance not in SAVED
    assert instance.author in SAVED


def test_persist_associations_force_build_strategy(gen: Genuine) -> None:
    SAVED = []

    def persist(instance: Any, context: Any) -> None:
        SAVED.append(instance)

    with gen.define_factory(User, storage=persist) as factory:
        factory.set("name", "Billy Pangolin")

    with gen.define_factory(Comment, storage=persist) as factory:
        factory.associate("author", User, strategy=Strategy.BUILD)

    instance: Comment = gen.create(Comment)
    assert instance in SAVED
    assert instance.author not in SAVED


def test_dependant_attributes(gen: Genuine) -> None:
    with gen.define_factory(User) as factory:
        factory.set("email", Computed(lambda name: f"{name.replace(' ', '.')}@example.com".lower()))
        factory.set("name", "John Doe")

    assert gen.build(User, overrides={"name": "Foo Bar"}).email == "foo.bar@example.com"
    assert gen.build(User, overrides={"name": "Foo Bar", "email": "🐈@🐈"}).email == "🐈@🐈"


def test_dag(gen: Genuine) -> None:
    @dataclass
    class Anniversary:
        age: int
        date_of_birth: date

    with gen.define_factory(Anniversary) as factory:
        with factory.transient() as transient:
            transient.set("ref_date", value=date(2023, 10, 20))
        factory.set("age", Computed(lambda ref_date, date_of_birth: (ref_date - date_of_birth).days // 365))
        factory.set("date_of_birth", value=date(1991, 12, 31))

    assert gen.build(Anniversary) == Anniversary(age=31, date_of_birth=date(1991, 12, 31))


def test_cyclic_dependencies(gen: Genuine) -> None:
    @dataclass
    class Anniversary:
        age: int
        date_of_birth: date

    with gen.define_factory(Anniversary) as factory:
        factory.set("age", Computed(lambda date_of_birth: 21))
        factory.set("date_of_birth", Computed(lambda age: date(1991, 12, 31)))

    with pytest.raises(CyclicDependencies) as excinfo:
        assert gen.build(Anniversary)
    assert excinfo.value.dependencies == {"age": {"date_of_birth"}, "date_of_birth": {"age"}}
