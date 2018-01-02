"""
Ant`s queen, provide coroutines manage function
"""
import typing
import logging
import asyncio
from asyncio.queues import Queue, QueueEmpty
from itertools import islice

import async_timeout
from aiohttp.client import DEFAULT_TIMEOUT

from .exceptions import QueenError

logger = logging.getLogger(__name__)
__queue = None  # type: typing.Optional[Queue]
__done_queue = None  # type: typing.Optional[Queue]
__running_count = 0
__timeout = DEFAULT_TIMEOUT  # in seconds
__concurrent_limit = 30
# The Queue obj and "schedule_coroutine" function should use the same event loop
__loop = None  # type: typing.Optional[asyncio.AbstractEventLoop]


__all__ = ['init_loop', 'reset_concurrent_limit', 'get_loop', 'timeout_wrapper', 'schedule_coroutine',
           'schedule_coroutines', 'as_completed', 'wait_scheduled_coroutines']


def init_loop(loop: typing.Optional[asyncio.AbstractEventLoop]=None) -> None:
    """Set event loop and coroutines queue for "schedule_coroutine" function"""
    global __queue, __done_queue, __loop
    if loop is None:
        loop = asyncio.get_event_loop()

    if __loop is not None:
        if __running_count > 0 or __done_queue.qsize() > 0 or __queue.qsize() > 0:
            raise QueenError('Replace Event loop with uncleaned coroutines')

    __loop = loop
    __queue = Queue(loop=__loop)
    __done_queue = Queue(loop=__loop)


def get_loop() -> asyncio.AbstractEventLoop:
    if __loop is None:
        init_loop()
    return __loop


def reset_concurrent_limit(limit: typing.Optional[int]) -> None:
    global __concurrent_limit
    if limit is not None:
        __concurrent_limit = limit


def timeout_wrapper(coro_or_func: typing.Union[typing.Coroutine, typing.Callable], timeout: float=__timeout
                    ) -> typing.Union[typing.Coroutine, typing.Callable]:
    """Add timeout limit to coroutine or coroutine function"""

    async def wrapper(*args, **kwargs):
        with async_timeout.timeout(timeout):
            if asyncio.iscoroutinefunction(coro_or_func):
                return await coro_or_func(*args, **kwargs)
            else:
                return await coro_or_func

    if asyncio.iscoroutinefunction(coro_or_func):
        return wrapper
    else:
        return wrapper()


def schedule_coroutine(coroutine: typing.Coroutine, timeout: float=__timeout) -> None:
    """Like "ensure_future", it schedule coroutine with concurrent limit even in "run_until_commplete" loop,
    "wait_scheduled_coroutines" coroutine must be called before process exit make sure all coroutine has been done"""
    if __loop is None or __queue is None or __done_queue is None:  # init Queue obj
        init_loop(loop=__loop)

    global __running_count

    def _done_callback(f):
        global __running_count

        exception = f.exception()
        if exception is not None:
            try:
                raise exception
            except exception.__class__:
                logger.exception(exception)

        __running_count -= 1
        __done_queue.put_nowait(f)
        try:
            if __running_count < __concurrent_limit:
                next_coroutine = __queue.get_nowait()
                __running_count += 1
                asyncio.ensure_future(next_coroutine, loop=__loop).add_done_callback(_done_callback)
        except QueueEmpty:
            pass
    if __running_count < __concurrent_limit:
        __running_count += 1
        asyncio.ensure_future(
            timeout_wrapper(coroutine, timeout=timeout), loop=__loop).add_done_callback(_done_callback)
    else:
        __queue.put_nowait(timeout_wrapper(coroutine, timeout=timeout))


def schedule_coroutines(coroutines: typing.Iterable, timeout: float=__timeout) -> None:
    for coroutine in coroutines:
        schedule_coroutine(coroutine, timeout=timeout)


async def wait_scheduled_coroutines():
    """Wait all coroutines schedule by "schedule_coroutine" function"""
    if __loop is None:
        return
    while __running_count > 0 or __done_queue.qsize() > 0:
        await __done_queue.get()


def as_completed(coroutines: typing.Iterable[typing.Coroutine], limit: int=__concurrent_limit, timeout: float=__timeout,
                 loop: typing.Optional[asyncio.AbstractEventLoop]=None
                 )-> typing.Generator[typing.Coroutine, None, None]:
    """Custom as_completed method provide coroutines concurrent limit,
    the "limit" is not shared with "schedule_coroutine" function"""
    coroutines = iter(coroutines)

    queue = Queue(loop=loop)
    todo = []

    def _done_callback(f):
        queue.put_nowait(f)
        todo.remove(f)
        try:
            nf = asyncio.ensure_future(next(coroutines))
            nf.add_done_callback(_done_callback)
            todo.append(nf)
        except StopIteration:
            pass

    async def _wait_for_one():
        f = await queue.get()
        return f.result()

    if limit <= 0:
        fs = {asyncio.ensure_future(timeout_wrapper(cor, timeout=timeout), loop=loop) for cor in coroutines}
    else:
        fs = {asyncio.ensure_future(timeout_wrapper(cor, timeout=timeout), loop=loop)
              for cor in islice(coroutines, 0, limit)}
    for f in fs:
        f.add_done_callback(_done_callback)
        todo.append(f)

    while len(todo) > 0 or queue.qsize() > 0:
        yield _wait_for_one()


async def as_completed_with_async(
        coroutines: typing.Iterable[typing.Coroutine],
        limit: int=__concurrent_limit, timeout: float=__timeout, ignore_exception: bool=True,
        )-> typing.AsyncGenerator[typing.Any, None]:
    """as_completed`s async version, catch and log exception inside"""
    for coro in as_completed(coroutines, limit=limit, timeout=timeout, loop=asyncio.get_event_loop()):
        try:
            yield await coro
        except Exception as e:
            if ignore_exception:
                logger.exception(e)
            else:
                raise e
