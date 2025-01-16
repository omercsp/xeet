from . import finalize, initialize
from . import XeetUnittest
from functools import cache
import pytest


@pytest.fixture(scope="session", autouse=True)
def xeet_dir_setup():
    initialize()
    yield
    finalize()


@cache
def _default_xut() -> XeetUnittest:
    return XeetUnittest("main.yaml")


@pytest.fixture
def xut():
    xut = _default_xut()
    xut.reset()
    yield xut
