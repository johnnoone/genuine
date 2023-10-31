# A tour of genuine

Genuine is a fixture generator for model object inspired by [ruby factory_bot](https://thoughtbot.github.io/factory_bot/) and [elixir ex_machina](https://hexdocs.pm/ex_machina/ExMachina.html).

It makes it easy to create test data and associations for [dataclasses](https://docs.python.org/3/library/dataclasses.html). Install genuine and then you will be able to use it without configuration:

```python hl_lines="2 10"
from dataclasses import dataclass
from genuine import build

@dataclass
class User:
    name: str
    age: int
    admin: bool = False

user = build(User)
assert isinstance(user, User)
```

You can also generate a list of objects

```python hl_lines="3"
from genuine import build_many

users = build_many(2, User)
assert len(users) == 2
```

In these examples, `name` and `age` are auto generated, infered from object annotations.
Will it is the default behavior, rendered values can be overriten:

```python
user = build(User, overrides={"name": "John"})
assert user.name == "John"
```

But it doesn't seem natural that all objects have the same name, does it?
You can some smart randomness to this attribute.

For example you can use the Cycle helper that will return a value cyclicly:

```python
from genuine import Cycle

users = build_many(3, User, overrides={"name": Cycle(["John", "Dave"])})
assert users[0].name == "John"
assert users[1].name == "Dave"
assert users[2].name == "John"
```

Or use an fixture library like [faker](https://faker.readthedocs.io) or [mimesis](https://mimesis.name) that will make it smoothly for you:

```python
from mimesis import Generic
from genuine import Computed

g = Generic()

name_generator = Computed(lambda: g.person.name())
users = build_many(3, User, overrides={"name": name_generator})
assert user[0].name != user[1].name != user[2].name
```


## Persist data

Often you want to persist your model object somewhere. This is where the `create` and `create_many` helpers come from.

```python
from genuine import create, Context

PERSISTED = []

def persist(instance: User, context: Context):
    PERSISTED.append(instance)

user = create(User, storage=persist)
assert user in PERSISTED
```


## Factories

OK, we saw that `overrides` let you fine tune the value of attributes. but it's long and tiring to always include it, especially when you always want the same thing.

This is why you can define factories to teach genuine what plausible values it should use to build instances.

For example, those 2 scenarios have the same result:

```python
name_generator = Cycle(["John", "Dave"])
user = build(User, overrides={"name": name_generator})
user = build(User, overrides={"name": name_generator})
user = build(User, overrides={"name": name_generator})
user = build(User, overrides={"name": name_generator})
```

```python
from genuine import define_factory

with define_factory(User) as factory:
    factory.set("name", Cycle(["John", "Dave"]))

user = build(User)
user = build(User)
user = build(User)
user = build(User)
```

Defining factories allows you to reuse them everywhere in your tests.

But that's not all. instances sometimes have to be like this or like that.
Factories allow you to also define different `traits` for the same model object:

```python
with define_factory(User) as factory:
    factory.set("name", name_generator)
    with factory.trait("regular") as trait:
        trait.set("admin", False)
    with factory.trait("admin") as trait:
        trait.set("admin", True)

assert build(User, "regular").admin is False
assert build(User, "admin").admin is True
```

Traits are a mechanism when there is little things that change.

You can also define derived factories using `derived_factory`, for example:

```python
with define_factory(User) as main:
    main.set("name", name_generator)
    main.set("admin", False)

    with main.derived_factory("admin") as derived:
        derived.set("admin", True)

assert build(User).admin is False
assert build((User, "admin")).admin is True
```

Finally you are able to define specialized factories for the same model:

```python
with define_factory(User) as factory:
    ...

with define_factory(User, "admin") as factory:
    ...

assert build(User).admin is False
assert build((User, "admin")).admin is True
```


## Context and transient

Factories let you declare some context data that will help you to fine tune you instances.

Let's say sometime you need to uppercase name:

```python
with define_factory(User) as factory:
    factory.set("name", Computed(lambda uppercased: "BIG JOHN" if uppercased else "Regular John"))
    with factory.transient() as transient:
        transient.set("uppercased", False)

assert build(User).name == "Regular John"
assert build(User, overrides={"uppercased": True}).name== "BIG JOHN"
```

Those instance attributes and transient data are passed into `Context` object.
This object will help you to define complexe scenarios. It is exposed into helper functions like persist, hooks and refinement.

For example, the previous factory will generate those Context:

```python
build(User, overrides={"uppercased": False})  # --> Context({"name": "Regular John", "uppercased": False})
build(User, overrides={"uppercased": True})  # --> Context({"name": "Regular John", "uppercased": True})
```

## Nested model objects

Comment have commenter, right? This is what we call a sub object.

With factory bot, those objects can be declared easily to, with associations:

```python

@dataclass
class Comment:
    commenter: Author


with define_factory(Comment) as factory:
    factory.associate("commenter", User)

commenter = build(Comment).commenter
assert isinstance(commenter, User)
```

You can override nested objects too:

```python
comment = build(Comment, override={"commenter": Overrides({"name": "Mickey"})})
assert comment.commenter.name == "Mickey"
```

Note that by default, nested objects are always created. This behavior can be configured within association, or with Overrides object.

```python
with define_factory(Comment) as factory:
    factory.associate("commenter", User, strategy=Strategy.BUILD)
```

```python
build(Comment, overrides={"commenter": Overrides(strategy=Strategy.BUILD)})
```

## Hooks and refinement

You can declare some hooks that will be applied during the construction of the object.

```python
with define_factory(User) as factory:
    @factory.hook("after_build")
    def _(instance: User, context: Context):
        print("called after_build")

    @factory.hook("before_create")
    def _(instance: User, context: Context):
        print("called before_create")

    @factory.hook("after_create")
    def _(instance: User, context: Context):
        print("called after_create")

create(User)
# prints
# called after_build
# called before_create
# called after_create
```

And you can define a refinement function at the end of the function

```python
build(User, refine=lambda instance, context: print("called refine"))
```
