from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from genuine import Lookup, Overrides, Sequence, build, define_factory
from genuine.values import Computed


@dataclass
class User:
    id: int
    name: str
    profile: Profile | None


@dataclass
class Profile:
    user_id: int
    spirit_animal: str | None = None
    bio: str | None = None


@dataclass
class Comment:
    message: str
    commenter: User


def test_uncorrelated_assoc_evaluation() -> None:
    seq: Sequence[int]
    seq = Sequence()

    with define_factory(User) as factory:
        factory.set("id", seq)
        factory.set("name", "Gary Kangaroo")
        factory.associate("profile", Profile)

    with define_factory(Comment) as factory:
        factory.set("message", "cricri")
        factory.associate("commenter", User)

    with define_factory(Profile) as factory:
        factory.set("user_id", seq)
        factory.set("spirit_animal", None)

    comment = build(Comment)
    assert comment.commenter.name == "Gary Kangaroo"
    assert cast(Profile, comment.commenter.profile).spirit_animal is None
    assert comment.commenter.id != cast(Profile, comment.commenter.profile).user_id

    comment = build(
        Comment,
        overrides={
            "commenter": Overrides(
                {
                    "name": "Cassy Merkat",
                    "profile": Overrides(
                        {
                            "user_id": Lookup(".id"),  # <-- correlation
                            "spirit_animal": "🦒",
                        }
                    ),
                }
            )
        },
    )
    assert comment.commenter.name == "Cassy Merkat"
    assert cast(Profile, comment.commenter.profile).spirit_animal == "🦒"
    assert comment.commenter.id == cast(Profile, comment.commenter.profile).user_id


def test_corelated_assoc_evaluation() -> None:
    seq: Sequence[int]
    seq = Sequence()

    with define_factory(User) as factory:
        factory.set("id", seq)
        factory.set("name", "Gary Kangaroo")
        factory.associate(
            "profile",
            Profile,
            overrides={
                "user_id": Lookup(".id"),  # <-- correlation
                "spirit_animal": "🦒",
            },
        )

    with define_factory(Comment) as factory:
        factory.set("message", "cricri")
        factory.associate("commenter", User, overrides={"name": "Cassy Merkat"})

    with define_factory(Profile) as factory:
        factory.set("user_id", seq)
        factory.set("spirit_animal", None)

    comment = build(Comment)
    assert comment.commenter.name == "Cassy Merkat"
    assert cast(Profile, comment.commenter.profile).spirit_animal == "🦒"
    assert comment.commenter.id == cast(Profile, comment.commenter.profile).user_id
