"""Provide Ant`s Request, Response, Item and Extractor."""
import typing
import os
from collections import defaultdict
from collections.abc import MutableMapping
import logging
import re
import tempfile
import webbrowser

from aiohttp import ClientResponse, ClientRequest, hdrs
from aiohttp.client import DEFAULT_TIMEOUT
from lxml import html
import jpath
import ujson
from multidict import CIMultiDict

from .exceptions import ItemExtractError, ItemGetValueError


class Request(ClientRequest):
    def __init__(self, *args, timeout: float = DEFAULT_TIMEOUT.total,
                 response_in_stream: bool = False,
                 headers: typing.Optional[CIMultiDict] = None,
                 data: typing.Optional[
                     typing.Union[typing.AnyStr, dict, typing.IO]] = None,
                 **kwargs) -> None:
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

    def get_text(self, encoding: typing.Optional[str] = None,
                 errors: str = 'strict') -> str:

        if self._body is None:
            raise ValueError('Read stream first')
        if self._text is None:
            if encoding is None:
                encoding = self.get_encoding()
            self._text = self._body.decode(encoding, errors=errors)
        return self._text

    @property
    def simple_text(self) -> str:
        return self.get_text(errors='ignore')

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
            self, file_type: str = '.html',
            _open_browser_function: typing.Callable
            [..., bool] = webbrowser.open) -> bool:
        fd, path = tempfile.mkstemp(file_type)
        os.write(fd, self._body)
        os.close(fd)
        return _open_browser_function('file://' + path)


class CustomNoneType:
    """Different with "None" obj ("null" in json)
    """
    pass


Item = typing.TypeVar('Item')
Things = typing.Union[Request, Response, Item]


def set_value_to_item(item: Item, key: str, value: typing.Any):
    if isinstance(item, MutableMapping):
        item[key] = value
    else:
        setattr(item, key, value)


def get_value_from_item(
        item: Item, key: str, default: typing.Any = CustomNoneType()):
    try:
        if isinstance(item, MutableMapping):
            return item[key]
        else:
            return getattr(item, key)
    except (KeyError, AttributeError) as e:
        if isinstance(default, CustomNoneType):
            raise ItemGetValueError from e
        else:
            return default


Resource = typing.Union[Response, html.HtmlElement, str, dict]


class Searcher:
    """Search data we need from data resource by pattern."""
    name = 'base'

    @staticmethod
    def search(pattern: str, data: Response) -> typing.List[typing.Any]:
        """Search information from source data by pattern"""


class RegexSearcher(Searcher):
    name = 'regex'

    @staticmethod
    def search(pattern: str, data: Response) -> typing.List[typing.Any]:
        # convert data to string
        if isinstance(data, Response):
            data = data.simple_text
        elif isinstance(data, html.HtmlElement):
            data = html.tostring(data, encoding='unicode')
        else:
            data = str(data)
        return re.findall(pattern, data)


class JsonSearcher(Searcher):
    name = 'jpath'

    @staticmethod
    def search(pattern: str, data: Response) -> typing.List[typing.Any]:
        # convert data to json object
        if isinstance(data, Response):
            data = data.simple_json
        elif isinstance(data, str):
            data = ujson.loads(data)
        return jpath.get_all(pattern, data)


class XmlSearcher(Searcher):
    name = 'xpath'

    @staticmethod
    def search(pattern: str, data: Response) -> typing.List[typing.Any]:
        if isinstance(data, Response):
            data = data.html_element
        elif not isinstance(data, html.HtmlElement):
            data = html.fromstring(str(data))
        return data.xpath(pattern)


class ItemExtractor:
    """Search data and create item."""
    EXTRACT_WITH_TAKE_FIRST = 'take_first'
    EXTRACT_WITH_JOIN_ALL = 'join_all'
    EXTRACT_WITH_DO_NOTHING = 'do_nothing'
    searchers: typing.Dict[str, Searcher] = {
        cls.name: cls for cls in (RegexSearcher, JsonSearcher, XmlSearcher)}

    def __init__(self, item_class: typing.Type[Item]) -> None:
        self.item_class = item_class
        self.logger = logging.getLogger(self.__class__.__name__)
        self.rules: typing.DefaultDict[
            str, typing.List[typing.Tuple[str, str, str, typing.Any]]
        ] = defaultdict(list)
        # eg: {'name': [('regex', 'pattern', 'extract_type', 'default'),]}

    def add_pattern(self, _type: str, key: str, pattern: str,
                    extract_type: str = EXTRACT_WITH_TAKE_FIRST,
                    default: typing.Any = CustomNoneType()):
        if _type in self.searchers.keys():
            self.rules[key].append((_type, pattern, extract_type, default))
        else:
            raise ValueError(
                'The type of searcher: {:s} not support'.format(_type))

    @classmethod
    def extract_value(cls, _type: str, pattern: str, data: Resource,
                      extract_type=EXTRACT_WITH_TAKE_FIRST,
                      default: typing.Any = CustomNoneType()) -> typing.Any:
        if _type not in cls.searchers.keys():
            raise ValueError('The type: {:s} not support'.format(_type))

        extract_value = cls.searchers[_type].search(pattern, data)
        if not extract_value:
            if not isinstance(default, CustomNoneType):
                return default
            else:
                raise ItemExtractError(
                    'Get empty result when extract value'
                    'with rule: {:s}'.format(str((_type, pattern))))
        if extract_type == ItemExtractor.EXTRACT_WITH_TAKE_FIRST:
            extract_value = extract_value[0]
        elif extract_type == ItemExtractor.EXTRACT_WITH_JOIN_ALL:
            extract_value = list(filter(lambda x: isinstance(x, str),
                                        extract_value))  # join string only
            extract_value = ''.join(extract_value)
        return extract_value

    def extract(self, data: Resource) -> Item:
        """Create item by patterns"""
        self.logger.debug('Extract item: {:s} with rule: {:s}'.format(
            self.item_class.__name__, str(self.rules)))
        item = self.item_class()
        for key, rule in self.rules.items():
            value = CustomNoneType()
            for path_type, path, extract_type, default in rule:
                try:
                    extract_value = self.__class__.extract_value(
                        path_type, path, data, extract_type=extract_type,
                        default=default)
                except ItemExtractError:
                    continue
                if not isinstance(value,
                                  CustomNoneType) and value != extract_value:
                    raise ItemExtractError(
                        'Match different result: {:s} and {:s} for key: '
                        '{:s}'.format(value, extract_value, key))
                value = extract_value
            if not isinstance(value, CustomNoneType):
                set_value_to_item(item, key, value)
            else:
                raise ItemExtractError('Can`t extract item`s key: ' + key)
        return item


class ItemNestExtractor(ItemExtractor):
    def __init__(self, root_path_type: str, root_path: str,
                 item_class: typing.Type[Item]) -> None:
        self.root_path_type = root_path_type
        self.root_path = root_path
        super().__init__(item_class)

    def extract(self, data: Response):
        raise NotImplementedError('This method is dropped in this class')

    def extract_items(self, data: Resource
                      ) -> typing.Generator[Item, None, None]:
        base_data = self.extract_value(
            self.root_path_type, self.root_path, data,
            extract_type=self.EXTRACT_WITH_DO_NOTHING)
        for data in base_data:
            yield super().extract(data)


__all__ = ['Request', 'Response', 'ItemExtractor', 'ItemNestExtractor',
           'Things', 'get_value_from_item', 'set_value_to_item']
