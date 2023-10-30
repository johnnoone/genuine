from __future__ import annotations

from random import Random

import pytest

from genuine.bases import Genuine
from genuine.random import random


@pytest.fixture(name="gen")
def gen_fixture() -> Genuine:
    return Genuine()


@pytest.fixture(autouse=True)
def global_rand() -> Random:
    random.seed(None)
    return random
