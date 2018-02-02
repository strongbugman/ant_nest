from typing import Optional, List, Tuple, DefaultDict, Dict, Any, IO, Union
import logging
from collections import defaultdict
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio

import aiomysql
import aiosmtplib

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
    user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_1) AppleWebKit/537.36 (KHTML, like Gecko)' \
                 'Chrome/62.0.3202.89 Safari/537.36 Name'

    def __init__(self, user_agent=user_agent):
        super().__init__()
        self.user_agent = user_agent

    def process(self, thing):
        if thing.headers is None:
            thing.headers = {}
        thing.headers['User-Agent'] = self.user_agent
        return thing


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
    def __init__(self, fields: List[str], excess_chars: Tuple[str]=('\r', '\n', '\t')):
        self.fields = fields
        self.excess_chars = excess_chars
        super().__init__()

    def process(self, thing: Item) -> Item:
        for field in self.fields:
            for char in self.excess_chars:
                if field in thing and isinstance(thing[field], str):
                    thing[field] = thing[field].replace(char, '')
        return thing


class ItemBaseJsonDumpPipeline(Pipeline):
    @staticmethod
    def _dump(file_path: str, data: Dict) -> None:
        with open(file_path, 'w') as f:
            json.dump(data, f)

    async def dump(self, file_path: str, data: Dict) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self._dump, file_path, data)


class ItemJsonDumpPipeline(ItemBaseJsonDumpPipeline):
    def __init__(self, file_dir: str='.'):
        super().__init__()
        self.file_dir = file_dir
        self.data = defaultdict(list)  # type: DefaultDict[str, List[Dict]]

    def process(self, thing: Item) -> Item:
        self.data[thing.__class__.__name__].append(dict(thing))
        return thing

    async def on_spider_close(self) -> None:
        for file_name, data in self.data.items():
            await self.dump(os.path.join(self.file_dir, file_name + '.json'), data)


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

    async def on_spider_open(self) -> None:
        self.pool = await aiomysql.create_pool(host=self.host, port=self.port, user=self.user, password=self.password,
                                               db=self.database, charset=self.charset, use_unicode=True)

    async def on_spider_close(self) -> None:
        self.pool.close()
        await self.pool.wait_closed()

    async def push_data(self, sql: str) -> None:
        """Run SQL without pulling data like "INSERT" and "UPDATE" command"""
        self.logger.debug('Executing SQL: ' + sql)
        async with self.pool.get() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
            await conn.commit()

    async def pull_data(self, sql: str) -> Tuple[Dict[str, Any]]:
        """Run SQL with pulling data like "SELECT" command"""
        self.logger.debug('Executing SQL: ' + sql)
        async with self.pool.get() as conn:
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

    async def process(self, thing: Item):
        fields = []
        values = []
        for k, v in thing.items():
            fields.append(k)
            values.append(self.convert_item_value(v))
        sql = self.sql_format.format(database=self.database, table=self.table, fields='`' + '`,`'.join(fields) + '`',
                                     values=','.join(values))
        await self.push_data(sql)
        return thing


class ItemMysqlUpdatePipeline(ItemBaseMysqlPipeline):
    sql_format = 'UPDATE `{database}`.`{table}` SET {pairs} WHERE `{primary_key}`={primary_value}'

    def __init__(self, primary_key: str, host: str, port: int, user: str, password: str, database: str, table: str,
                 charset: str='utf8'):
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
            await self.push_data(sql)
        return thing


class ItemMysqlInsertUpdatePipeline(ItemBaseMysqlPipeline):
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
        await self.push_data(sql)
        return thing


class ItemBaseEmailPipeline(Pipeline):
    def __init__(self, account: str, password: str, server: str, port: int, recipients: List[str],
                 sender_name: str='AntNest.ItemEmailPipeline', tls: bool=False, starttls: bool=False):
        super().__init__()
        self.account = account
        self.password = password
        self.server = server
        self.port = port
        self.recipients = recipients
        self.sender_name = sender_name
        self.starttls = starttls
        self.tls = tls

    async def open_smtp(self) -> aiosmtplib.SMTP:
        smtp = aiosmtplib.SMTP()
        if self.starttls:
            await smtp.connect(self.server, self.port, use_tls=False)
            await smtp.starttls()
        else:
            await smtp.connect(self.server, self.port, use_tls=self.tls)
        await smtp.login(self.account, self.password)
        return smtp

    async def send(self, smtp: aiosmtplib.SMTP, title: str, content: str, attachments: Optional[List[IO]]=None):
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
        smtp = await self.open_smtp()
        await self.send(smtp, self.title, '\n'.join(item.__repr__() for item in self.items))
        smtp.close()


__all__ = [var for var in vars().keys() if 'Pipeline' in var]
