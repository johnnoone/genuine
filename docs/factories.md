# Factories

## Setting values

Factories allow you to define each attributes precisely

### As-is

```python
@dataclass
class User:
    name: str
    age: int
    date_of_birth: date

with define_factory(User) as factory:
    factory.set("name", "John Smith")
```

With this definition, `name` will always be "John Smith".


### Cycle

```python
with define_factory(User) as factory:
    factory.set("name", Cycle(["John Smith", "Bob Advaark"]))
```

With this definition, `name` will alternate cyclically between "John Smith" and "Bob Advaark".


### Computed

```python
with define_factory(User) as factory:
    factory.set("age", Computed(lambda date_of_birth: date.today().year - date_of_birth.year))
```

With this definition, `age` will depends on th cyclically between "John Smith" and "Bob Advaark".


### RandomValues

```python
with define_factory(User) as factory:
    factory.set("name", RandomValues(["John Smith", "Bob Advaark"]))
```

With this definition, `name` will be randomly set to "John Smith" or "Bob Advaark".


## Specialisation

A same model can be defined several times using aliases.

For example, you have a single model Character that is used for different roles:


```python
@dataclass
class Character:
    name: str
    house: Literal["lannister", "stark", "targaryen"]
```

Everytime you need a new character your have to repeat those configurations

```python
build(Character, overrides={"name": "Danaerys", "house": "targaryen"})
build(Character, overrides={"name": "Cersei", "house": "lannister"})
build(Character, overrides={"name": "Eddard", "house": "stark"})
```

It's cumbersome and error-prone.

Aliases allow you to define different factories for the same model, for example:

```python
with define_factory(Character, "targaryen") as factory:
    factory.set("name", RandomValue(["Danaerys", "Rhaegar", "Rhaenyra"]))
    factory.set("house", "targaryen")

with define_factory(Character, "lannister") as factory:
    factory.set("name", RandomValue(["Cersei", "Tyrion", "Tywin"]))
    factory.set("house", "lannister")

with define_factory(Character, "stark") as factory:
    factory.set("name", RandomValue(["Eddard", "Arya", "Sansa"]))
    factory.set("house", "stark")
```

Each factory will produce a consistent object with little configuration:

```python
build((Character, "targaryen"))
build((Character, "lannister"))
build((Character, "stark"))
```


## Singletons

Factories are singletons. Several calls to `define_factory` will return the same instance:

```python
@dataclass
class User:
    given_name: str
    family_name: str
    age: int

with define_factory(User) as factory:
    factory.set("given_name", "John")

with define_factory(User) as factory:
    factory.set("family_name", "Smith")

with define_factory(User) as factory:
    factory.set("age", 45)

assert build(User) == User("John", "Smith", 45)
```
