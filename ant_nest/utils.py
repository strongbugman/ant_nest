"""Utilities box"""
import typing
import logging
import asyncio

import async_timeout

from .ant import Ant
from .exceptions import ThingDropped

__all__ = ['ExceptionFilter', 'timeout_wrapper']


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


# TODO: move
class CliAnt(Ant):
    async def run(self):
        pass


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
