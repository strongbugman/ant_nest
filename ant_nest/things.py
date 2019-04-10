"""Provide Ant`s Request, Response, Item and Extractor."""
import typing
import os
from collections.abc import MutableMapping
import tempfile
import webbrowser

from aiohttp import ClientResponse, ClientRequest, hdrs
from aiohttp.typedefs import LooseHeaders
from lxml import html
import ujson

from .exceptions import ItemGetValueError


class Request(ClientRequest):
    def __init__(
        self,
        *args,
        timeout: float = 60,
        response_in_stream: bool = False,
        headers: typing.Optional[LooseHeaders] = None,
        data: typing.Any = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, headers=headers, data=data, **kwargs)

        if headers is None or hdrs.HOST not in headers:
            self.headers.pop(hdrs.HOST)

        self.response_in_stream = response_in_stream
        self.timeout = timeout
        self.data = data


class Response(ClientResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = None
        self._html_element = None
        self._json = None

    def get_text(
        self, encoding: typing.Optional[str] = None, errors: str = "strict"
    ) -> str:

        if self._body is None:
            raise ValueError("Read stream first")
        if self._text is None:
            if encoding is None:
                encoding = self.get_encoding()
            self._text = self._body.decode(encoding, errors=errors)
        return self._text

    @property
    def simple_text(self) -> str:
        return self.get_text(errors="ignore")

    def get_json(self, loads: typing.Callable = ujson.loads):
        if self._json is None:
            self._json = loads(self.simple_text)
        return self._json

    @property
    def simple_json(self) -> typing.Any:
        return self.get_json()

    @property
    def html_element(self) -> html.HtmlElement:
        if self._html_element is None:
            self._html_element = html.fromstring(self.simple_text)
        return self._html_element

    def open_in_browser(
        self,
        file_type: str = ".html",
        _open_browser_function: typing.Callable[..., bool] = webbrowser.open,
    ) -> bool:
        fd, path = tempfile.mkstemp(file_type)
        os.write(fd, self._body)
        os.close(fd)
        return _open_browser_function("file://" + path)


class CustomNoneType:
    """Different with "None" obj ("null" in json)
    """

    pass


Item = typing.TypeVar("Item")


def set_value_to_item(item: Item, key: str, value: typing.Any):
    if isinstance(item, MutableMapping):
        item[key] = value
    else:
        setattr(item, key, value)


def get_value_from_item(item: Item, key: str):
    try:
        if isinstance(item, MutableMapping):
            return item[key]
        else:
            return getattr(item, key)
    except (KeyError, AttributeError) as e:
        raise ItemGetValueError from e


class ItemExtractor:
    def __init__(self, item_cls: typing.Type[Item]):
        self.item_cls = item_cls
        self.extractors: typing.Dict[
            str, typing.Callable[[typing.Any], typing.Any]
        ] = dict()

    def add_extractor(
        self, key: str, extractor: typing.Callable[[typing.Any], typing.Any]
    ):
        self.extractors[key] = extractor

    def extract(self, res: Response) -> Item:
        item = self.item_cls()
        for key, extractor in self.extractors.items():
            set_value_to_item(item, key, extractor(res))

        return item


class ItemNestExtractor(ItemExtractor):
    def __init__(
        self,
        item_class: typing.Type[Item],
        root_extractor: typing.Callable[[Response], typing.Sequence],
    ):
        self.root_extractor = root_extractor
        super().__init__(item_class)

    def extract_items(self, res: Response) -> typing.Generator[Item, None, None]:
        for node in self.root_extractor(res):
            yield super().extract(node)


__all__ = [
    "Request",
    "Response",
    "Item",
    "ItemExtractor",
    "ItemNestExtractor",
    "get_value_from_item",
    "set_value_to_item",
]
