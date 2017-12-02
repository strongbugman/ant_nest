from typing import Any, Optional, Iterator, List, Coroutine, Union
import abc
import itertools
import logging
import asyncio
from asyncio.queues import Queue, QueueEmpty
from itertools import islice

import aiohttp
from aiohttp.client_reqrep import ClientResponse
from yarl import URL

from .pipelines import Pipeline
from .things import Request, Response, Item, Things
from .exceptions import ThingDropped


class Ant(abc.ABC):
    response_pipelines = [Pipeline()]  # type: List[Pipeline]
    request_pipelines = [Pipeline()]  # type: List[Pipeline]
    item_pipelines = [Pipeline()]  # type: List[Pipeline]

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        # for background coroutines - coroutines schedule by self.ensure_future method
        self.__queue = Queue()  # background coroutines waiting for execution
        self.__done_queue = Queue()  # execution completed background coroutines
        self.__count = 0  # backgroud coroutines be executed
        self.__done_count = 0  # backgroud coroutines completed
        self.__limit = 1000

    async def request(self, url: Union[str, URL], method='GET', params: Optional[dict]=None, headers: Optional[dict]=None,
                      cookies: Optional[dict]=None, data: Optional[Any]=None,
                      proxy: Optional[str]=None) -> Response:
        self.logger.debug('{:s} {:s}'.format(method, str(url)))
        kwargs = locals()
        kwargs.pop('self')

        req = Request(**kwargs)
        req = await self._handle_thing_with_pipelines(req, self.request_pipelines)

        res = await self._request(req)

        res = await self._handle_thing_with_pipelines(res, self.response_pipelines)
        return res

    async def collect(self, item: Item) -> None:
        self.logger.debug('Collect item: ' + str(item))
        await self._handle_thing_with_pipelines(item, self.item_pipelines)

    async def open(self) -> None:
        self.logger.info('Opening')
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            obj = pipeline.on_spider_open(self)
            if isinstance(obj, Coroutine):
                await obj

    async def close(self) -> None:
        for pipeline in itertools.chain(self.item_pipelines, self.response_pipelines, self.request_pipelines):
            obj = pipeline.on_spider_close(self)
            if isinstance(obj, Coroutine):
                await obj
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

    def ensure_future(self, coroutine: Coroutine) -> None:
        """Custom ensure_future method provide coroutines limit and watch dog"""

        def _done_callback(f):
            self.__done_count += 1
            self.__done_queue.put_nowait(f)
            try:
                running_count = self.__count - self.__done_count
                if running_count < self.__limit:
                    next_coroutine = self.__queue.get_nowait()
                    self.__count += 1
                    asyncio.ensure_future(next_coroutine).add_done_callback(_done_callback)
            except QueueEmpty:
                pass

        running_count = self.__count - self.__done_count
        if running_count < self.__limit:
            self.__count += 1
            asyncio.ensure_future(coroutine).add_done_callback(_done_callback)
        else:
            self.__queue.put_nowait(coroutine)

    def as_completed(self, coroutines: Union[Iterator[Coroutine], List],
                     limit: int=-1) -> Iterator[Coroutine]:
        """Custom as_completed method provide coroutines limit"""
        if limit == -1:
            limit = self.__limit
        if isinstance(coroutines, List):
            coroutines = Iterator(coroutines)

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
            fs = {asyncio.ensure_future(cor) for cor in coroutines}
        else:
            fs = {asyncio.ensure_future(cor) for cor in islice(coroutines, 0, limit)}
        for f in fs:
            f.add_done_callback(_done_callback)
            todo.append(f)

        while len(todo) > 0:
            yield _wait_for_one()

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
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.request(**kwargs) as aio_response:
                await aio_response.read()
        return self._convert_response(aio_response, req)

    def _convert_response(self, aio_response: ClientResponse, request: Request) -> Response:
        return Response(request, aio_response.status, aio_response._content,
                        headers=aio_response.headers, cookies=aio_response.cookies,
                        encoding=aio_response._get_encoding())
