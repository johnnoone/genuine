# Genuine

Genuine makes it easy to create test data and associations.
It is inspired by ruby factory-bot.


FactoryBot is a fixtures replacement with a straightforward definition syntax, support for multiple build strategies (saved instances, unsaved instances, attribute hashes, and stubbed objects), and support for multiple factories for the same class (user, admin_user, and so on), including factory inheritance.


## TODO

* [ ] link read me to documentation
* [ ] infer attributes from dataclasses
* [ ] test aliases with traits
* [ ] master random seed
* [ ] Document how to use fake data generator like [faker](https://faker.readthedocs.io) or [mimesis](https://mimesis.name)

## Cookbook

This cookbook is eavily inspired by https://cheatography.com/ash-angell/cheat-sheets/factorybot/ of Ash Angell
### Define factories

```python
from genuine import define_factory


@dataclass
class User:
    given_name: str
    family_name: str
    admin: bool


# Default
# It will use the User class
with define_factory(User) as factory:
    factory.set("given_name", "John")
    factory.set("family_name", "Doe")
    factory.set("admin", False)


# Specialised name
# It will use the name "admin" on the User class
with define_factory(User, {"admin"}) as factory:
    factory.set("given_name", "Admin")
    factory.set("family_name", "User")
    factory.set("admin", True)
```

### Building factories

```python
from genuine import build, create, attributes_for


# Returns an User instance that's not saved
user = build(User)

# Returns a saved User instance
user = create(User)

# Returns a hash of attributes that can be used to build an User instance
attrs = attributes_for(User)

# Passing a refinement to any of the methods above will yield the return object
def refinement(instance: User):
    Post.create(attributes_for("post", author=instance))

create(User, refine=refinement)

# Overriding attributes of a factory
user = build(User, overrides={"first_name": "Joe"})
user.first_name
# => "Joe"

# No matter which build strategy is used to override attributes
user = create(User, overrides={"first_name": "Joe"})
user.first_name
# => "Joe"
```


### Options (trans­ients)

```python
with define_factory(User) as factory:
    with factory.transient() as transient:
        transient.set("upcased", True)

    @factory.hook("after_build")
    def _(instance: User, context: Context):
        if context.get("upcased"):
            instance.name = instance.name.upper()

create(User, overrides={"upcased": True})
```

Transient attributes will not get passed to the model, but will be available in **after_build** hooks.


### Nested Factories

```python
with define_factory(User) as factory:
    factory.set("first_name", "John")

    with factory.sub_factory("sample_user") as sub:
        sub.set("first_name", Computed(lambda: Faker.first_name()))

create((User, "sample_user"))
```


### Associ­ations

```python
with define_factory(Post) as factory:
    factory.associate("author", User)


# You can also override attributes
with define_factory(Post) as factory:
    factory.associate("author", User, overrides={"family_name": "Writely"})


# Builds and saves a User and a Post
post = create(Post)
is_new_record(post)        # => False
is_new_record(post.author) # => False

# Builds and saves a User, and then builds but does not save a Post
post = build(Post)
is_new_record(post)        # => True
is_new_record(post.author) # => False
```

### Dependent attributes

```python
from genuine import Computed

with define_factory(=User) as factory:
    factory.set("given_name", "John")
    factory.set("family_name", "Blow")
    factory.set('email', Computed(lambda given_name, family_name: f"{given_name}.{family_name}@example.com".lower()))
```

Attributes can be based on the values of other attrib­utes.


### Traits

```python
with define_factory(Post) as factory:
    factory.set("title", "An awesome post")
    factory.set("body", "Lorem Ipsum...")

    with factory.trait("published") as trait:
        trait.set("status", "published")

    with factory.trait("unpublished") as trait:
        trait.set("status", "draft")

    with factory.trait("with_comments") as trait:
        @trait.hook("after_create")
        def _(instance: Post, context: Context):
            create_many(2, "comment", overrides={"todo_item": instance})

# then in your test
post = create("post", "published")

# or even with
post = create("post", "published", "with_comments")
```

Trait helps you to remove duplic­ation.


### Aliases

```python
with define_factory(User, {"author", "commenter"}) as factory:
    factory.set("given_name", "John")
    factory.set("family_name", "Doe" )
    factory.set("date_of_birth", Computed(lambda: date.today() - timedelta(days=365 * 18)))

with define_factory(Post) as factory:
    factory.associate("author", (User, "author"))
    factory.set("title", "How to read a book effectively")
    factory.set("body", "There are five steps involved.")

with define_factory(Comment) as factory:
    factory.associate("commenter", (User, "commenter"))
    factory.set("body", "Great article!")

```

Aliases allow to use named associ­ations more easily.


## Overriding attributes

```python
override={"name": "John"}
override={"name": Cycle("John", "Dave")}
override={"author": Overrides({"name": "John"})}
```
