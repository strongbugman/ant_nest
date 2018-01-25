from typing import Any

from .ant import *
from .cli import *
from .things import *
from .pipelines import *
from . import queen
from .exceptions import *


def extract_value(_type: str, path: str, data: Any, extract_type: str=ItemExtractor.extract_with_take_first,
                  ignore_exception: bool=True,
                  default: Any=None) -> Any:
    try:
        return ItemExtractor.extract_value(_type, path, data, extract_type=extract_type)
    except Exception as e:
        if ignore_exception:
            return default
        else:
            raise e


def extract_value_by_xpath(path: str, data: Any, extract_type: str=ItemExtractor.extract_with_take_first,
                           ignore_exception: bool=True, default: Any=None) -> Any:
    return extract_value('xpath', path, data, extract_type=extract_type, ignore_exception=ignore_exception,
                         default=default)


def extract_value_by_jpath(path: str, data: Any, extract_type: str=ItemExtractor.extract_with_take_first,
                           ignore_exception: bool=True, default: Any=None) -> Any:
    return extract_value('jpath', path, data, extract_type=extract_type, ignore_exception=ignore_exception,
                         default=default)


def extract_value_by_regex(path: str, data: Any, extract_type: str=ItemExtractor.extract_with_take_first,
                           ignore_exception: bool=True, default: Any=None) -> Any:
    return extract_value('regex', path, data, extract_type=extract_type, ignore_exception=ignore_exception,
                         default=default)


class CliAnt(Ant):
    async def run(self):
        pass


__all__ = ['queen'] + ant.__all__ + cli.__all__ + pipelines.__all__ + exceptions.__all__ +\
          things.__all__ + ['extract_value_by_jpath', 'extract_value_by_regex', 'extract_value_by_xpath']
