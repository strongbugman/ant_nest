from typing import Optional, List, Coroutine, Union, Dict, Callable, AnyStr, IO
import abc
import itertools
import logging

import aiohttp
from aiohttp.client_reqrep import ClientResponse
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
from .exceptions import ThingDropped
from . import queen


__all__ = ['Ant']


class Ant(abc.ABC):
    response_pipelines = []  # type: List[Pipeline]
    request_pipelines = []  # type: List[Pipeline]
    item_pipelines = []  # type: List[Pipeline]
    request_timeout = DEFAULT_TIMEOUT
    request_retries = 3
    request_retry_delay = 5
    request_proxy = None  # type: Optional[str]
    request_max_redirects = 10
    request_allow_redirects = True

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sessions = {}  # type: Dict[str, ClientSession]

    async def request(self, url: Union[str, URL], method='GET', params: Optional[dict]=None,
                      headers: Optional[dict]=None, cookies: Optional[dict]=None,
                      data: Optional[Union[AnyStr, Dict, IO]]=None,
                      ) -> Response:
        req = Request(url, method=method, params=params, headers=headers, cookies=cookies, data=data)
        req = await self._handle_thing_with_pipelines(req, self.request_pipelines, timeout=self.request_timeout)

        request_function = queen.timeout_wrapper(self._request, timeout=self.request_timeout)
        retries = self.request_retries
        if retries > 0:
            res = await self.make_retry_decorator(retries, self.request_retry_delay)(request_function)(req)
        else:
            res = await request_function(req)

        res = await self._handle_thing_with_pipelines(res, self.response_pipelines, timeout=self.request_timeout)
        return res

    async def collect(self, item: Item) -> None:
        self.logger.debug('Collect item: ' + str(item))
        await self._handle_thing_with_pipelines(item, self.item_pipelines)

    async def open(self) -> None:
        self.logger.info('Opening')
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            try:
                obj = pipeline.on_spider_open()
                if isinstance(obj, Coroutine):
                    await obj
            except Exception as e:
                self.logger.exception('Open pipelines with ' + e.__class__.__name__)

    async def close(self) -> None:
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            try:
                obj = pipeline.on_spider_close()
                if isinstance(obj, Coroutine):
                    await obj
            except Exception as e:
                self.logger.exception('Close pipelines with ' + e.__class__.__name__)
        # close cached sessions
        for session in self.sessions.values():
            await session.close()
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
        # wait scheduled coroutines before wait "close" method
        await queen.wait_scheduled_coroutines()
        await self.close()
        await queen.wait_scheduled_coroutines()

    @staticmethod
    def make_retry_decorator(retries: int, delay: float) -> Callable[[Callable], Callable]:
        return retry(wait=wait_fixed(delay),
                     retry=(retry_if_result(lambda res: res.status >= 500) | retry_if_exception_type()),
                     stop=stop_after_attempt(retries + 1))

    async def _handle_thing_with_pipelines(self, thing: Things, pipelines: List[Pipeline],
                                           timeout=DEFAULT_TIMEOUT) -> Things:
        """Process thing one by one, break the process chain when get "None" or exception
        :raise ThingDropped"""
        self.logger.debug('Process thing: ' + str(thing))
        raw_thing = thing
        for pipeline in pipelines:
            thing = pipeline.process(thing)
            if isinstance(thing, Coroutine):
                with async_timeout.timeout(timeout):
                    thing = await thing
            if thing is None:
                raise ThingDropped('"{:s}" is dropped by {:s}'.format(str(raw_thing), pipeline.__class__.__name__))
        return thing

    async def _request(self, req: Request) -> Response:
        kwargs = {k: getattr(req, k) for k in req.__slots__}
        cookies = kwargs.pop('cookies')
        kwargs['proxy'] = self.request_proxy
        kwargs['max_redirects'] = self.request_max_redirects
        kwargs['allow_redirects'] = self.request_allow_redirects

        # proxy auth not work when one session with many requests
        if self.request_proxy is not None and URL(self.request_proxy).user is not None:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.request(**kwargs) as aio_response:
                    await aio_response.read()
                return self._convert_response(aio_response, req)

        host = req.url.host
        if host not in self.sessions:
            session = aiohttp.ClientSession(cookies=cookies)
            self.sessions[host] = session
        else:
            session = self.sessions[host]
            if cookies is not None:
                session.cookie_jar.update_cookies(cookies)

        async with session.request(**kwargs) as aio_response:
            await aio_response.read()
        return self._convert_response(aio_response, req)

    @staticmethod
    def _convert_response(aio_response: ClientResponse, request: Request) -> Response:
        return Response(request, aio_response.status, aio_response._content,
                        headers=aio_response.headers, cookies=aio_response.cookies,
                        encoding=aio_response._get_encoding())
