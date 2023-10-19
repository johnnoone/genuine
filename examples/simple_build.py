from dataclasses import dataclass

from genuine import build, build_many, define_factory


@dataclass
class User:
    name: str
    email: str
    age: int
    role: str = "user"


with define_factory("user", "author", model=User) as user_factory:
    user_factory.set("name", "John")
    user_factory.set("age", 21)
    user_factory.set('email', computed=lambda name: f"{name}@example.com".lower())

    with user_factory.trait("admin") as admin_factory:
        admin_factory.set("role", "admin")



user: User = build("user")
print(user)

user = build("author")
print(user)

user = build(User)
print(user)

def refinement(instance, i):
    instance.email = f"user{i}@example.com"
users = build_many(2, "user", overrides={"name": "Daniel"}, refine=refinement)
print(users)

user = build("user", "admin")
print(user)
