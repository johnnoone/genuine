from __future__ import annotations

from random import Random
from typing import Iterator

import pytest

from genuine.bases import Genuine
from genuine.random import random

from genuine import FACTORIES


@pytest.fixture(name="gen")
def gen_fixture() -> Genuine:
    return Genuine()


@pytest.fixture(autouse=True)
def global_rand() -> Random:
    random.seed(None)
    return random


@pytest.fixture(autouse=True)
def _teardown_fixture() -> Iterator[None]:
    yield
    FACTORIES.clear()
