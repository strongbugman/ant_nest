from typing import Any, Optional, Iterator, Generator, List, Coroutine, Union, Dict
import abc
import itertools
import logging
import asyncio
from asyncio.queues import Queue, QueueEmpty
from itertools import islice
import async_timeout

import aiohttp
from aiohttp.client_reqrep import ClientResponse
from aiohttp import ClientSession
from yarl import URL

from .pipelines import Pipeline
from .things import Request, Response, Item, Things
from .exceptions import ThingDropped


DEFAULT_VALUE = -1


class Ant(abc.ABC):
    response_pipelines = [Pipeline()]  # type: List[Pipeline]
    request_pipelines = [Pipeline()]  # type: List[Pipeline]
    item_pipelines = [Pipeline()]  # type: List[Pipeline]

    CONCURRENT_LIMIT = 30  # backgroud coroutines concurrent limit
    COROUTINE_TIMEOUT = 180

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.sessions = {}  # type: Dict[str, ClientSession]
        # for background coroutines - coroutines schedule by self.ensure_future method
        self.__queue = Queue()  # background coroutines waiting for execution
        self.__done_queue = Queue()  # execution completed background coroutines
        self.__count = 0  # backgroud coroutines be executed
        self.__done_count = 0  # backgroud coroutines completed

    async def request(self, url: Union[str, URL], method='GET', params: Optional[dict]=None,
                      headers: Optional[dict]=None, cookies: Optional[dict]=None, data: Optional[Any]=None,
                      proxy: Optional[str]=None, timeout: int=DEFAULT_VALUE) -> Response:
        self.logger.debug('{:s} {:s}'.format(method, str(url)))
        kwargs = locals()
        kwargs.pop('self')
        timeout = kwargs.pop('timeout')

        req = Request(**kwargs)
        req = await self.timeout_wrapper(self._handle_thing_with_pipelines(req, self.request_pipelines), timeout=timeout)

        res = await self.timeout_wrapper(self._request(req), timeout=timeout)

        res = await self.timeout_wrapper(self._handle_thing_with_pipelines(res, self.response_pipelines),
                                         timeout=timeout)
        return res

    async def collect(self, item: Item, timeout: int=DEFAULT_VALUE) -> None:
        self.logger.debug('Collect item: ' + str(item))
        await self.timeout_wrapper(self._handle_thing_with_pipelines(item, self.item_pipelines), timeout=timeout)

    async def open(self, timeout: int=DEFAULT_VALUE) -> None:
        self.logger.info('Opening')
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            obj = pipeline.on_spider_open(self)
            if isinstance(obj, Coroutine):
                await self.timeout_wrapper(obj, timeout=timeout)

    async def close(self, timeout: int=DEFAULT_VALUE) -> None:
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            obj = pipeline.on_spider_close(self)
            if isinstance(obj, Coroutine):
                await self.timeout_wrapper(obj, timeout=timeout)
        for session in self.sessions.values():
            await session.close()
        self.logger.info('Closed')

    @abc.abstractmethod
    async def run(self) -> None:
        """App custom entrance"""

    async def main(self) -> None:
        try:
            await self.open()
            await self.run()
            await self.__run_until_complete()
            await self.close()
        except Exception as e:
            self.logger.exception('Run main coroutine with ' + e.__class__.__name__)

    def ensure_future(self, coroutine: Coroutine, timeout: int=DEFAULT_VALUE) -> None:
        """Custom ensure_future method provide coroutines concurrent limit and watch dog"""
        if timeout == DEFAULT_VALUE:
            timeout = self.COROUTINE_TIMEOUT

        def _done_callback(f):
            exception = f.exception()
            if exception is not None:
                try:
                    raise exception
                except exception.__class__:
                    self.logger.exception(exception)

            self.__done_count += 1
            self.__done_queue.put_nowait(f)
            try:
                running_count = self.__count - self.__done_count
                if running_count < self.CONCURRENT_LIMIT:
                    next_coroutine = self.__queue.get_nowait()
                    self.__count += 1
                    asyncio.ensure_future(next_coroutine).add_done_callback(_done_callback)
            except QueueEmpty:
                pass

        running_count = self.__count - self.__done_count
        if running_count < self.CONCURRENT_LIMIT:
            self.__count += 1
            asyncio.ensure_future(self.timeout_wrapper(coroutine, timeout=timeout)).add_done_callback(_done_callback)
        else:
            self.__queue.put_nowait(self.timeout_wrapper(coroutine, timeout=timeout))

    def as_completed(self, coroutines: Union[Iterator[Coroutine], List[Coroutine]],
                     limit: int=DEFAULT_VALUE, timeout: int=DEFAULT_VALUE) -> Generator[Coroutine, None, None]:
        """Custom as_completed method provide coroutines concurrent limit"""
        if limit == DEFAULT_VALUE:
            limit = self.CONCURRENT_LIMIT
        if timeout == DEFAULT_VALUE:
            timeout = self.COROUTINE_TIMEOUT

        if isinstance(coroutines, List):
            coroutines = iter(coroutines)

        queue = Queue()
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
            fs = {asyncio.ensure_future(self.timeout_wrapper(cor, timeout=timeout)) for cor in coroutines}
        else:
            fs = {asyncio.ensure_future(self.timeout_wrapper(cor, timeout=timeout))
                  for cor in islice(coroutines, 0, limit)}
        for f in fs:
            f.add_done_callback(_done_callback)
            todo.append(f)

        while len(todo) > 0:
            yield _wait_for_one()

    async def timeout_wrapper(self, coroutine: Coroutine, timeout: int=DEFAULT_VALUE):
        if timeout == DEFAULT_VALUE:
            timeout = self.COROUTINE_TIMEOUT
        if timeout > 0:
            with async_timeout.timeout(timeout):
                return await coroutine
        else:
            return await coroutine

    async def __run_until_complete(self) -> None:
        """Watch dog,  wait all background coroutines to be completed"""
        while self.__done_count != self.__count:
            await self.__done_queue.get()

    async def _handle_thing_with_pipelines(self, thing: Things, pipelines: List[Pipeline]) -> Optional[Things]:
        """Process thing one by one, break the process chain when get None
        :raise ThingProcessError"""
        self.logger.debug('Process thing: ' + str(thing))
        raw_thing = thing
        for pipeline in pipelines:
            thing = pipeline.process(self, thing)
            if isinstance(thing, Coroutine):
                thing = await thing
            if thing is None:
                msg = 'The thing {:s} is dropped by {:s}'.format(str(raw_thing),
                                                                 pipeline.__class__.__name__)
                self.logger.warning(msg)
                raise ThingDropped(msg)
        return thing

    async def _request(self, req: Request) -> Response:
        kwargs = {k: getattr(req, k) for k in req.__slots__}
        cookies = kwargs.pop('cookies')

        # proxy auth not work in one session with many requests
        proxy_with_auth = False
        if req.proxy is not None and URL(req.proxy).user is not None:
            proxy_with_auth = True

        host = req.url.host
        if host not in self.sessions or proxy_with_auth:
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
