"""Provide Ant`s Request, Response, Item and Extractor."""
from typing import Any, Optional, Tuple, Type, Union, List, \
    DefaultDict, AnyStr, IO, Callable, Generator, TypeVar
from collections import defaultdict
from collections.abc import MutableMapping
import logging
import re

from aiohttp import ClientResponse, ClientRequest
from aiohttp.client import DEFAULT_TIMEOUT
from lxml import html
import jpath
import ujson

from .exceptions import ItemExtractError, ItemGetValueError


class Request(ClientRequest):
    def __init__(self, *args, timeout: float = DEFAULT_TIMEOUT.total,
                 response_in_stream: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.response_in_stream = response_in_stream
        self.timeout = timeout
        # store data obj
        self.data: Optional[Union[AnyStr, dict, IO]] = kwargs.get('data', None)


class Response(ClientResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = None
        self._html_element = None
        self._json = None

    def get_text(self, encoding: Optional[str] = None,
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

    def get_json(self, loads: Callable = ujson.loads):
        if self._json is None:
            self._json = loads(self.simple_text)
        return self._json

    @property
    def simple_json(self) -> Any:
        return self.get_json()

    @property
    def html_element(self) -> html.HtmlElement:
        if self._html_element is None:
            self._html_element = html.fromstring(self.simple_text)
        return self._html_element


class CustomNoneType:
    """Different with "None" obj ("null" in json)
    """
    pass


Item = TypeVar('Item')
Things = Union[Request, Response, Item]


def set_value_to_item(item: Item, key: str, value: Any):
    if isinstance(item, MutableMapping):
        item[key] = value
    else:
        setattr(item, key, value)


def get_value_by_item(item: Item, key: str, default: Any = CustomNoneType()):
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


class ItemExtractor:
    extract_with_take_first = 'take_first'
    extract_with_join_all = 'join_all'
    extract_with_do_nothing = 'do_nothing'

    def __init__(self, item_class: Type[Item]) -> None:
        self.item_class = item_class
        self.logger = logging.getLogger(self.__class__.__name__)
        self.paths: DefaultDict[str, List[Tuple[str, str, str]]] = \
            defaultdict(list)

    def add_xpath(self, key: str, xpath: str,
                  extract_type=extract_with_take_first):
        self.paths[key].append(('xpath', xpath, extract_type))

    def add_regex(self, key: str, pattern: str,
                  extract_type=extract_with_take_first):
        self.paths[key].append(('regex', pattern, extract_type))

    def add_jpath(self, key: str, jpath, extract_type=extract_with_take_first):
        self.paths[key].append(('jpath', jpath, extract_type))

    @staticmethod
    def _regex_search(pattern: str, data: Any) -> List[str]:
        # convert data to string
        if isinstance(data, Response):
            data = data.simple_text
        elif isinstance(data, html.HtmlElement):
            data = html.tostring(data, encoding='unicode')
        else:
            data = str(data)
        return re.findall(pattern, data)

    @staticmethod
    def _jpath_search(pattern: str, data: Any) -> List[Any]:
        # convert data to json object
        if isinstance(data, Response):
            data = data.simple_json
        elif isinstance(data, str):
            data = ujson.loads(data)
        return jpath.get_all(pattern, data)

    @staticmethod
    def _xpath_search(pattern: str, data: Any
                      ) -> List[Union[str, html.HtmlElement]]:
        if isinstance(data, Response):
            data = data.html_element
        elif not isinstance(data, html.HtmlElement):
            data = html.fromstring(str(data))
        return data.xpath(pattern)

    @staticmethod
    def extract_value(_type: str, pattern: str, data: Any,
                      extract_type=extract_with_take_first) -> Any:
        if _type == 'xpath':
            extract_value = ItemExtractor._xpath_search(pattern, data)
        elif _type == 'regex':
            extract_value = ItemExtractor._regex_search(pattern, data)
        elif _type == 'jpath':
            extract_value = ItemExtractor._jpath_search(pattern, data)
        else:
            raise ValueError('The type: {:s} not support'.format(_type))
        # handle by extract type
        if extract_type == ItemExtractor.extract_with_take_first:
            extract_value = extract_value[0]
        elif extract_type == ItemExtractor.extract_with_join_all:
            extract_value = list(filter(lambda x: isinstance(x, str),
                                        extract_value))  # join string only
            extract_value = ''.join(extract_value)
        return extract_value

    def extract(self, data: Any) -> Item:
        """Extract item from response or other data by xpath,
        jpath or regex."""
        self.logger.debug('Extract item: {:s} with path: {:s}'.format(
            self.item_class.__name__, str(self.paths)))
        item = self.item_class()
        for key, paths in self.paths.items():
            value = CustomNoneType()
            for path_type, path, extract_type in paths:
                try:
                    extract_value = ItemExtractor.extract_value(
                        path_type, path, data, extract_type=extract_type)
                except IndexError:  # IndexError is often raised
                    continue
                # check multiple path`s result
                if not isinstance(value,
                                  CustomNoneType) and value != extract_value:
                    raise ItemExtractError(
                        'Match different result: {:s} and {:s} for paths: '
                        '{:s}'.format(value, extract_value, str(paths)))
                value = extract_value
            if not isinstance(value, CustomNoneType):
                set_value_to_item(item, key, value)
        return item


class ItemNestExtractor(ItemExtractor):
    def __init__(self, root_path_type: str, root_path: str,
                 item_class: Type[Item]) -> None:
        self.root_path_type = root_path_type
        self.root_path = root_path
        super().__init__(item_class)

    def extract(self, response: Response):
        raise NotImplementedError('This method is dropped in this class')

    def extract_items(self, response: Response
                      ) -> Generator[Item, None, None]:
        base_data = self.extract_value(
            self.root_path_type, self.root_path, response,
            extract_type=self.extract_with_do_nothing)
        for data in base_data:
            yield super().extract(data)


__all__ = ['Request', 'Response', 'ItemExtractor', 'ItemNestExtractor',
           'Things'] + \
          [var for var in vars().keys() if 'Field' in var]
