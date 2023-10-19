from dataclasses import dataclass

from genuine import build, build_many, define_factory, Context


@dataclass
class User:
    name: str
    email: str


with define_factory("user", "author", model=User) as user_factory:
    user_factory.set("name", "John")
    user_factory.set("email", computed=lambda name: f"{name}@example.com".lower())


user: User = build("user")
print(user)
