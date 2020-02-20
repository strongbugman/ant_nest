import os
import sys
import typing
import asyncio
import abc
import itertools
import logging
import time
from collections import defaultdict

import httpx

from .pipelines import Pipeline
from .things import Item
from .exceptions import ThingDropped
from .pool import Pool
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
        self.client = httpx.Client(**settings.HTTPX_CONFIG)
        self.pool = Pool(**settings.POOL_CONFIG)
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
        request = await self._handle_thing_with_pipelines(
            request, self.request_pipelines
        )
        self.report(request)

        response = await utils.retry(settings.HTTP_RETRIES, settings.HTTP_RETRY_DELAY)(
            self.client.send
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
        await self.pool.wait_close()

        for pipeline in itertools.chain(
            self.item_pipelines, self.response_pipelines, self.request_pipelines
        ):
            await utils.run_cor_func(pipeline.on_spider_close)

        await self.client.close()

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
