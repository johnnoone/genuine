from dataclasses import dataclass
from genuine.bases import Genuine


@dataclass
class User:
    given_name: str
    family_name: str
    age: int


def test_singleton(gen: Genuine) -> None:
    """define_factory is like logging.getLogger, instance is a singleton."""
    with gen.define_factory(User) as factory:
        factory.set("given_name", "John")

    with gen.define_factory(User) as factory:
        factory.set("family_name", "Smith")

    with gen.define_factory(User) as factory:
        factory.set("age", 45)

    user = gen.build(User)
    assert user == User("John", "Smith", 45)
