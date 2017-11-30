from typing import Optional, List, Tuple
import logging

from .things import Things, Response, Request, Item


class ThingProcessError(Exception):
    """Raise when one thing is None"""


class Pipeline:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    async def on_spider_open(self, ant: '.ant_nest.Ant') -> None:
        """Call when ant open, method or coroutine"""

    async def on_spider_close(self, ant: '.ant_nest.Ant') -> None:
        """Call when ant close, method or coroutine"""

    async def process(self, ant: '.ant_nest.ant', thing: Things) -> Optional[Things]:
        """method or coroutine"""
        return thing


class ReportPipeline(Pipeline):
    def __init__(self):
        self.count = 0
        self.report_type = None
        super().__init__()

    def process(self, ant: '.ant_nest.ant', thing: Things) -> Things:
        if self.report_type is None:
            self.report_type = thing.__class__.__name__
        self.count += 1

    def on_spider_close(self, ant: '.ant_nest.Ant'):
        self.logger.info('Get {:d} {:s} in total'.format(self.count, self.report_type))


# Response pipelines
class ResponseFilterErrorPipeline(Pipeline):
    def process(self, ant: '.ant_nest.Ant', thing: Response) -> Optional[Response]:
        if thing.status >= 400:
            self.logger.warning('Response: {:s} has bean dropped because http status {:d}'.format(str(thing),
                                                                                                  thing.status))
            return None
        else:
            return thing


class ResponseRetryPipeline(Pipeline):
    """This pipeline should be in front of the pipeline chain"""
    def __init__(self, retries=3):
        self.retries = retries
        super().__init__()

    async def process(self, ant: '.ant_nest.ant', thing: Response) -> Optional[Response]:
        retries = self.retries
        while retries >= 0:
            if thing.status >= 400:
                self.logger.debug('Retry {:s} because http status {:d}'.format(str(thing.request), thing.status))
                thing = await ant._request(thing.request)
            else:
                return thing
            retries -= 1
        self.logger.warning('{:d} reties failed for {:s}'.format(self.retries, thing))
        return thing


# Request pipelines
class RequestNoRedirectsPipeline(Pipeline):
    def process(self, ant: '.ant_nest.Ant', thing: Request) -> Request:
        thing.allow_redirects = False
        thing.max_redirects = 0
        return thing


class RequestProxyPipeline(Pipeline):
    def __init__(self, proxy: str):
        self.proxy = proxy
        super().__init__()

    def process(self, ant: '.ant_nest.ant', thing: Request) -> Request:
        thing.proxy = self.proxy
        return thing


class RequestDuplicateFilterPipeline(Pipeline):
    def __init__(self):
        self.__request_urls = set()
        super().__init__()

    def process(self, ant: '.ant_nest.ant', thing: Request) -> Optional[Request]:
        if thing.url in self.__request_urls:
            return None
        else:
            self.__request_urls.add(thing.url)
            return thing


# Item pipelines
class ItemPrintPipeline(Pipeline):
    def process(self, ant: '.ant_nest.ant', thing: Item) -> Item:
        print(thing)
        return thing


class ItemValidatePipeline(Pipeline):
    def process(self, ant: '.ant_nest.ant', thing: Item) -> Item:
        thing.validate()
        return thing


class ItemFieldReplacePipeline(Pipeline):
    def __init__(self, fields: List[str], excess_chars: Tuple[str]=('\r', '\n', '\t')):
        self.fields = fields
        self.excess_chars = excess_chars
        super().__init__()

    def process(self, ant: '.ant_nest.ant', thing: Item) -> Item:
        for field in self.fields:
            for char in self.excess_chars:
                if 'field' in thing and isinstance(thing['field'], str):
                    thing[field] = thing[field].replace(char, '')
        return thing
