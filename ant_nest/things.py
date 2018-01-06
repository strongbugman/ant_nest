"""The thing`s usage is simple, can be created by ant, processed by ants and pipelines"""
from typing import Any, Optional, Iterator, Tuple, Dict, Type, Union, List, DefaultDict, AnyStr, IO
from collections.abc import MutableMapping
import json
import abc
from collections import defaultdict
import logging
import re
from multidict import CIMultiDictProxy

from lxml import html
from yarl import URL
import jpath
from aiohttp.backport_cookies import SimpleCookie

from .exceptions import FieldValidationError, ItemExtractError


class Request:
    __slots__ = ('url', 'params', 'method', 'headers', 'cookies', 'data')

    def __init__(self, url: Union[str, URL], method='GET', params: Optional[dict]=None, headers: Optional[dict]=None,
                 cookies: Optional[dict]=None, data: Optional[Union[AnyStr, Dict, IO]]=None):
        if isinstance(url, str):
            url = URL(url)
        self.url = url
        self.params = params
        self.method = method
        self.headers = headers
        self.cookies = cookies
        self.data = data

    def __repr__(self):
        return '{:s}: {:s} {:s}'.format(self.__class__.__name__, self.method, str(self.url))


class Response:
    __slots__ = ('url', 'status', 'headers', 'cookies', 'encoding', 'content', '_text', 'request', '_html_element',
                 '_json')

    def __init__(self, request: Request, status: int, content: bytes, headers: CIMultiDictProxy,
                 cookies: SimpleCookie, encoding: str='utf-8'):
        self.request = request
        self.url = request.url
        self.status = status
        self.headers = headers
        self.cookies = cookies
        self.encoding = encoding
        self.content = content
        self._text = None
        self._html_element = None
        self._json = None

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = self.content.decode(self.encoding)
        return self._text

    @property
    def json(self) -> Any:
        if self._json is None:
            self._json = json.loads(self.text)
        return self._json

    @property
    def html_element(self) -> html.HtmlElement:
        if self._html_element is None:
            self._html_element = html.fromstring(self.text)
        return self._html_element

    def __repr__(self):
        return '{:s}: {:s} {:d}'.format(self.__class__.__name__, str(self.url), self.status)


class IntField:
    _type = int
    storage_name = ''
    __shadow_name_prefix = '__field#'

    def __init__(self, null: bool=False, default: Any=None):
        """
        "null" is True means this field can be ignore when value have not been set in validation,
        "default" is None means this field have no default value
        """
        self.null = null
        self.default = default

    def __set__(self, instance: 'Item', value: Any) -> None:
        setattr(instance, self.storage_name, value)

    def __get__(self, instance: 'Item', owner: Type['Item']) -> Any:
        try:
            return getattr(instance, self.storage_name)
        except AttributeError as e:
            raise AttributeError(
                '\'{:s}\' object has no attribute \'{:s}\''.format(instance.__class__.__name__,
                                                                   self.get_name_from_shadow(self.storage_name))) from e

    def __delete__(self, instance):
        delattr(instance, self.storage_name)

    def validate(self, value: Any) -> Any:
        """:raise FieldValidationError"""
        try:
            return self._type(value)
        except (ValueError, TypeError) as e:
            raise FieldValidationError(str(e)) from e

    @classmethod
    def make_shadow_name(cls, name: str) -> str:
        if name == cls.__shadow_name_prefix:
            raise AttributeError('This name: {:s} has been used internally'.format(cls.__shadow_name_prefix))
        return cls.__shadow_name_prefix + name

    @classmethod
    def is_shadow_name(cls, name: str) -> bool:
        return cls.__shadow_name_prefix in name

    @classmethod
    def get_name_from_shadow(cls, name: str) -> str:
        return name.replace(cls.__shadow_name_prefix, '')


class FloatField(IntField):
    _type = float


class StringField(IntField):
    _type = str


class BytesField(IntField):
    _type = bytes


class ItemMeta(abc.ABCMeta):
    def __init__(cls, name: str, bases: Tuple[type, ...], attr_dict: Dict[str, Any]):
        super().__init__(name, bases, attr_dict)
        for k, v in attr_dict.items():
            if isinstance(v, IntField):
                v.storage_name = IntField.make_shadow_name(k)


class Item(MutableMapping, metaclass=ItemMeta):
    _is_validating = False

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        # default field value
        class_dict = self.__class__.__dict__
        for k, obj in class_dict.items():
            if isinstance(obj, IntField):
                if obj.default is not None and k not in self:
                    setattr(self, k, obj.default)

    def __setattr__(self, key: str, value: Any) -> None:
        if isinstance(key, str):
            super().__setattr__(key, value)
        else:
            raise AttributeError('attribute name must be string, not \'{:s}\''.format(key.__class__.__name__))

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            setattr(self, key, value)
        except TypeError as e:
            raise KeyError(str(e)) from e

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError as e:
            raise KeyError(str(e)) from e

    def __delitem__(self, key: str) -> None:
        try:
            delattr(self, key)
        except AttributeError as e:
            raise KeyError(str(e)) from e

    def __len__(self) -> int:
        return len(self.__dict__)

    def __iter__(self) -> Iterator[str]:
        keys = []
        for k in self.__dict__:
            if IntField.is_shadow_name(k):
                keys.append(IntField.get_name_from_shadow(k))
            else:
                keys.append(k)
        return iter(keys)

    def validate(self):
        """Validate item`s type.
        Get descriptors reference method from __class__.__dict__"""
        class_dict = self.__class__.__dict__
        for k, obj in class_dict.items():
            if isinstance(obj, IntField):
                if k in self:
                    setattr(self, k, class_dict[k].validate(getattr(self, k)))
                elif not obj.null:
                    raise FieldValidationError(
                        '\'{:s}.{:s}\' have no value yet'.format(self.__class__.__name__, k))

    def __repr__(self):
        return '{:s}: {:s}'.format(self.__class__.__name__, str(dict(self)))

    def __str__(self):
        return '{:s}'.format(self.__class__.__name__)


Things = Union[Request, Response, Item]


class CustomNoneType:
    pass


class ItemExtractor:
    extract_with_take_first = 'take_first'
    extract_with_join_all = 'join_all'
    extract_with_do_nothing = 'do_nothing'

    def __init__(self, item_class: Type[Item]):
        self.item_class = item_class
        self.logger = logging.getLogger(self.__class__.__name__)
        self.path = defaultdict(list)  # type: DefaultDict[str, List[Tuple[str, str, str]]]

    def add_xpath(self, key: str, xpath: str, extract_type=extract_with_take_first):
        self.path[key].append(('xpath', xpath, extract_type))

    def add_regex(self, key: str, pattern: str, extract_type=extract_with_take_first):
        self.path[key].append(('regex', pattern, extract_type))

    def add_jpath(self, key: str, jpath, extract_type=extract_with_take_first):
        self.path[key].append(('jpath', jpath, extract_type))

    @staticmethod
    def extract_value(_type: str, pattern: str, data: Any, extract_type=extract_with_take_first) -> Any:
        if _type == 'xpath':
            extract_value = data.xpath(pattern)
        elif _type == 'regex':
            extract_value = re.findall(pattern, data)
        elif _type == 'jpath':
            extract_value = jpath.get_all(pattern, data)
        else:
            raise ValueError('The type: {:s} not support'.format(_type))
        # handle by extract type
        if extract_type == ItemExtractor.extract_with_take_first:
            extract_value = extract_value[0]
        elif extract_type == ItemExtractor.extract_with_join_all:
            extract_value = list(filter(lambda x: isinstance(x, str), extract_value))  # join string only
            extract_value = ''.join(extract_value)
        return extract_value

    def extract(self, response: Response) -> Item:
        """Extract item from response by path with xpath, jpath or re."""
        self.logger.debug('Extract item: {:s} with path: {:s}'.format(self.item_class.__name__, str(self.path)))
        item = self.item_class()
        for key, all_xpath in self.path.items():
            value = CustomNoneType()  # be different with "None" obj ("null" in json)
            for path_type, path, extract_type in all_xpath:
                # get data by search type
                if path_type == 'xpath':
                    data = response.html_element
                elif path_type == 'regex':
                    data = response.text
                else:
                    data = response.json
                try:
                    extract_value = ItemExtractor.extract_value(path_type, path, data, extract_type=extract_type)
                except IndexError:
                    continue
                # check multiple path`s result
                if not isinstance(value, CustomNoneType) and value != extract_value:
                    raise ItemExtractError(
                        'Match different result: {:s} and {:s} for key: {:s}'.format(value, extract_value, key))
                value = extract_value
            if not isinstance(value, CustomNoneType):
                item[key] = value
        return item


__all__ = ['Request', 'Response', 'Item', 'ItemExtractor', 'Things'] + [var for var in vars().keys() if 'Field' in var]
