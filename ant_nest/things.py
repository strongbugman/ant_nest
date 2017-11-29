"""The thing`s usage is simple, can be created by ant, processed by ants and pipelines"""
from typing import Any, Optional, Iterator, Tuple, Dict, Type, Union, List, DefaultDict
from collections.abc import MutableMapping
import json
import abc
from collections import defaultdict
import logging

from lxml import html
from yarl import URL


class Request:
    __slots__ = ('url', 'params', 'method', 'headers', 'cookies', 'data', 'proxy', 'max_redirects', 'allow_redirects')

    def __init__(self, url: Union[str, URL], method='GET', params: Optional[dict]=None, headers: Optional[dict]=None,
                 cookies: Optional[dict]=None, data: Optional[Any]=None, proxy: Optional[str]=None,
                 allow_redirects=True, max_redirects=10):
        if isinstance(url, str):
            url = URL(url)
        self.url = url
        self.params = params
        self.method = method
        self.headers = headers
        self.cookies = cookies
        self.data = data
        self.proxy = proxy
        self.allow_redirects = allow_redirects
        self.max_redirects = max_redirects

    def __repr__(self):
        return '{:s}: {:s} {:s}'.format(self.__class__.__name__, self.method, str(self.url))


class Response:
    __slots__ = ('url', 'status', 'headers', 'cookies', 'encoding', 'content', 'text', 'request', '_html_element',
                 '_json')

    def __init__(self, request: Request, status: int, content: bytes, headers: Optional[dict]=None,
                 cookies: Optional[dict]=None, encoding: str='utf-8'):
        self.request = request
        self.url = request.url
        self.status = status
        self.headers = headers
        self.cookies = cookies
        self.encoding = encoding
        self.content = content
        self.text = content.decode(encoding)
        self._html_element = None
        self._json = None

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


class FiledValidationError(Exception):
    pass


class ItemExtractError(Exception):
    """Raise when extract item when error"""


class IntField:
    _type = int
    storage_name = ''
    __shadow_name_prefix = '__field#'

    def __init__(self, null: bool=False):
        self.null = null

    def __set__(self, instance: 'Item', value: Any) -> None:
        setattr(instance, self.storage_name, value)

    def __get__(self, instance: 'Item', owner: Type['Item']) -> Any:
        return getattr(instance, self.storage_name)

    def __delete__(self, instance):
        delattr(instance, self.storage_name)

    def validate(self, value: Any) -> Any:
        """:raise FiledValidationError"""
        if self.null and value is None:
            return value
        elif value is not None:
            try:
                return self._type(value)
            except (ValueError, TypeError) as e:
                raise FiledValidationError(e)
        else:
            raise FiledValidationError

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

    def __setattr__(self, key: str, value: Any) -> None:
        if isinstance(key, str):
            super().__setattr__(key, value)
        else:
            raise AttributeError('The key`s type must be str')

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            setattr(self, key, value)
        except AttributeError:
            raise KeyError(key)

    def __getitem__(self, key: str) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __delitem__(self, key: str) -> None:
        try:
            delattr(self, key)
        except AttributeError:
            raise KeyError(key)

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
        for k, v in self.items():
            if k in class_dict:
                setattr(self, k, class_dict[k].validate(v))

    def __repr__(self):
        return '{:s}: {:s}'.format(self.__class__.__name__, str(dict(self)))


Things = Union[Request, Response, Item]


class ItemExtractor:
    take_first = 'take_first'
    join_all = 'join_all'
    do_nothing = 'do_nothing'

    xpath = defaultdict(list)  # type: DefaultDict[str, List[Tuple[str, str]]]

    def __init__(self, item_class: Type[Item]):
        self.item_class = item_class
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_xpath(self, key: str, xpath: str, extract_type=take_first):
        self.xpath[key].append((xpath, extract_type))

    def extract(self, response: Response) -> Item:
        """Extract item from response by xpath"""
        self.logger.debug('Extract item: {:s} with xpath: {:s}'.format(self.item_class.__name__, str(self.xpath)))
        item = self.item_class()
        for key, all_xpath in self.xpath.items():
            value = None
            for xpath, extract_type in all_xpath:
                extract_value = response.html_element.xpath(xpath)
                if len(extract_value) == 0:
                    continue
                elif not isinstance(extract_value[0], str):
                    raise ItemExtractError('The xpath({:s}) result must be str'.format(
                        xpath
                    ))
                # handle by extract type
                if extract_type == self.take_first:
                    extract_value = extract_value[0]
                elif extract_type == self.join_all:
                    extract_value = ''.join(extract_value)
                elif extract_value == self.do_nothing:
                    pass
                if extract_value is not None:
                    if value is not None and value != extract_value:
                        raise ItemExtractError(
                            'Match different result: {:s} and {:s} for key: {:s}'.format(value, extract_value, key))
                    elif extract_value is not None:
                        value = extract_value
            item[key] = value
        return item
