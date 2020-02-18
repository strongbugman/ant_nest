import os
import sys
import typing
import asyncio
import abc
import itertools
import logging
import time
from collections import defaultdict
from asyncio.queues import Queue, QueueEmpty
from itertools import islice

import httpx

from .pipelines import Pipeline
from .things import Item
from .exceptions import ThingDropped
from . import utils

pwd = os.getcwd()
if os.path.exists(os.path.join(pwd, "settings.py")):
    sys.path.append(pwd)
    import settings
else:
    from . import _settings_example as settings

__all__ = ["Ant", "CliAnt"]


class Ant(abc.ABC):
    response_pipelines: typing.List[Pipeline] = []
    request_pipelines: typing.List[Pipeline] = []
    item_pipelines: typing.List[Pipeline] = []

    def __init__(self, loop: typing.Optional[asyncio.AbstractEventLoop] = None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._http_client = httpx.Client(**settings.HTTPX_CONFIG)
        # background coroutine job config
        self._queue: Queue = Queue(loop=self.loop)
        self._done_queue: Queue = Queue(loop=self.loop)
        self._running_count = 0
        self._is_closed = False
        # report var
        self._reports: typing.DefaultDict[str, typing.List[int]] = defaultdict(
            lambda: [0, 0]
        )
        self._drop_reports: typing.DefaultDict[str, typing.List[int]] = defaultdict(
            lambda: [0, 0]
        )
        self._start_time = time.time()
        self._last_time = self._start_time
        self._report_slot = 60  # report once after one minute by default

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def is_running(self) -> bool:
        return self._running_count > 0

    async def request(
        self,
        url: str,
        method: str = "get",
        data: httpx.models.RequestData = None,
        files: httpx.models.RequestFiles = None,
        json: typing.Any = None,
        params: httpx.models.QueryParamTypes = None,
        headers: httpx.models.HeaderTypes = None,
        cookies: httpx.models.CookieTypes = None,
        auth: httpx.models.AuthTypes = None,
        stream: bool = False,
    ) -> httpx.Response:
        request: httpx.Request = self._http_client.build_request(
            method,
            url,
            params=params,
            headers=headers,
            cookies=cookies,
            data=data,
            files=files,
            json=json,
        )
        request = await self._handle_thing_with_pipelines(
            request, self.request_pipelines
        )
        self.report(request)

        response = await utils.retry(settings.HTTP_RETRIES, settings.HTTP_RETRY_DELAY)(
            self._http_client.send
        )(request, auth=auth, stream=stream)
        if not stream:
            await response.read()

        response = await self._handle_thing_with_pipelines(
            response, self.response_pipelines
        )
        self.report(response)

        return response

    async def collect(self, item: Item):
        self.logger.debug("Collect item: " + str(item))
        await self._handle_thing_with_pipelines(item, self.item_pipelines)
        self.report(item)

    async def open(self):
        self.logger.info("Opening")
        for pipeline in itertools.chain(
            self.item_pipelines, self.response_pipelines, self.request_pipelines
        ):
            await utils.run_cor_func(pipeline.on_spider_open)

    async def close(self):
        await self.wait_scheduled_tasks()

        for pipeline in itertools.chain(
            self.item_pipelines, self.response_pipelines, self.request_pipelines
        ):
            await utils.run_cor_func(pipeline.on_spider_close)

        await self._http_client.close()

        self._is_closed = True
        self.logger.info("Closed")

    @abc.abstractmethod
    async def run(self):
        """App custom entrance"""

    async def main(self):
        with utils.suppress(self.logger):
            await self.open()
            await self.run()
        with utils.suppress(self.logger):
            await self.close()
        # total report
        for name, counts in self._reports.items():
            self.logger.info("Get {:d} {:s} in total".format(counts[1], name))
        for name, counts in self._drop_reports.items():
            self.logger.info("Drop {:d} {:s} in total".format(counts[1], name))
        self.logger.info(
            "Run {:s} in {:f} seconds".format(
                self.__class__.__name__, time.time() - self._start_time
            )
        )

    def schedule_task(self, coroutine: typing.Awaitable):
        """Like "asyncio.ensure_future", with concurrent count limit

        Call "self.wait_scheduled_tasks" make sure all task has been
        done.
        """

        def _done_callback(f):
            self._running_count -= 1
            self._done_queue.put_nowait(f)
            try:
                if settings.JOB_LIMIT == -1 or self._running_count < settings.JOB_LIMIT:
                    next_coroutine = self._queue.get_nowait()
                    self._running_count += 1
                    asyncio.ensure_future(
                        next_coroutine, loop=self.loop
                    ).add_done_callback(_done_callback)
            except QueueEmpty:
                pass

        if self._is_closed:
            self.logger.warning("This ant has be closed!")
            return

        if settings.JOB_LIMIT == -1 or self._running_count < settings.JOB_LIMIT:
            self._running_count += 1
            asyncio.ensure_future(coroutine, loop=self.loop).add_done_callback(
                _done_callback
            )
        else:
            self._queue.put_nowait(coroutine)

    def schedule_tasks(self, coros: typing.Iterable[typing.Awaitable]):
        """A short way to schedule many tasks.
        """
        for coro in coros:
            self.schedule_task(coro)

    async def wait_scheduled_tasks(self):
        """Wait scheduled tasks to be done"""
        while self._running_count > 0 or self._done_queue.qsize() > 0:
            await self._done_queue.get()

    def as_completed(
        self, coros: typing.Iterable[typing.Awaitable], limit: int = settings.JOB_LIMIT,
    ) -> typing.Generator[typing.Awaitable, None, None]:
        """Like "asyncio.as_completed",
        run and iter coros out of pool.

        :param limit: set to "settings.JOB_LIMIT" by default,
        this "limit" is not shared with pool`s limit
        """
        coros = iter(coros)
        queue: Queue = Queue(loop=self.loop)
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
            fs = {asyncio.ensure_future(cor, loop=self.loop) for cor in coros}
        else:
            fs = {
                asyncio.ensure_future(cor, loop=self.loop)
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
        limit: int = settings.JOB_LIMIT,
        raise_exception: bool = True,
    ) -> typing.AsyncGenerator[typing.Any, None]:
        """as_completed`s async version, can catch and log exception inside.
        """
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

    def report(self, thing: typing.Any, dropped: bool = False):
        now_time = time.time()
        if now_time - self._last_time > self._report_slot:
            self._last_time = now_time
            for name, counts in self._reports.items():
                count = counts[1] - counts[0]
                counts[0] = counts[1]
                self.logger.info(
                    "Get {:d} {:s} in total with {:d}/{:d}s rate".format(
                        counts[1], name, count, self._report_slot
                    )
                )
            for name, counts in self._drop_reports.items():
                count = counts[1] - counts[0]
                counts[0] = counts[1]
                self.logger.info(
                    "Drop {:d} {:s} in total with {:d}/{:d} rate".format(
                        counts[1], name, count, self._report_slot
                    )
                )
        report_type = thing.__class__.__name__
        if dropped:
            reports = self._drop_reports
        else:
            reports = self._reports
        counts = reports[report_type]
        counts[1] += 1

    async def _handle_thing_with_pipelines(
        self, thing: typing.Any, pipelines: typing.List[Pipeline]
    ) -> typing.Any:
        self.logger.debug("Process thing: " + str(thing))
        raw_thing = thing
        for pipeline in pipelines:
            try:
                thing = await utils.run_cor_func(pipeline.process, thing)
            except Exception as e:
                if isinstance(e, ThingDropped):
                    self.report(raw_thing, dropped=True)
                raise e
        return thing


class CliAnt(Ant):
    """As a http client"""

    async def run(self):
        pass
