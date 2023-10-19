from typing import Any
import uuid
from dataclasses import dataclass

from genuine import Context, create, define_factory


@dataclass(kw_only=True)
class User:
    id: uuid.UUID | None = None
    name: str


REPO: Any = {"user_by_ids": {}}


def persist(instance: User, context: Context):
    instance_id = instance.id = instance.id or uuid.uuid4()
    REPO["user_by_ids"][instance_id] = instance


with define_factory("user", model=User, repository=persist) as user_factory:
    user_factory.set("name", "John")


users = [
    create(User, overrides={"name": "John"}),
    create(User, overrides={"name": "Paul"}),
    create(User, overrides={"name": "Ringo"}),
]

print(users)
print(REPO)
