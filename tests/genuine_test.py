from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator, cast

import pytest
from pytest_subtests import SubTests

from genuine import (
    FACTORIES,
    Computed,
    Context,
    Cycle,
    FactoryNotFound,
    Overrides,
    Sequence,
    Strategy,
    attributes_for,
    build,
    create,
    create_many,
    define_factory,
)


@dataclass
class User:
    given_name: str
    family_name: str
    admin: bool = False
    email: str | None = None


@dataclass
class Post:
    author: User
    title: str | None = None
    body: str | None = None
    status: str = "idle"


@dataclass
class Comment:
    todo_item: Post | None = None
    commenter: User | None = None
    body: str | None = None


class Missing:
    ...


@pytest.fixture(autouse=True)
def _teardown_fixture() -> Iterator[None]:
    yield
    FACTORIES.clear()


def test_define(subtests: SubTests) -> None:
    with define_factory(User, {"user", "admin"}) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    with subtests.test("with `user` alias"):
        assert build((User, "user")) == User("John", "Doe", False)

    with subtests.test("with `admin` alias"):
        assert build((User, "admin")) == User("John", "Doe", False)

    with subtests.test("with Missing factory"):
        with pytest.raises(FactoryNotFound) as excinfo:
            build(Missing)
        assert excinfo.value.name == (Missing, None)


def test_create() -> None:
    PERSISTED = list()

    def persist(instance: User, context: Context) -> None:
        PERSISTED.append(instance)

    with define_factory(User, storage=persist) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    instance = create(User)
    assert instance in PERSISTED


def test_create_storage() -> None:
    PERSISTED = list()

    def persist(instance: User, context: Context) -> None:
        PERSISTED.append(instance)

    with define_factory(User) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    instance = create(User)
    assert instance not in PERSISTED

    instance = create(User, storage=persist)
    assert instance in PERSISTED


def test_instantiations(subtests: SubTests) -> None:
    with define_factory(User) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    assert build(User) == User("John", "Doe", False)
    assert create(User) == User("John", "Doe", False)
    assert attributes_for(User) == {"given_name": "John", "family_name": "Doe", "admin": False, "email": None}

    with subtests.test("with overrides"):
        assert build(User, overrides={"given_name": "Joe"}).given_name == "Joe"
        assert create(User, overrides={"given_name": "Joe"}).given_name == "Joe"


def test_refinement() -> None:
    with define_factory(User) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    REFINED = []

    def refinement(instance: User) -> None:
        REFINED.append(instance)

    instance = create(User, refine=refinement)
    assert instance in REFINED


def test_transient(subtests: SubTests) -> None:
    with define_factory(User) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

        factory.transient().set("upcased", True)

        @factory.hook("after_build")
        def _(instance: User, context: Context) -> None:
            if context.get("upcased"):
                instance.given_name = instance.given_name.upper()
                instance.family_name = instance.family_name.upper()

    with subtests.test("default behavior"):
        assert create(User).given_name == "JOHN"

    with subtests.test("upcased on"):
        assert create(User, overrides={"upcased": True}).given_name == "JOHN"

    with subtests.test("upcased off"):
        assert create(User, overrides={"upcased": False}).given_name == "John"


class TestAssociations:
    def test_create_with_default_strategy(self, subtests: SubTests) -> None:
        PERSISTED = list()

        def persist(instance: Any, context: Context) -> None:
            PERSISTED.append(instance)

        with define_factory(Post, storage=persist) as factory:
            factory.set("body", None)
            factory.associate("author", (User, "author"))

        with define_factory(User, {"author"}, storage=persist) as factory:
            factory.set("given_name", "John")
            factory.set("family_name", "Doe")
            factory.set("admin", False)

        with subtests.test("all is persisted"):
            post = create(Post, overrides={"body": "foo"})
            assert post in PERSISTED
            assert post.author in PERSISTED

    def test_build_with_default_strategy(self, subtests: SubTests) -> None:
        PERSISTED = list()

        def persist(instance: Any, context: Context) -> None:
            PERSISTED.append(instance)

        with define_factory(Post, storage=persist) as factory:
            factory.set("body", None)
            factory.associate("author", (User, "author"))

        with define_factory(User, {"author"}, storage=persist) as factory:
            factory.set("given_name", "John")
            factory.set("family_name", "Doe")
            factory.set("admin", False)

        with subtests.test("associations are persisted"):
            post = build(Post, overrides={"body": "bar"})
            assert post not in PERSISTED
            assert post.author in PERSISTED

    def test_create_with_create_strategy(self, subtests: SubTests) -> None:
        PERSISTED = list()

        def persist(instance: Any, context: Context) -> None:
            PERSISTED.append(instance)

        with define_factory(Post, storage=persist) as factory:
            factory.set("body", None)
            factory.associate("author", (User, "author"), strategy=Strategy.CREATE)

        with define_factory(User, {"author"}, storage=persist) as factory:
            factory.set("given_name", "John")
            factory.set("family_name", "Doe")
            factory.set("admin", False)

        with subtests.test("all is persisted"):
            post = create(Post, overrides={"body": "foo"})
            assert post in PERSISTED
            assert post.author in PERSISTED

    def test_build_with_create_strategy(self, subtests: SubTests) -> None:
        PERSISTED = list()

        def persist(instance: Any, context: Context) -> None:
            PERSISTED.append(instance)

        with define_factory(Post, storage=persist) as factory:
            factory.set("body", None)
            factory.associate("author", (User, "author"), strategy=Strategy.CREATE)

        with define_factory(User, {"author"}, storage=persist) as factory:
            factory.set("given_name", "John")
            factory.set("family_name", "Doe")
            factory.set("admin", False)

        with subtests.test("associations are persisted"):
            post = build(Post, overrides={"body": "bar"})
            assert post not in PERSISTED
            assert post.author in PERSISTED

    def test_create_with_build_strategy(self, subtests: SubTests) -> None:
        PERSISTED = list()

        def persist(instance: Any, context: Context) -> None:
            PERSISTED.append(instance)

        with define_factory(Post, storage=persist) as factory:
            factory.set("body", None)
            factory.associate("author", (User, "author"), strategy=Strategy.BUILD)

        with define_factory(User, {"author"}, storage=persist) as factory:
            factory.set("given_name", "John")
            factory.set("family_name", "Doe")
            factory.set("admin", False)

        with subtests.test("all is persisted"):
            post = create(Post, overrides={"body": "foo"})
            assert post in PERSISTED
            assert post.author not in PERSISTED

    def test_build_with_build_strategy(self, subtests: SubTests) -> None:
        PERSISTED = list()

        def persist(instance: Any, context: Context) -> None:
            PERSISTED.append(instance)

        with define_factory(Post, storage=persist) as factory:
            factory.set("body", None)
            factory.associate("author", (User, "author"), strategy=Strategy.BUILD)

        with define_factory(User, {"author"}, storage=persist) as factory:
            factory.set("given_name", "John")
            factory.set("family_name", "Doe")
            factory.set("admin", False)

        with subtests.test("associations are persisted"):
            post = build(Post, overrides={"body": "bar"})
            assert post not in PERSISTED
            assert post.author not in PERSISTED


def test_dependant_attributes() -> None:
    with define_factory(User) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set(
            "email", Computed(lambda given_name, family_name: f"{given_name}.{family_name}@example.com".lower())
        )

    assert build(User, overrides={"given_name": "Foo", "family_name": "Bar"}).email == "foo.bar@example.com"
    assert build(User, overrides={"given_name": "Foo", "family_name": "Bar", "email": "🐈@🐈"}).email == "🐈@🐈"


def test_traits() -> None:
    define_factory(Comment)
    with define_factory(Post) as factory:
        factory.set("title", "An awesome post")
        factory.set("body", "Lorem Ipsum...")

        with factory.trait("published") as trait:
            trait.set("status", "published")

        with factory.trait("unpublished") as trait:
            trait.set("status", "draft")

        with factory.trait("with_comments") as trait:

            @trait.hook("after_create")
            def _(instance: Post, _context: Context) -> None:
                create_many(2, Comment, overrides={"todo_item": instance})

    assert create(Post, "published").status == "published"
    assert create(Post, "unpublished").status == "draft"
    assert create(Post, "published", "with_comments").status == "published"


def test_aliases() -> None:
    with define_factory(User, {"author", "commenter"}) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")

    with define_factory(Post) as factory:
        # instead of association :author, factory: :user
        factory.associate("author", (User, "author"))
        factory.set("title", "How to read a book effectively")
        factory.set("body", "There are five steps involved.")

    with define_factory(Comment) as factory:
        # instead of association :commenter, factory: :user
        factory.associate("commenter", (User, "commenter"))
        factory.set("body", "Great article!")

    assert cast(User, create(Comment).commenter).given_name == "John"
    assert cast(User, create(Comment).commenter).family_name == "Doe"


def test_sequence_is_called() -> None:
    sequence = Sequence(lambda n: f"person{n}@example.com")
    with define_factory(User) as factory:
        factory.set("email", sequence)
    assert create(User).email == "person0@example.com"
    assert create(User).email == "person1@example.com"
    assert create(User).email == "person2@example.com"

    assert sequence({}) == "person3@example.com"
    assert sequence({}) == "person4@example.com"
    assert sequence({}) == "person5@example.com"


def test_cycle() -> None:
    # custom cycle
    sequence = Cycle(["a", "b", "c"])
    assert sequence({}) == "a"
    assert sequence({}) == "b"
    assert sequence({}) == "c"
    assert sequence({}) == "a"


def test_sequence() -> None:
    with define_factory(User) as factory:
        factory.set("email", Sequence(lambda n: f"person{n}@example.com"))
    assert create(User).email == "person0@example.com"
    assert create(User).email == "person1@example.com"
    assert create(User).email == "person2@example.com"


def test_dag() -> None:
    @dataclass
    class Anniversary:
        age: int
        date_of_birth: date

    with define_factory(Anniversary) as factory:
        factory.transient().set("ref_date", value=date(2023, 10, 20))
        factory.set("age", Computed(lambda ref_date, date_of_birth: (ref_date - date_of_birth).days // 365))
        factory.set("date_of_birth", value=date(1991, 12, 31))

    assert build(Anniversary) == Anniversary(age=31, date_of_birth=date(1991, 12, 31))


def test_nested() -> None:
    with define_factory(Post) as factory:
        factory.set("body", None)
        factory.associate("author", (User, "author"))

    with define_factory(User, {"author"}) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    assert (
        build(
            Post,
            overrides={
                "body": "hello!",
                "author": Overrides({"given_name": "Steeve"}),
            },
        ).author.given_name
        == "Steeve"
    )


def test_overrides_association_strategy() -> None:
    PERSISTED = list()

    def persist(instance: Any, context: Context) -> None:
        PERSISTED.append(instance)

    with define_factory(Post, storage=persist) as factory:
        factory.set("body", None)
        factory.associate("author", (User, "author"), strategy=Strategy.BUILD)

    with define_factory(User, {"author"}, storage=persist) as factory:
        factory.set("given_name", "John")
        factory.set("family_name", "Doe")
        factory.set("admin", False)

    post = create(Post)
    assert post.author not in PERSISTED

    post = create(Post, overrides={"author": Overrides({}, strategy=Strategy.CREATE)})
    assert post.author in PERSISTED
