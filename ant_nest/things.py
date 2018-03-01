"""The thing`s usage is simple, can be created by ant, processed by ants and pipelines"""
from typing import Any, Optional, Iterator, Tuple, Dict, Type, Union, List, DefaultDict, AnyStr, IO, Callable, Generator
from collections.abc import MutableMapping
import abc
from collections import defaultdict
import logging
import re

from aiohttp import ClientResponse, ClientRequest
from lxml import html
import jpath
import simplejson

from .exceptions import FieldValidationError, ItemExtractError


class Request(ClientRequest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # store data obj
        self.data = kwargs.get('data', None)  # type: Union[AnyStr, dict, IO, None]


class Response(ClientResponse):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._text = None
        self._html_element = None
        self._json = None

    def get_text(self, encoding: Optional[str]=None, errors: str='strict') -> str:
        if self._content is None:
            raise ValueError('Read stream first')
        if self._text is None:
            if encoding is None:
                encoding = self.get_encoding()
            self._text = self._content.decode(encoding, errors=errors)
        return self._text

    @property
    def simple_text(self) -> str:
        return self.get_text(errors='ignore')

    def get_json(self, loads: Callable=simplejson.loads):
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
    pass


class IntField:
    _type = int
    storage_name = ''
    __shadow_name_prefix = '__field#'

    def __init__(self, null: bool=False, default: Any=CustomNoneType()):
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


# store all item class`s field reference
_fields = defaultdict(dict)  # type: DefaultDict[Type['Item'], Dict[str, IntField]]


class ItemMeta(abc.ABCMeta):
    def __init__(cls, name: str, bases: Tuple[type, ...], attr_dict: Dict[str, Any]):
        super().__init__(name, bases, attr_dict)
        for k, v in attr_dict.items():
            if isinstance(v, IntField):
                _fields[cls][k] = v
                v.storage_name = IntField.make_shadow_name(k)
        # fetch all fields from base class
        for base_cls in bases:
            if base_cls in _fields:
                # base item class`s fields must have been set
                _fields[cls].update(_fields[base_cls])


class Item(MutableMapping, metaclass=ItemMeta):
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        # default field value
        for k, obj in _fields[self.__class__].items():
            if not isinstance(obj.default, CustomNoneType) and k not in self:
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
        Get descriptors reference method from _fields"""
        for k, obj in _fields[self.__class__].items():
            if k in self:
                setattr(self, k, obj.validate(getattr(self, k)))
            elif not obj.null:
                raise FieldValidationError(
                    '\'{:s}.{:s}\' have no value yet'.format(self.__class__.__name__, k))

    def __repr__(self):
        return '{:s}: {:s}'.format(self.__class__.__name__, str(dict(self)))

    def __str__(self):
        return '{:s}'.format(self.__class__.__name__)


Things = Union[Request, Response, Item]


class ItemExtractor:
    extract_with_take_first = 'take_first'
    extract_with_join_all = 'join_all'
    extract_with_do_nothing = 'do_nothing'

    def __init__(self, item_class: Type[Item]):
        self.item_class = item_class
        self.logger = logging.getLogger(self.__class__.__name__)
        self.paths = defaultdict(list)  # type: DefaultDict[str, List[Tuple[str, str, str]]]

    def add_xpath(self, key: str, xpath: str, extract_type=extract_with_take_first):
        self.paths[key].append(('xpath', xpath, extract_type))

    def add_regex(self, key: str, pattern: str, extract_type=extract_with_take_first):
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
            data = simplejson.loads(data)
        try:
            return jpath.get_all(pattern, data)
        except KeyError:  # it seem is a bug in "jpath" lib, should return "[]" other than raise a error
            return []

    @staticmethod
    def _xpath_search(pattern: str, data: Any) -> List[Union[str, html.HtmlElement]]:
        if isinstance(data, Response):
            data = data.html_element
        elif not isinstance(data, html.HtmlElement):
            data = html.fromstring(str(data))
        return data.xpath(pattern)

    @staticmethod
    def extract_value(_type: str, pattern: str, data: Any, extract_type=extract_with_take_first) -> Any:
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
            extract_value = list(filter(lambda x: isinstance(x, str), extract_value))  # join string only
            extract_value = ''.join(extract_value)
        return extract_value

    def extract(self, data: Any) -> Item:
        """Extract item from response or other data by xpath, jpath or regex."""
        self.logger.debug('Extract item: {:s} with path: {:s}'.format(self.item_class.__name__, str(self.paths)))
        item = self.item_class()
        for key, paths in self.paths.items():
            value = CustomNoneType()  # be different with "None" obj ("null" in json)
            for path_type, path, extract_type in paths:
                try:
                    extract_value = ItemExtractor.extract_value(path_type, path, data, extract_type=extract_type)
                except IndexError:  # IndexError is often raised
                    continue
                # check multiple path`s result
                if not isinstance(value, CustomNoneType) and value != extract_value:
                    raise ItemExtractError(
                        'Match different result: {:s} and {:s} for paths: {:s}'.format(value, extract_value, str(paths)))
                value = extract_value
            if not isinstance(value, CustomNoneType):
                item[key] = value
        return item


class ItemNestExtractor(ItemExtractor):
    def __init__(self, root_path_type: str, root_path: str, item_class: Type[Item]):
        self.root_path_type = root_path_type
        self.root_path = root_path
        super().__init__(item_class)

    def extract(self, response: Response):
        raise NotImplementedError('This method is dropped in this class')

    def extract_items(self, response: Response) -> Generator[Item, None, None]:
        base_data = self.extract_value(self.root_path_type, self.root_path, response,
                                       extract_type=self.extract_with_do_nothing)
        for data in base_data:
            yield super().extract(data)


__all__ = ['Request', 'Response', 'Item', 'ItemExtractor', 'ItemNestExtractor', 'Things'] +\
          [var for var in vars().keys() if 'Field' in var]
