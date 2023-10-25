# Genuine

Genuine makes it easy to create test data and associations.
It is inspired by ruby factory-bot.


It has a straightforward definition syntax, support for multiple build strategies (saved instances, unsaved instances, and attribute mappings), and support for multiple factories for the same class.


## Installation

```
pip install genuine
```

## Usage

```python
from genuine import build
from dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int
    admin: bool = False

instance = build(User)
assert isinstance(instance, User)
```

With a factory

```python
from genuine import define_factory

with define_factory(User) as factory:
    factory.set("name", "John")

instance = build(User)
assert instance.name == "John"
```

Nested model objects

```python
@dataclass
class Comment:
    body: str
    commenter: User


with define_factory(Comment) as factory:
    factory.set("body", "awesome")
    factory.association("commenter", User)

assert build(Comment).commenter.name == "John"
```


## Doc

more example are located here https://johnnoone.github.io/genuine/
