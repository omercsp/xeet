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


def _set_tests_order(**kwargs):
    items = kwargs.get('items', [])
    # Example: Define a custom order for specific modules
    module_order = ["test_common",  "test_resource", "test_core", "test_xeet_conf",
                    "test_run_events", "test_exec_step"]
    module_order = [f"ut.{mod}" for mod in module_order]

    # Create a new list for sorted items
    sorted_items = []

    # Add items based on the desired module order
    for module_name in module_order:
        sorted_items.extend(item for item in items if item.module.__name__ == module_name)

    # Add any remaining items (not explicitly ordered)
    for item in items:
        if item not in sorted_items:
            sorted_items.append(item)

    # Update the items list in place
    items[:] = sorted_items


def pytest_collection_modifyitems(session, config, items):
    _set_tests_order(session=session, config=config, items=items)
