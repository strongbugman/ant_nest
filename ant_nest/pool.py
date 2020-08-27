"""
Background coroutine pool with limit
"""
import typing
import asyncio
from asyncio.queues import Queue, QueueEmpty
import logging
from itertools import islice


__all__ = ["Pool"]


class Pool:
    def __init__(self, limit: int = 50):
        self._loop = asyncio.get_event_loop()
        self._limit = limit
        self.logger = logging.getLogger(self.__class__.__name__)
        self._pending_queue: Queue = Queue()
        self._done_queue: Queue = Queue()
        self._running_count = 0
        self._closed = False

    def spawn(self, coroutine: typing.Awaitable):
        """Like "asyncio.ensure_future", with concurrent limit

        Call "self.done" make sure all coroutine has been
        done.
        """
        if self._closed:
            self.logger.warning("This ant has be closed!")
            return

        if self._limit == -1 or self._running_count < self._limit:
            self._running_count += 1
            asyncio.ensure_future(coroutine, loop=self._loop).add_done_callback(
                self._done_callback
            )
        else:
            self._pending_queue.put_nowait(coroutine)

    @property
    def closed(self):
        return self._closed

    @property
    def done(self):
        return not (
            self._running_count
            or self._done_queue.qsize()
            or self._pending_queue.qsize()
        )

    async def wait_done(self):
        """Wait all coroutine to be done"""
        while not self.done:
            await self._done_queue.get()

    def close(self):
        self._closed = True

    async def wait_close(self):
        """Graceful close"""
        await self.wait_done()
        self.close()
        await self.wait_done()  # wait again avoid concurrent competition

    def as_completed(
        self,
        coros: typing.Iterable[typing.Awaitable],
        limit: int = 50,
    ) -> typing.Generator[typing.Awaitable, None, None]:
        """Like "asyncio.as_completed",
        run and iter coros out of pool.

        :param limit: set to "settings.JOB_LIMIT" by default,
        this "limit" is not shared with pool`s limit
        """
        coros = iter(coros)
        queue: Queue = Queue()
        todo: typing.List[asyncio.Future] = []

        def _done_callback(f):
            queue.put_nowait(f)
            todo.remove(f)
            try:
                nf = asyncio.ensure_future(next(coros))
                nf.add_done_callback(_done_callback)
                todo.append(nf)
            except StopIteration:
                pass

        async def _wait_for_one():
            return (await queue.get()).result()

        if limit <= 0:
            fs = {asyncio.ensure_future(cor, loop=self._loop) for cor in coros}
        else:
            fs = {
                asyncio.ensure_future(cor, loop=self._loop)
                for cor in islice(coros, 0, limit)
            }
        for f in fs:
            f.add_done_callback(_done_callback)
            todo.append(f)

        while len(todo) > 0 or queue.qsize() > 0:
            yield _wait_for_one()

    async def as_completed_with_async(
        self,
        coros: typing.Iterable[typing.Awaitable],
        limit: int = 50,
        raise_exception: bool = True,
    ) -> typing.AsyncGenerator[typing.Any, None]:
        """as_completed`s async version, can catch and log exception inside."""
        for coro in self.as_completed(coros, limit=limit):
            try:
                yield await coro
            except Exception as e:
                if raise_exception:
                    raise e
                else:
                    self.logger.exception(
                        "Get exception {:s} in "
                        '"as_completed_with_async"'.format(str(e))
                    )

    def _done_callback(self, f):
        self._running_count -= 1
        self._done_queue.put_nowait(f)
        try:
            if not self.closed and (
                self._limit == -1 or self._running_count < self._limit
            ):
                next_coroutine = self._pending_queue.get_nowait()
                self._running_count += 1
                asyncio.ensure_future(
                    next_coroutine, loop=self._loop
                ).add_done_callback(self._done_callback)
        except QueueEmpty:
            pass
