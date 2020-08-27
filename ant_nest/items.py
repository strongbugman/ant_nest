"""Provide Ant`s Item and Extractor."""
import typing
from collections.abc import MutableMapping

import httpx

from .exceptions import ItemGetValueError


class CustomNoneType:
    """Different with "None" obj ("null" in json)"""

    pass


Item = typing.TypeVar("Item")


def set_value(item: Item, key: str, value: typing.Any):
    if isinstance(item, MutableMapping):
        item[key] = value
    else:
        setattr(item, key, value)


def get_value(item: Item, key: str) -> typing.Any:
    try:
        if isinstance(item, MutableMapping):
            return item[key]
        else:
            return getattr(item, key)
    except (KeyError, AttributeError) as e:
        raise ItemGetValueError from e


class Extractor:
    def __init__(self, item_cls: typing.Type[Item]):
        self.item_cls = item_cls
        self.extractors: typing.Dict[
            str, typing.Callable[[typing.Any], typing.Any]
        ] = dict()

    def add_extractor(
        self, key: str, extractor: typing.Callable[[typing.Any], typing.Any]
    ):
        self.extractors[key] = extractor

    def extract(self, res: httpx.Response) -> Item:
        item = self.item_cls()
        for key, extractor in self.extractors.items():
            set_value(item, key, extractor(res))

        return item


class NestExtractor(Extractor):
    def __init__(
        self,
        item_class: typing.Type[Item],
        root_extractor: typing.Callable[[httpx.Response], typing.Sequence],
    ):
        self.root_extractor = root_extractor
        super().__init__(item_class)

    def extract_items(self, res: httpx.Response) -> typing.Generator[Item, None, None]:
        for node in self.root_extractor(res):
            yield super().extract(node)


__all__ = [
    "Item",
    "Extractor",
    "NestExtractor",
    "get_value",
    "set_value",
]
