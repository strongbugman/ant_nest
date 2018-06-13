"""Utilities box"""
import typing
import logging
import asyncio

import async_timeout

from .ant import Ant
from .things import ItemExtractor
from .exceptions import ThingDropped

__all__ = ['extract_value_by_xpath', 'extract_value_by_jpath',
           'extract_value_by_regex', 'ExceptionFilter', 'timeout_wrapper']


def timeout_wrapper(
        coro_or_func: typing.Union[typing.Coroutine, typing.Callable],
        timeout: typing.Union[float, int]
) -> typing.Union[typing.Coroutine, typing.Callable]:
    """Add timeout limit to coroutine or coroutine function"""
    is_coroutinefunction = asyncio.iscoroutinefunction(coro_or_func)

    async def wrapper(*args, **kwargs):
        with async_timeout.timeout(timeout):
            if is_coroutinefunction:
                return await coro_or_func(*args, **kwargs)
            else:
                return await coro_or_func

    if timeout < 0:
        return coro_or_func
    elif is_coroutinefunction:
        return wrapper
    else:
        return wrapper()


class CliAnt(Ant):
    async def run(self):
        pass


def extract_value(_type: str, path: str, data: typing.Any,
                  extract_type: str = ItemExtractor.extract_with_take_first,
                  ignore_exception: bool = True,
                  default: typing.Any = None) -> typing.Any:
    try:
        return ItemExtractor.extract_value(_type, path, data,
                                           extract_type=extract_type)
    except Exception as e:
        if ignore_exception:
            return default
        else:
            raise e


def extract_value_by_xpath(
        path: str, data: typing.Any,
        extract_type: str = ItemExtractor.extract_with_take_first,
        ignore_exception: bool = True,
        default: typing.Any = None) -> typing.Any:
    return extract_value('xpath', path, data, extract_type=extract_type,
                         ignore_exception=ignore_exception,
                         default=default)


def extract_value_by_jpath(
        path: str, data: typing.Any,
        extract_type: str = ItemExtractor.extract_with_take_first,
        ignore_exception: bool = True,
        default: typing.Any = None) -> typing.Any:
    return extract_value('jpath', path, data, extract_type=extract_type,
                         ignore_exception=ignore_exception,
                         default=default)


def extract_value_by_regex(
        path: str, data: typing.Any,
        extract_type: str = ItemExtractor.extract_with_take_first,
        ignore_exception: bool = True,
        default: typing.Any = None) -> typing.Any:
    return extract_value('regex', path, data, extract_type=extract_type,
                         ignore_exception=ignore_exception,
                         default=default)


class ExceptionFilter(logging.Filter):
    """A exception log filter class for logging.
    """

    def __init__(
            self,
            exceptions: typing.Sequence[
                typing.Type[Exception]] = (ThingDropped, ), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exceptions = exceptions

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            for e in self.exceptions:
                if record.exc_info[0] is e:
                    return False
        return True
