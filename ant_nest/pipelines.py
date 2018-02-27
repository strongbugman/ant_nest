from typing import Optional, List, Tuple, DefaultDict, Dict, Any, IO, Union, Sequence, Coroutine, AnyStr
import asyncio
import logging
from collections import defaultdict
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import re

import aiomysql
import aioredis
import aiosmtplib
import aiofiles

from .things import Things, Response, Request, Item
from .exceptions import FieldValidationError, ThingDropped


class Pipeline:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    async def on_spider_open(self) -> None:
        """Call when ant open, this method can be coroutine function"""

    async def on_spider_close(self) -> None:
        """Call when ant close, this method can be coroutine function"""

    async def process(self, thing: Things) -> Things:
        """Process things, this method can be coroutine function
        Raise ThingDropped when drop one thing

        :raise ThingDropped
        """
        return thing


# Response pipelines
class ResponseFilterErrorPipeline(Pipeline):
    def process(self, thing: Response) -> Union[Things, Exception]:
        if thing.status >= 400:
            raise ThingDropped('Respose status is {:d}'.format(thing.status))
        else:
            return thing


# Request pipelines
class RequestDuplicateFilterPipeline(Pipeline):
    def __init__(self):
        self.__request_urls = set()
        super().__init__()

    def process(self, thing: Request) -> Union[Things, Exception]:
        if thing.url in self.__request_urls:
            raise ThingDropped('Request duplicate!')
        else:
            self.__request_urls.add(thing.url)
            return thing


class RequestUserAgentPipeline(Pipeline):
    user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) ' \
                 'Chrome/51.0.2704.103 Safari/537.36'

    def __init__(self, user_agent=user_agent):
        super().__init__()
        self.user_agent = user_agent

    def process(self, thing: Request) -> Request:
        thing.headers['User-Agent'] = self.user_agent
        return thing


class RequestRandomUserAgentPipeline(Pipeline):
    """Create simple and common user agent for request by random,
    It`s easy to add new rule.
    """
    USER_AGENT_FORMAT = 'Mozilla/5.0 ({system}) {browser}'
    SYSTEM_FORMATS = {
        'UnixLike': 'X11; {unix-like_os} {cpu_type}',
        'MacOS': 'Macintosh; Intel Mac OS X {macos_version}',
        'Windows': 'Windows NT {windows_version}',
        'Android': 'Android {android_version}; Linux',
        'iOS': '{ios_driver}; CPU OS {ios_version} like Mac OS X',
    }
    BROWSER_FORMATS = {
        'Firefox': 'Gecko/20100101 Firefox/{firefox_version}',
        'Safari': 'AppleWebKit/{webkit_version} (KHTML, like Gecko) Version/{safari_version} Safari/{safari_version2}',
        'Chrome': 'AppleWebKit/{webkit_version} (KHTML, like Gecko) Chrome/{chrome_version} Safari/{safari_version2}',
    }
    FORMAT_VARS = {
        'unix-like_os': ('Linux', 'FreeBSD'),
        'cpu_type': ('x86_64', 'i386', 'amd64'),
        'macos_version': ('10_10_1', '10_11_1', '10_11_2', '10_12_2', '10_12_3', '10_13_3'),
        'windows_version': ('5_0', '5_1', '5_2', '6_0', '6_1', '10_0'),
        'android_version': ('4_4', '5_0', '5_1', '6_0', '6_1', '7_0', '7_1', '8_0'),
        'ios_driver': ('iPone', 'iPod', 'iPad'),
        'ios_version': ('6_0', '7_0', '8_1', '9_2', '10_3', '10_2_3', '11_3_3'),
        'firefox_version': ('27.3', '28.0', '31.0', '40.1'),
        'webkit_version': ('533.18.1', '533.19.4', '533.20.25', '534.55.3'),
        'safari_version': ('4.0.1', '5.0.4', '5.1.3', '6.0', '7.0.3'),
        'safari_version2': ('530.19.1', '531.9', '533.16', '533.20.27'),
        'chrome_version': ('41.0.2226.0', '60.0.1325.223', '62.0.1532.123', '64.0.3282.119')
    }

    def __init__(self, system: str = 'random', browser: str = 'random'):
        if system != 'random' and system not in self.SYSTEM_FORMATS.keys():
            raise ValueError('The system {:s} is not supported!'.format(system))
        if browser != 'random' and browser not in self.BROWSER_FORMATS.keys():
            raise ValueError('The browser {:s} is not supported!'.format(browser))

        self.system = system
        self.browser = browser
        super().__init__()

    @staticmethod
    def choice(data: Sequence[str]) -> str:
        return random.choice(data)

    def _format(self, pattern: str) -> str:
        """format system or browser pattern string"""
        kv = {}
        keys = re.findall('{(\S+?)}', pattern)

        for key in keys:
            kv[key] = self.choice(self.FORMAT_VARS[key])

        return pattern.format(**kv)

    def create(self) -> str:
        if self.system != 'random':
            system_format = self.SYSTEM_FORMATS[self.system]
        else:
            system_format = self.SYSTEM_FORMATS[self.choice(list(self.SYSTEM_FORMATS.keys()))]

        if self.browser != 'random':
            browser_format = self.BROWSER_FORMATS[self.browser]
        else:
            browser_format = self.BROWSER_FORMATS[self.choice(list(self.BROWSER_FORMATS.keys()))]

        return self.USER_AGENT_FORMAT.format(system=self._format(system_format), browser=self._format(browser_format))

    def process(self, thing: Request) -> Request:
        thing.headers['User-Agent'] = self.create()
        return thing


class RequestRandomComputerUserAgentPipeline(Pipeline):
    SYSTEM_FORMATS = {
        'UnixLike': 'X11; {unix-like_os} {cpu_type}',
        'MacOS': 'Macintosh; Intel Mac OS X {macos_version}',
        'Windows': 'Windows NT {windows_version}',
    }


class RequestRandomMobileUserAgentPipeline(Pipeline):
    SYSTEM_FORMATS = {
        'Android': 'Android {android_version}; Linux',
        'iOS': '{ios_driver}; CPU OS {ios_version} like Mac OS X',
    }


# Item pipelines
class ItemPrintPipeline(Pipeline):
    def process(self, thing: Item) -> Item:
        self.logger.info(thing.__repr__())
        return thing


class ItemValidatePipeline(Pipeline):
    def process(self, thing: Item) -> Union[Things, Exception]:
        try:
            thing.validate()
            return thing
        except FieldValidationError as e:
            raise ThingDropped('Validation failed') from e


class ItemFieldReplacePipeline(Pipeline):
    def __init__(self, fields: List[str], excess_chars: Tuple[str] = ('\r', '\n', '\t')):
        self.fields = fields
        self.excess_chars = excess_chars
        super().__init__()

    def process(self, thing: Item) -> Item:
        for field in self.fields:
            for char in self.excess_chars:
                if field in thing and isinstance(thing[field], str):
                    thing[field] = thing[field].replace(char, '')
        return thing


class ItemBaseFileDumpPipeline(Pipeline):
    streaming_buffer_size = 1024 * 1024  # default is 1MB

    @classmethod
    async def dump(cls, file_path: str, data: Union[AnyStr, IO]) -> None:
        """Dump data(binary or text, stream or normal, async or not) to disk file.
        IO data will be closed.
        """
        chunk = None  # type: Optional[Union[AnyStr]]
        if isinstance(data, str):
            file_mode = 'w'
        elif isinstance(data, bytes):
            file_mode = 'wb'
        elif hasattr(data, 'read'):  # readable
            chunk = data.read(cls.streaming_buffer_size)
            if asyncio.iscoroutine(chunk):
                chunk = await chunk

            if isinstance(chunk, str):
                file_mode = 'w'
            else:
                file_mode = 'wb'
        else:
            raise ValueError('The type {:s} is not supported'.format(type(data).__class__.__name__))

        async with aiofiles.open(file_path, file_mode) as file:
            if chunk is not None:  # in streaming
                await file.write(chunk)
                while True:

                    chunk = data.read(cls.streaming_buffer_size)
                    if asyncio.iscoroutine(chunk):
                        chunk = await chunk

                    if len(chunk) == 0:
                        break
                    else:
                        await file.write(chunk)

                result = data.close()
                if asyncio.iscoroutine(result):
                    await result
            else:
                await file.write(data)


class ItemJsonDumpPipeline(ItemBaseFileDumpPipeline):
    """Dump item to json during pipeline closing"""
    def __init__(self, file_dir: str = '.'):
        super().__init__()
        self.file_dir = file_dir
        self.data = defaultdict(list)  # type: DefaultDict[str, List[Dict]]

    def process(self, thing: Item) -> Item:
        self.data[thing.__class__.__name__].append(dict(thing))
        return thing

    async def on_spider_close(self) -> None:
        for file_name, data in self.data.items():
            data = json.dumps(data)
            await self.dump(os.path.join(self.file_dir, file_name + '.json'), data)


class ItemBaseMysqlPipeline(Pipeline):
    def __init__(self, host: str, port: int, user: str, password: str, database: str, table: str,
                 charset: str = 'utf8'):
        super().__init__()
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.table = table
        self.charset = charset

    async def create_pool(self) -> aiomysql.Pool:
        return await aiomysql.create_pool(host=self.host, port=self.port, user=self.user, password=self.password,
                                          db=self.database, charset=self.charset, use_unicode=True)

    async def push_data(self, sql: str, pool: aiomysql.Pool) -> None:
        """Run SQL without pulling data like "INSERT" and "UPDATE" command"""
        self.logger.debug('Executing SQL: ' + sql)
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
            await conn.commit()

    async def pull_data(self, sql: str, pool: aiomysql.Pool) -> Tuple[Dict[str, Any]]:
        """Run SQL with pulling data like "SELECT" command"""
        self.logger.debug('Executing SQL: ' + sql)
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                return await cur.fetchall()

    @staticmethod
    def convert_item_value(value: Any) -> str:
        """Parse value to str for making sql string, eg: False -> '0'"""
        if isinstance(value, bool):
            return '1' if value else '0'
        elif isinstance(value, int) or isinstance(value, float):
            return str(value)
        elif isinstance(value, bytes):
            return 'X\'{:s}\''.format(value.hex())
        elif value is None:
            return 'null'
        else:
            value = str(value).replace('\"', '\\\"')
            return '"{:s}"'.format(value)


class ItemMysqlInsertPipeline(ItemBaseMysqlPipeline):
    sql_format = 'INSERT IGNORE INTO `{database}`.`{table}` ({fields}) VALUES ({values})'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pool = None

    async def on_spider_open(self) -> None:
        self.pool = await self.create_pool()

    async def on_spider_close(self) -> None:
        self.pool.close()
        await self.pool.wait_closed()

    async def process(self, thing: Item) -> Item:
        fields = []
        values = []
        for k, v in thing.items():
            fields.append(k)
            values.append(self.convert_item_value(v))
        sql = self.sql_format.format(database=self.database, table=self.table, fields='`' + '`,`'.join(fields) + '`',
                                     values=','.join(values))
        await self.push_data(sql, self.pool)
        return thing


class ItemMysqlUpdatePipeline(ItemMysqlInsertPipeline):
    sql_format = 'UPDATE `{database}`.`{table}` SET {pairs} WHERE `{primary_key}`={primary_value}'

    def __init__(self, primary_key: str, host: str, port: int, user: str, password: str, database: str, table: str,
                 charset: str = 'utf8'):
        super().__init__(host, port, user, password, database, table, charset=charset)
        self.primary_key = primary_key

    async def process(self, thing: Item) -> Item:
        pairs = []
        primary_value = None

        for k, v in thing.items():
            if k == self.primary_key:
                primary_value = self.convert_item_value(v)
            else:
                pairs.append('`{:s}`={:s}'.format(k, self.convert_item_value(v)))

        if primary_value is not None:
            sql = self.sql_format.format(database=self.database, table=self.table, pairs=','.join(pairs),
                                         primary_key=self.primary_key, primary_value=primary_value)
            await self.push_data(sql, self.pool)
        return thing


class ItemMysqlInsertUpdatePipeline(ItemMysqlInsertPipeline):
    sql_format = 'INSERT INTO `{database}`.`{table}` ({fields}) VALUES ({values}) on duplicate key update {pairs}'

    def __init__(self, update_keys: List[str], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_keys = update_keys

    async def process(self, thing: Item) -> Item:
        fields = []
        values = []
        pairs = []
        for k, v in thing.items():
            v = self.convert_item_value(v)
            fields.append(k)
            values.append(v)
            if k in self.update_keys:
                pairs.append('`{:s}`={:s}'.format(k, v))
        sql = self.sql_format.format(database=self.database, table=self.table, fields='`' + '`,`'.join(fields) + '`',
                                     values=','.join(values), pairs=','.join(pairs))
        await self.push_data(sql, self.pool)
        return thing


class ItemBaseEmailPipeline(Pipeline):
    def __init__(self, account: str, password: str, server: str, port: int, recipients: List[str],
                 sender_name: str = 'AntNest.ItemEmailPipeline', tls: bool = False, starttls: bool = False):
        super().__init__()
        self.account = account
        self.password = password
        self.server = server
        self.port = port
        self.recipients = recipients
        self.sender_name = sender_name
        self.starttls = starttls
        self.tls = tls

    async def create_smtp(self) -> aiosmtplib.SMTP:
        smtp = aiosmtplib.SMTP()
        if self.starttls:
            await smtp.connect(self.server, self.port, use_tls=False)
            await smtp.starttls()
        else:
            await smtp.connect(self.server, self.port, use_tls=self.tls)
        await smtp.login(self.account, self.password)
        return smtp

    async def send(self, smtp: aiosmtplib.SMTP, title: str, content: str, attachments: Optional[List[IO]] = None):
        if attachments is None:
            msg = MIMEText(content)
        else:
            msg = MIMEMultipart()
            msg.attach(MIMEText(content))
            for f in attachments:
                att = MIMEText(f.read(), 'base64', 'utf-8')
                att["Content-Type"] = 'application/octet-stream'
                att["Content-Disposition"] = 'attachment; filename="{:s}"'.format(f.name)
                msg.attach(att)
        msg['From'] = '{:s} <{:s}>'.format(self.sender_name, self.account)
        msg['To'] = '<' + '> <'.join(self.recipients) + '>'
        msg['Subject'] = title
        await smtp.send_message(msg)


class ItemEmailPipeline(ItemBaseEmailPipeline):
    def __init__(self, title, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.items = []
        self.title = title

    def process(self, thing: Item) -> Item:
        self.items.append(thing)
        return thing

    async def on_spider_close(self) -> None:
        smtp = await self.create_smtp()
        await self.send(smtp, self.title, '\n'.join(item.__repr__() for item in self.items))
        smtp.close()


class ItemBaseRedisPipeline(Pipeline):
    def __init__(self, address: str, db: Optional[int] = None, password: Optional[str] = None, encoding: str = 'utf-8',
                 minsize: int = 1, maxsize: int = 10, ssl: Optional[bool] = None, timeout: Optional[float] = None):
        super().__init__()
        self.address = address
        self.db = db
        self.password = password
        self.encoding = encoding
        self.minsize = minsize
        self.maxsize = maxsize
        self.ssl = ssl
        self.timeout = timeout

    async def create_redis(self) -> aioredis.ConnectionsPool:
        return await aioredis.create_redis_pool(
            self.address, db=self.db, password=self.password, encoding=self.encoding, minsize=self.minsize,
            maxsize=self.maxsize, ssl=self.ssl, timeout=self.timeout)


__all__ = [var for var in vars().keys() if 'Pipeline' in var]
