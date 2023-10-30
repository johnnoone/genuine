from random import Random
from typing import Any

random = Random()


def reseed(new_seed: Any) -> None:
    random.seed(new_seed)
