import pytest


@pytest.fixture()
def item_cls():
    class Item:
        pass

    yield Item
