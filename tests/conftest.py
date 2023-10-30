from __future__ import annotations

from random import Random

import pytest

from genuine.bases import Genuine


@pytest.fixture(name="gen")
def gen_fixture() -> Genuine:
    return Genuine()


@pytest.fixture
def global_rand() -> Random:
    return Random(1)
