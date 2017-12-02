from typing import Optional, List, Tuple, DefaultDict, Dict, Any
import logging
from collections import defaultdict
import json
import asyncio
import os
import time
import datetime

import aiomysql

from .things import Things, Response, Request, Item
from .exceptions import FiledValidationError


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
        self.last_time = time.time()
        self.last_count = 0
        super().__init__()

    def process(self, ant: '.ant_nest.ant', thing: Things) -> Things:
        if self.report_type is None:
            self.report_type = thing.__class__.__name__
        self.count += 1
        now_time = time.time()
        if now_time - self.last_time > 60:
            count = self.count - self.last_count
            self.logger.info('Get {:d} {:s} in total with {:d}/min'.format(self.count, self.report_type, count))
            self.last_time = now_time
            self.last_count = self.count
        return thing

    def on_spider_close(self, ant: '.ant_nest.Ant'):
        if self.report_type is not None:
            self.logger.info('Get {:d} {:s} in total'.format(self.count, self.report_type))


# Response pipelines
class ResponseFilterErrorPipeline(Pipeline):
    def process(self, ant: '.ant_nest.Ant', thing: Response) -> Optional[Response]:
        if thing.status >= 400:
            self.logger.warning('Response: {:s} has bean dropped'.format(str(thing)))
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
                self.logger.info('Retry {:s} because http status {:d}'.format(str(thing.request), thing.status))
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


class RequestUserAgentPipeline(Pipeline):
    user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/44.0.2403.157 ' \
                 'Safari/537.36'

    def __init__(self, user_agent=user_agent):
        super().__init__()
        self.user_agent = user_agent

    def process(self, ant, thing):
        if thing.headers is None:
            thing.headers = {}
        thing.headers['User-Agent'] = self.user_agent
        return thing


# Item pipelines
class ItemPrintPipeline(Pipeline):
    def process(self, ant: '.ant_nest.ant', thing: Item) -> Item:
        self.logger.info(str(thing))
        return thing


class ItemValidatePipeline(Pipeline):
    def process(self, ant: '.ant_nest.ant', thing: Item) -> Optional[Item]:
        try:
            thing.validate()
            return thing
        except FiledValidationError:
            return None


class ItemFieldReplacePipeline(Pipeline):
    def __init__(self, fields: List[str], excess_chars: Tuple[str]=('\r', '\n', '\t')):
        self.fields = fields
        self.excess_chars = excess_chars
        super().__init__()

    def process(self, ant: '.ant_nest.ant', thing: Item) -> Item:
        for field in self.fields:
            for char in self.excess_chars:
                if field in thing and isinstance(thing[field], str):
                    thing[field] = thing[field].replace(char, '')
        return thing


class ItemJsonDumpPipeline(Pipeline):
    def __init__(self, file_dir: str='.'):
        super().__init__()
        self.file_dir = file_dir
        self.data = defaultdict(list)  # type: DefaultDict[str, List[Dict]]

    def process(self, ant: '.ant_nest.ant', thing: Item) -> Item:
        self.data[thing.__class__.__name__].append(dict(thing))
        return thing

    def dump(self, file_path: str, data: dict):
        with open(file_path, 'w') as f:
            json.dump(data, f)

    async def on_spider_close(self, ant: '.ant_nest.Ant'):
        for file_name, data in self.data.items():
            ant.ensure_future(
                asyncio.get_event_loop().run_in_executor(
                    None, self.dump, os.path.join(self.file_dir, file_name + '.json'), data))


class ItemBaseMysqlPipeline(Pipeline):
    def __init__(self, host: str, port: int, user: str, password: str, database: str, table: str, charset: str='utf8'):
        super().__init__()
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.table = table
        self.charset = charset
        self.pool = None

    async def on_spider_open(self, ant: '.ant_nest.ant') -> None:
        self.pool = await aiomysql.create_pool(host=self.host, port=self.port, user=self.user, password=self.password,
                                               db=self.database, charset=self.charset, use_unicode=True)

    def on_spider_close(self, ant: '.ant_nest.ant') -> None:
        self.pool.close()

    async def push_data(self, sql: str) -> None:
        self.logger.debug('Executing SQL: ' + sql)
        async with self.pool.get() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(sql)
                await conn.commit()
            except Exception as e:
                self.logger.exception('Push data with ' + e.__class__.__name__)

    @staticmethod
    def convert_item_value(value: Any) -> str:
        """Parse value to str for making sql string, eg: False -> '0'"""
        if isinstance(value, bool):
            return '1' if value else '0'
        elif isinstance(value, str):
            value = value.replace('\"', '\\\"')
            return '"{:s}"'.format(value)
        elif isinstance(value, datetime.datetime):
            return '"{:s}"'.format(str(value))
        elif isinstance(value, datetime.date):
            return '"{:s}"'.format(str(value))
        elif value is None:
            return 'null'
        else:
            return str(value)


class ItemMysqlInsertPipeline(ItemBaseMysqlPipeline):
    sql_format = 'INSERT IGNORE INTO {database}.{table} ({fields}) VALUES ({values})'

    async def process(self, ant: '.ant_nest.ant', thing: Item):
        fields = []
        values = []
        for k, v in thing.items():
            fields.append(k)
            values.append(self.convert_item_value(v))
        sql = self.sql_format.format(database=self.database, table=self.table, fields=','.join(fields),
                                     values=','.join(values))
        await self.push_data(sql)
        return thing
