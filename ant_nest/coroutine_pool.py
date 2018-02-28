"""
Coroutines tool box
"""
import typing
import logging
import asyncio
from asyncio.queues import Queue, QueueEmpty
from itertools import islice

import async_timeout


def timeout_wrapper(coro_or_func: typing.Union[typing.Coroutine, typing.Callable],
                    timeout: typing.Union[float, int]) -> typing.Union[typing.Coroutine, typing.Callable]:
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


class CoroutinesPool:
    """
    Coroutines concurrent execute pool with API like standard "asyncio.ensure_future" and "asyncio.as_completed'
    """
    def __init__(self, loop: typing.Optional[asyncio.AbstractEventLoop]=None, raise_exception: bool = True,
                 limit: int = -1, timeout: typing.Union[int, float] = -1):
        """
        :param loop: set to "asyncio.get_event_loop()" by default.
        :param raise_exception: raise coroutine`s exception inside (handle by asyncio) or just log it by logging
        :param limit: concurrency coroutines`s count limit, no limit by default.
        :param timeout: global timeout for single one coroutine, no timeout by default.
        """

        if loop is None:
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = loop

        self._timeout = timeout
        self._limit = limit
        self._raise_exception = raise_exception
        self._queue = Queue(loop=self._loop)  # store coroutines waiting for running
        self._done_queue = Queue(loop=self._loop)
        self._running_count = 0  # coroutines running count, less than limit
        self._is_closed = False  # pool status
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def loop(self):
        return self._loop

    @property
    def timeout(self) -> typing.Union[int, float]:
        return self._timeout

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def raise_exception(self) -> bool:
        return self._raise_exception

    @property
    def running_count(self) -> int:
        return self._running_count

    @property
    def is_running(self) -> bool:
        return self._running_count > 0

    @property
    def status(self):
        if self._is_closed:
            status = 'closed'
        elif self.is_running:
            status = 'running'
        else:
            status = 'ready'
        return status

    def reset(self, limit: typing.Optional[int] = None, timeout: typing.Union[int, float, None] = None,
              raise_exception: typing.Optional[bool] = None):
        """Rest limit or timeout or raise_exception, it`s safe to call anytime"""
        self._limit = self._limit if limit is None else limit
        self._timeout = self._timeout if timeout is None else timeout
        self._raise_exception = self._raise_exception if raise_exception is None else raise_exception

    def schedule_coroutine(self, coroutine: typing.Coroutine, timeout: typing.Union[float, int, None] = None) -> None:
        """Like "asyncio.ensure_future", it schedule coroutine in event loop and return immediately.
        Call "self.wait_scheduled_coroutines" make sure all coroutine has been done.

        :param timeout: set to "self._timeout" by default
        """
        timeout = self._timeout if timeout is None else timeout

        def _done_callback(f):
            self._running_count -= 1
            self._done_queue.put_nowait(f)
            try:
                if self._limit == -1 or self._running_count < self._limit:
                    next_coroutine = self._queue.get_nowait()
                    self._running_count += 1
                    asyncio.ensure_future(next_coroutine, loop=self._loop).add_done_callback(_done_callback)
            except QueueEmpty:
                pass
            # handle exception
            exception = f.exception()
            if exception is not None:
                try:
                    raise exception
                except exception.__class__:
                    if self._raise_exception:
                        raise exception
                    else:
                        self.logger.exception(exception)

        if self._is_closed:
            self.logger.warning('This pool has be closed!')
            return

        if self._limit == -1 or self._running_count < self._limit:
            self._running_count += 1
            asyncio.ensure_future(
                timeout_wrapper(coroutine, timeout=timeout), loop=self._loop).add_done_callback(_done_callback)
        else:
            self._queue.put_nowait(timeout_wrapper(coroutine, timeout=timeout))

    def schedule_coroutines(self, coroutines: typing.Iterable[typing.Coroutine],
                            timeout: typing.Union[float, int, None] = None) -> None:
        """A short way to schedule many coroutines.

        :param timeout: set to "self._timeout" by default
        """
        for coroutine in coroutines:
            self.schedule_coroutine(coroutine, timeout=timeout)

    async def wait_scheduled_coroutines(self):
        """Wait scheduled coroutines to be done, can be called many times.
        """
        while self._running_count > 0 or self._done_queue.qsize() > 0:
            await self._done_queue.get()

    def as_completed(self, coroutines: typing.Iterable[typing.Coroutine], limit: typing.Optional[int] = None,
                     timeout: typing.Union[int, float, None] = None)-> typing.Generator[typing.Coroutine, None, None]:
        """Like "asyncio.as_completed", run and iter coroutines out of the pool.

        :param timeout: set to "self._timeout" by default
        :param limit: set to "self._limit" by default, this "limit" is not shared with pool`s limit
        """
        limit = self._limit if limit is None else limit
        timeout = self._timeout if timeout is None else timeout

        coroutines = iter(coroutines)
        queue = Queue(loop=self._loop)
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
            fs = {asyncio.ensure_future(timeout_wrapper(cor, timeout=timeout), loop=self._loop) for cor in coroutines}
        else:
            fs = {asyncio.ensure_future(timeout_wrapper(cor, timeout=timeout), loop=self._loop)
                  for cor in islice(coroutines, 0, limit)}
        for f in fs:
            f.add_done_callback(_done_callback)
            todo.append(f)

        while len(todo) > 0 or queue.qsize() > 0:
            yield _wait_for_one()

    async def as_completed_with_async(
            self, coroutines: typing.Iterable[typing.Coroutine], limit: typing.Optional[int] = None,
            timeout: typing.Union[int, float, None] = None, raise_exception: typing.Optional[bool] = None,
    )-> typing.AsyncGenerator[typing.Any, None]:
        """as_completed`s async version, can catch and log exception inside.

        :param timeout: set to "self._timeout" by default
        :param limit: set to "self._limit" by default, this "limit" is not shared with pool`s limit
        :param raise_exception: set to "self._raise_exception" by default
        """
        raise_exception = self._raise_exception if raise_exception is None else raise_exception

        for coro in self.as_completed(coroutines, limit=limit, timeout=timeout):
            try:
                yield await coro
            except Exception as e:
                if raise_exception:
                    raise e
                else:
                    self.logger.exception(e)

    async def close(self):
        await self.wait_scheduled_coroutines()
        self._is_closed = True

    def __repr__(self):
        return '{:s}({:s}) with {:d} running coroutines count'.format(
            self.__class__.__name__, self.status, self._running_count)

    def __del__(self):
        if not self._is_closed:
            if self._running_count > 0 or self._done_queue.qsize() > 0:
                self.logger.error('Leave with running coroutines!')
            else:
                self.logger.warning('Leave without pool closed!')


__all__ = ['CoroutinesPool', 'timeout_wrapper']


