import os
import sys
import typing
import abc
import itertools
import logging
import time

import httpx

from .pipelines import Pipeline
from .items import Item
from .exceptions import Dropped
from .pool import Pool
from .reporter import Reporter
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

    def __init__(self):
        self._start_time = time.time()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.client = httpx.AsyncClient(**settings.HTTPX_CONFIG)
        self.pool = Pool(**settings.POOL_CONFIG)
        self.reporter = Reporter(**settings.REPORTER)

    @property
    def name(self):
        return self.__class__.__name__

    async def request(
        self,
        url: str,
        method: str = "get",
        data: httpx._models.RequestData = None,
        files: httpx._models.RequestFiles = None,
        json: typing.Any = None,
        params: httpx._models.QueryParamTypes = None,
        headers: httpx._models.HeaderTypes = None,
        cookies: httpx._models.CookieTypes = None,
        auth: httpx._auth.Auth = None,
        stream: bool = False,
    ) -> httpx.Response:
        request: httpx.Request = self.client.build_request(
            method,
            url,
            params=params,
            headers=headers,
            cookies=cookies,
            data=data,
            files=files,
            json=json,
        )
        request = await self._pipe(request, self.request_pipelines)
        self.reporter.report(request)

        response = await utils.retry(settings.HTTP_RETRIES, settings.HTTP_RETRY_DELAY)(
            self.client.send
        )(request, auth=auth, stream=stream)

        response = await self._pipe(response, self.response_pipelines)
        self.reporter.report(response)

        return response

    async def collect(self, item: Item):
        self.logger.debug("Collect item: " + str(item))
        await self._pipe(item, self.item_pipelines)
        self.reporter.report(item)

    async def open(self):
        self.logger.info("Opening")
        for pipeline in itertools.chain(
            self.item_pipelines, self.response_pipelines, self.request_pipelines
        ):
            await utils.run_cor_func(pipeline.on_spider_open)

    async def close(self):
        await self.pool.wait_close()

        for pipeline in itertools.chain(
            self.item_pipelines, self.response_pipelines, self.request_pipelines
        ):
            await utils.run_cor_func(pipeline.on_spider_close)

        await self.client.aclose()

        self.reporter.close()

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
        self.logger.info(
            "Run {:s} in {:f} seconds".format(
                self.__class__.__name__, time.time() - self._start_time
            )
        )

    async def _pipe(
        self,
        obj: typing.Union[Item, httpx.Request, httpx.Response],
        pipelines: typing.List[Pipeline],
    ) -> typing.Any:
        self.logger.debug("Process obj: " + str(obj))
        raw_obj = obj
        for pipeline in pipelines:
            try:
                obj = await utils.run_cor_func(pipeline.process, obj)
            except Exception as e:
                if isinstance(e, Dropped):
                    self.reporter.report(raw_obj, dropped=True)
                raise e
        return obj


class CliAnt(Ant):
    """As a http client"""

    async def run(self):
        pass
