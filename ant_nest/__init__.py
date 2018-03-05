from typing import Any

from .ant import *
from .things import *
from .pipelines import *
from .coroutine_pool import *
from .exceptions import *


__version__ = '0.32.0'


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


__all__ = ant.__all__ + pipelines.__all__ + exceptions.__all__ + coroutine_pool.__all__ + \
          things.__all__ + ['extract_value_by_jpath', 'extract_value_by_regex', 'extract_value_by_xpath']
