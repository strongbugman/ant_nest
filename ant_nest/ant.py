from typing import Optional, List, Union, Dict, Callable, AnyStr, IO, DefaultDict
import asyncio
import abc
import itertools
import logging
import time
import random
from collections import defaultdict

import aiohttp
from aiohttp.client import DEFAULT_TIMEOUT
from aiohttp import ClientSession
import async_timeout
from yarl import URL
from tenacity import retry
from tenacity.retry import retry_if_result, retry_if_exception_type
from tenacity.wait import wait_fixed
from tenacity.stop import stop_after_attempt

from .pipelines import Pipeline
from .things import Request, Response, Item, Things
from .coroutine_pool import CoroutinesPool, timeout_wrapper
from .exceptions import ThingDropped


__all__ = ['Ant']


class Ant(abc.ABC):
    response_pipelines = []  # type: List[Pipeline]
    request_pipelines = []  # type: List[Pipeline]
    item_pipelines = []  # type: List[Pipeline]
    request_cls = Request
    response_cls = Response
    request_timeout = DEFAULT_TIMEOUT
    request_retries = 3
    request_retry_delay = 5
    request_proxies = []  # type: List[str]
    request_max_redirects = 10
    request_allow_redirects = True
    response_in_stream = False
    connection_limit = 100  # see "TCPConnector" in "aiohttp"
    connection_limit_per_host = 0
    pool_limit = 100
    pool_timeout = DEFAULT_TIMEOUT
    pool_raise_exception = False

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # report var
        self._reports = defaultdict(lambda: [0, 0])  # type: DefaultDict[str, List[int, int]]
        self._drop_reports = defaultdict(lambda: [0, 0])  # type: DefaultDict[str, List[int, int]]
        self._start_time = time.time()
        self._last_time = self._start_time
        self._report_slot = 60  # report once after one minute by default
        self._session = self.make_session()
        self.pool = CoroutinesPool(limit=self.pool_limit, timeout=self.pool_timeout,
                                   raise_exception=self.pool_raise_exception)

    async def request(self, url: Union[str, URL], method='GET', params: Optional[dict]=None,
                      headers: Optional[dict]=None, cookies: Optional[dict]=None,
                      data: Optional[Union[AnyStr, Dict, IO]]=None,
                      ) -> Response:
        if not isinstance(url, URL):
            url = URL(url)
        req = self.request_cls(method, url, params=params, headers=headers, cookies=cookies, data=data)
        req = await self._handle_thing_with_pipelines(req, self.request_pipelines, timeout=self.request_timeout)
        self.report(req)

        request_function = timeout_wrapper(self._request, timeout=self.request_timeout)
        retries = self.request_retries
        if retries > 0:
            res = await self.make_retry_decorator(retries, self.request_retry_delay)(request_function)(req)
        else:
            res = await request_function(req)

        res = await self._handle_thing_with_pipelines(res, self.response_pipelines, timeout=self.request_timeout)
        self.report(res)
        return res

    async def collect(self, item: Item) -> None:
        self.logger.debug('Collect item: ' + str(item))
        await self._handle_thing_with_pipelines(item, self.item_pipelines)
        self.report(item)

    async def open(self) -> None:
        self.logger.info('Opening')
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            try:
                obj = pipeline.on_spider_open()
                if asyncio.iscoroutine(obj):
                    await obj
            except Exception as e:
                self.logger.exception('Open pipelines with ' + e.__class__.__name__)

    async def close(self) -> None:
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            try:
                obj = pipeline.on_spider_close()
                if asyncio.iscoroutine(obj):
                    await obj
            except Exception as e:
                self.logger.exception('Close pipelines with ' + e.__class__.__name__)

        await self._session.close()
        await self.pool.close()

        self.logger.info('Closed')

    @abc.abstractmethod
    async def run(self) -> None:
        """App custom entrance"""

    async def main(self) -> None:
        await self.open()
        try:
            await self.run()
        except Exception as e:
            self.logger.exception('Run ant run`s coroutine with ' + e.__class__.__name__)
        # wait scheduled coroutines before "self.close" coroutine running
        await self.pool.wait_scheduled_coroutines()
        await self.close()
        # total report
        for name, counts in self._reports.items():
            self.logger.info('Get {:d} {:s} in total'.format(counts[1], name))
        for name, counts in self._drop_reports.items():
            self.logger.info('Drop {:d} {:s} in total'.format(counts[1], name))
        self.logger.info('Run {:s} in {:f} seconds'.format(self.__class__.__name__, time.time() - self._start_time))

    @staticmethod
    def make_retry_decorator(retries: int, delay: float) -> Callable[[Callable], Callable]:
        return retry(wait=wait_fixed(delay),
                     retry=(retry_if_result(lambda res: res.status >= 500) | retry_if_exception_type()),
                     stop=stop_after_attempt(retries + 1))

    def make_session(self) -> ClientSession:
        """Create aiohttp`s ClientSession"""
        return ClientSession(
            response_class=self.response_cls, request_class=self.request_cls,
            connector=aiohttp.TCPConnector(limit=self.connection_limit, enable_cleanup_closed=True,
                                           limit_per_host=self.connection_limit_per_host)
        )

    def get_proxy(self) -> Optional[URL]:
        """Chose a proxy, default by random"""
        try:
            return URL(random.choice(self.request_proxies))
        except IndexError:
            return None

    async def _handle_thing_with_pipelines(self, thing: Things, pipelines: List[Pipeline],
                                           timeout=DEFAULT_TIMEOUT) -> Things:
        """Process thing one by one, break the process chain when get "None" or exception
        :raise ThingDropped"""
        self.logger.debug('Process thing: ' + str(thing))
        raw_thing = thing
        for pipeline in pipelines:
            try:
                thing = pipeline.process(thing)
                if asyncio.iscoroutine(thing):
                    with async_timeout.timeout(timeout):
                        thing = await thing
            except Exception as e:
                if isinstance(e, ThingDropped):
                    self.report(raw_thing, dropped=True)
                raise e
        return thing

    async def _request(self, req: Request) -> Response:
        proxy = self.get_proxy()
        # cookies in headers, params in url
        kwargs = dict(method=req.method, url=req.url, headers=req.headers, data=req.data)
        kwargs['proxy'] = proxy
        kwargs['max_redirects'] = self.request_max_redirects
        kwargs['allow_redirects'] = self.request_allow_redirects

        # proxy auth not work when one session with many requests, add auth header to fix it
        if proxy is not None:
            if proxy.scheme == 'http' and proxy.user is not None:
                kwargs['headers'][aiohttp.hdrs.PROXY_AUTHORIZATION] = aiohttp.BasicAuth.from_url(proxy).encode()

        response = await self._session._request(**kwargs)
        if not self.response_in_stream:
            await response.read()
            response.close()
            await response.wait_for_close()
        return response

    def report(self, thing: Things, dropped: bool=False) -> None:
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
