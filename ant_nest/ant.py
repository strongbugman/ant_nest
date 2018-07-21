import typing
import asyncio
import abc
import itertools
import logging
import time
import random
from collections import defaultdict
from asyncio.queues import Queue, QueueEmpty
from itertools import islice

import aiohttp
from aiohttp.client import DEFAULT_TIMEOUT
from aiohttp import ClientSession
from yarl import URL
from tenacity import retry
from tenacity.retry import retry_if_result, retry_if_exception_type
from tenacity.wait import wait_fixed
from tenacity.stop import stop_after_attempt

from .pipelines import Pipeline
from .things import Request, Response, Item, Things
from .exceptions import ThingDropped

__all__ = ['Ant', 'CliAnt']


class Ant(abc.ABC):
    response_pipelines: typing.List[Pipeline] = []
    request_pipelines: typing.List[Pipeline] = []
    item_pipelines: typing.List[Pipeline] = []
    request_cls = Request
    response_cls = Response
    request_timeout = DEFAULT_TIMEOUT.total
    request_retries = 3
    request_retry_delay = 5
    request_proxies: typing.List[typing.Union[str, URL]] = []
    request_max_redirects = 10
    request_allow_redirects = True
    response_in_stream = False
    connection_limit = 100  # see "TCPConnector" in "aiohttp"
    connection_limit_per_host = 0
    concurrent_limit = 100

    def __init__(
            self, loop: typing.Optional[asyncio.AbstractEventLoop] = None):
        self.loop = loop if loop is not None else asyncio.get_event_loop()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.session: aiohttp.ClientSession = ClientSession(
            response_class=self.response_cls,
            connector=aiohttp.TCPConnector(
                limit=self.connection_limit,
                enable_cleanup_closed=True,
                limit_per_host=self.connection_limit_per_host)
        )
        # coroutine`s concurrency support
        self._queue = Queue(loop=self.loop)
        self._done_queue = Queue(loop=self.loop)
        self._running_count = 0
        self._is_closed = False
        # report var
        self._reports: typing.DefaultDict[
            str, typing.List[int, int]] = defaultdict(lambda: [0, 0])
        self._drop_reports: typing.DefaultDict[
            str, typing.List[int, int]] = defaultdict(lambda: [0, 0])
        self._start_time = time.time()
        self._last_time = self._start_time
        self._report_slot = 60  # report once after one minute by default

    @property
    def name(self):
        return self.__class__.__name__

    @property
    def is_running(self) -> bool:
        return self._running_count > 0

    async def request(self, url: typing.Union[str, URL],
                      method: str = aiohttp.hdrs.METH_GET,
                      params: typing.Optional[dict] = None,
                      headers: typing.Optional[dict] = None,
                      cookies: typing.Optional[dict] = None,
                      data: typing.Optional[
                          typing.Union[typing.AnyStr, typing.Dict, typing.IO]
                      ] = None,
                      proxy: typing.Optional[typing.Union[str, URL]] = None,
                      timeout: typing.Optional[
                          typing.Union[int, float]] = None,
                      retries: typing.Optional[int] = None,
                      response_in_stream: typing.Optional[bool] = None
                      ) -> Response:
        if not isinstance(url, URL):
            url = URL(url)
        if proxy and not isinstance(proxy, URL):
            proxy = URL(proxy)
        elif proxy is None:
            proxy = self.get_proxy()
        if timeout is None:
            timeout = self.request_timeout
        if retries is None:
            retries = self.request_retries
        if response_in_stream is None:
            response_in_stream = self.response_in_stream

        req = self.request_cls(method, url, timeout=timeout, params=params,
                               headers=headers, cookies=cookies, data=data,
                               proxy=proxy,
                               response_in_stream=response_in_stream)
        req = await self._handle_thing_with_pipelines(
            req, self.request_pipelines)
        self.report(req)

        if retries > 0:
            res = await self.make_retry_decorator(
                retries, self.request_retry_delay)(self._request)(req)
        else:
            res = await self._request(req)

        res = await self._handle_thing_with_pipelines(
            res, self.response_pipelines)
        self.report(res)
        return res

    async def collect(self, item: Item) -> None:
        self.logger.debug('Collect item: ' + str(item))
        await self._handle_thing_with_pipelines(item, self.item_pipelines)
        self.report(item)

    async def open(self) -> None:
        self.logger.info('Opening')
        for pipeline in itertools.chain(self.item_pipelines,
                                        self.response_pipelines,
                                        self.request_pipelines):
            obj = pipeline.on_spider_open()
            if asyncio.iscoroutine(obj):
                await obj

    async def close(self) -> None:
        for pipeline in itertools.chain(self.item_pipelines,
                                        self.response_pipelines,
                                        self.request_pipelines):
            obj = pipeline.on_spider_close()
            if asyncio.iscoroutine(obj):
                await obj

        await self.wait_scheduled_coroutines()
        await self.session.close()

        self._is_closed = True
        self.logger.info('Closed')

    @abc.abstractmethod
    async def run(self) -> None:
        """App custom entrance"""

    async def main(self) -> None:
        try:
            await self.open()
            await self.run()
        except Exception as e:
            self.logger.exception(
                'Run ant with ' + e.__class__.__name__)
        try:
            await self.close()
        except Exception as e:
            self.logger.exception(
                'Close ant with ' + e.__class__.__name__)
        # total report
        for name, counts in self._reports.items():
            self.logger.info('Get {:d} {:s} in total'.format(counts[1], name))
        for name, counts in self._drop_reports.items():
            self.logger.info('Drop {:d} {:s} in total'.format(counts[1], name))
        self.logger.info(
            'Run {:s} in {:f} seconds'.format(self.__class__.__name__,
                                              time.time() - self._start_time))

    @staticmethod
    def make_retry_decorator(
            retries: int, delay: float
    ) -> typing.Callable[[typing.Callable], typing.Callable]:
        return retry(wait=wait_fixed(delay),
                     retry=(retry_if_result(lambda res: res.status >= 500) |
                            retry_if_exception_type(
                                exception_types=aiohttp.ClientError)
                            ),
                     stop=stop_after_attempt(retries + 1))

    def get_proxy(self) -> typing.Optional[URL]:
        """Chose a proxy, default by random"""
        try:
            return URL(random.choice(self.request_proxies))
        except IndexError:
            return None

    def schedule_coroutine(self, coroutine: typing.Coroutine) -> None:
        """Like "asyncio.ensure_future", it schedule coroutine in event loop
        and return immediately.

        Call "self.wait_scheduled_coroutines" make sure all coroutine has been
        done.
        """
        def _done_callback(f):
            self._running_count -= 1
            self._done_queue.put_nowait(f)
            try:
                if (self.concurrent_limit == -1 or
                        self._running_count < self.concurrent_limit):
                    next_coroutine = self._queue.get_nowait()
                    self._running_count += 1
                    asyncio.ensure_future(next_coroutine,
                                          loop=self.loop).add_done_callback(
                        _done_callback)
            except QueueEmpty:
                pass

        if self._is_closed:
            self.logger.warning('This pool has be closed!')
            return

        if (self.concurrent_limit == -1 or
                self._running_count < self.concurrent_limit):
            self._running_count += 1
            asyncio.ensure_future(
                coroutine, loop=self.loop).add_done_callback(_done_callback)
        else:
            self._queue.put_nowait(coroutine)

    def schedule_coroutines(
            self, coroutines: typing.Iterable[typing.Coroutine]) -> None:
        """A short way to schedule many coroutines.
        """
        for coroutine in coroutines:
            self.schedule_coroutine(coroutine)

    async def wait_scheduled_coroutines(self):
        """Wait scheduled coroutines to be done, can be called many times.
        """
        while self._running_count > 0 or self._done_queue.qsize() > 0:
            await self._done_queue.get()

    def as_completed(self, coroutines: typing.Iterable[typing.Coroutine],
                     limit: typing.Optional[int] = None
                     ) -> typing.Generator[typing.Coroutine, None, None]:
        """Like "asyncio.as_completed",
        run and iter coroutines out of the pool.

        :param limit: set to "self.concurrent_limit" by default,
        this "limit" is not shared with pool`s limit
        """
        limit = self.concurrent_limit if limit is None else limit

        coroutines = iter(coroutines)
        queue = Queue(loop=self.loop)
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
            fs = {asyncio.ensure_future(
                cor, loop=self.loop) for cor in coroutines}
        else:
            fs = {asyncio.ensure_future(
                cor, loop=self.loop) for cor in islice(coroutines, 0, limit)}
        for f in fs:
            f.add_done_callback(_done_callback)
            todo.append(f)

        while len(todo) > 0 or queue.qsize() > 0:
            yield _wait_for_one()

    async def as_completed_with_async(
            self, coroutines: typing.Iterable[typing.Coroutine],
            limit: typing.Optional[int] = None,
            raise_exception: bool = True,
    ) -> typing.AsyncGenerator[typing.Any, None]:
        """as_completed`s async version, can catch and log exception inside.
        """
        for coro in self.as_completed(coroutines, limit=limit):
            try:
                yield await coro
            except Exception as e:
                if raise_exception:
                    raise e
                else:
                    self.logger.exception(
                        'Get exception {:s} in '
                        '"as_completed_with_async"'.format(str(e)))

    def report(self, thing: Things, dropped: bool = False) -> None:
        now_time = time.time()
        if now_time - self._last_time > self._report_slot:
            self._last_time = now_time
            for name, counts in self._reports.items():
                count = counts[1] - counts[0]
                counts[0] = counts[1]
                self.logger.info(
                    'Get {:d} {:s} in total with {:d}/{:d}s rate'.format(
                        counts[1], name, count, self._report_slot))
            for name, counts in self._drop_reports.items():
                count = counts[1] - counts[0]
                counts[0] = counts[1]
                self.logger.info(
                    'Drop {:d} {:s} in total with {:d}/{:d} rate'.format(
                        counts[1], name, count, self._report_slot))
        report_type = thing.__class__.__name__
        if dropped:
            reports = self._drop_reports
        else:
            reports = self._reports
        counts = reports[report_type]
        counts[1] += 1

    async def _handle_thing_with_pipelines(
            self, thing: Things, pipelines: typing.List[Pipeline]) -> Things:
        """Process thing one by one, break the process chain when get
        exception.
        """
        self.logger.debug('Process thing: ' + str(thing))
        raw_thing = thing
        for pipeline in pipelines:
            try:
                thing = pipeline.process(thing)
                if asyncio.iscoroutine(thing):
                    thing = await thing
            except Exception as e:
                if isinstance(e, ThingDropped):
                    self.report(raw_thing, dropped=True)
                raise e
        return thing

    async def _request(self, req: Request) -> Response:
        if req.proxy is not None:
            # proxy auth not work in one session with many requests,
            # add auth header to fix it
            if req.proxy.scheme == 'http' and req.proxy.user is not None:
                req.headers[aiohttp.hdrs.PROXY_AUTHORIZATION] = \
                    aiohttp.BasicAuth.from_url(req.proxy).encode()

        # cookies in headers, params in url
        req_kwargs = dict(method=req.method, url=req.url, headers=req.headers,
                          data=req.data, timeout=req.timeout, proxy=req.proxy,
                          max_redirects=self.request_max_redirects,
                          allow_redirects=self.request_allow_redirects)
        response = await self.session._request(**req_kwargs)

        if not req.response_in_stream:
            await response.read()
            response.close()
            await response.wait_for_close()
        return response


class CliAnt(Ant):
    """As a http client"""
    async def run(self):
        pass
