import os
import time
from datetime import datetime
import io

import pytest
from yarl import URL
import aiofiles

from ant_nest import *


@pytest.mark.asyncio
async def test_pipeline():
    pl = Pipeline()
    await pl.process(Request('GET', URL('https://test.com')))


def test_response_filter_error_pipeline():
    pl = ResponseFilterErrorPipeline()
    res = Response('GET', URL('https://test.com'))
    err_res = Response('GET', URL('https://test.com'))
    res.status = 200
    err_res.status = 403
    assert res is pl.process(res)
    with pytest.raises(ThingDropped):
        pl.process(err_res)


def test_request_duplicate_filter_pipeline():
    pl = RequestDuplicateFilterPipeline()
    req = Request('GET', URL('http://test.com'))
    assert pl.process(req) is req
    with pytest.raises(ThingDropped):
        pl.process(req)


class TItem(Item):
    count = IntField()
    info = StringField()


def test_item_print_pipeline():
    pl = ItemPrintPipeline()
    item = TItem()
    item.count = 3
    item.info = 'hi'
    assert pl.process(item) is item


def test_item_validate_pipeline():
    pl = ItemValidatePipeline()
    item = TItem()
    item.count = '3'
    with pytest.raises(ThingDropped):
        pl.process(item)

    item.info = 'hi'
    pl.process(item)
    assert item.count == 3


def test_item_filed_replace_pipeline():
    pl = ItemFieldReplacePipeline(['info'])
    item = TItem()
    item.info = 'hi\n,\t\r ant\n'
    pl.process(item)
    assert item.info == 'hi, ant'


@pytest.mark.asyncio
async def test_item_base_file_dump_pipeline():
    pl = ItemBaseFileDumpPipeline()
    await pl.dump('/dev/null', 'Hello World')
    await pl.dump('/dev/null', b'Hello World')
    await pl.dump('/dev/null', io.StringIO('Hello World'))
    await pl.dump('/dev/null', io.BytesIO(b'Hello World'))
    await pl.dump('/dev/null', open('./tests/test.html'))
    async with aiofiles.open('./tests/test.html') as f:
        await pl.dump('/dev/null', f)
    async with aiofiles.open('./tests/test.html', 'rb') as f:
        await pl.dump('/dev/null', f)

    with pytest.raises(ValueError):
        await pl.dump('/dev/null', None)


@pytest.mark.asyncio
async def test_item_json_dump_pipeline():
    pl = ItemJsonDumpPipeline()
    item = TItem()
    item.count = 1
    assert pl.process(item) is item
    item = TItem()
    item.info = 'hi'
    pl.process(item)
    await pl.on_spider_close()

    # clean file
    ci = os.getenv('TEST_HOST', 'localhost')
    if ci == 'localhost':
        os.remove('./Titem.json')


def test_request_user_agent_pipeline():
    pl = RequestUserAgentPipeline(user_agent='ant')
    req = Request('GET', URL('https://www.hi.com'))
    assert pl.process(req) is req
    assert req.headers['User-Agent'] == 'ant'


def test_request_random_user_agent_pipeline():
    pl = RequestRandomUserAgentPipeline()
    req = Request('GET', URL('https://www.hi.com'), headers={'User-Agent': ''})
    assert pl.process(req) is req
    assert req.headers['User-Agent'] != ''
    assert pl.create() != pl.create()

    with pytest.raises(ValueError):
        RequestRandomUserAgentPipeline(system='something')

    with pytest.raises(ValueError):
        RequestRandomUserAgentPipeline(browser='something')

    pl = RequestRandomUserAgentPipeline(system='UnixLike', browser='Firefox')
    user_agent = pl.create()
    assert 'X11' in user_agent
    assert 'Firefox' in user_agent


@pytest.mark.asyncio
async def test_item_email_pipeline():

    class TestPipeline(ItemEmailPipeline):
        async def create_smtp(self):

            class FakeSMTP:
                async def send_message(self, msg):
                    pass

                def close(self):
                    pass

            return FakeSMTP()

    pl = TestPipeline('test', 'a@b.c', 'letmein', 'localhost', 25, recipients=['b@a.c', 'c@b.a'])
    item = TItem(info='hi')

    pl.process(item)
    await pl.on_spider_close()


@pytest.mark.asyncio
async def test_item_mysql_pipeline():
    mysql_server = os.getenv('TEST_MYSQL_SERVER', 'localhost')
    mysql_port = int(os.getenv('TEST_MYSQL_PORT', 3306))
    mysql_user = os.getenv('TEST_MYSQL_USER', 'root')
    mysql_password = os.getenv('TEST_MYSQL_PASSWORD', 'letmein')

    bpl = ItemBaseMysqlPipeline(host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
                                database='mysql', table='')
    pool = await bpl.create_pool()
    await bpl.push_data('''DROP DATABASE IF EXISTS test;
                           CREATE DATABASE test;''', pool)
    await bpl.push_data('''CREATE TABLE test.test (
                           `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
                           `test` TEXT DEFAULT NULL,
                           `test_bool` BOOL DEFAULT NULL,
                           `test_int` INT DEFAULT NULL,
                           `test_float` FLOAT DEFAULT NULL,
                           `test_bytes` BLOB DEFAULT NULL,
                           `test_datetime` DATETIME DEFAULT NULL,
                           PRIMARY KEY (`id`)
                           ) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8;''', pool)

    test_item = Item(test='I ant', test_bool=False, test_int=1, test_float=0.3, test_bytes=b'\xf0\x9f\x91\x8d',
                     test_datetime=datetime.now())
    ibpl = ItemMysqlInsertPipeline(host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
                                   database='test', table='test')
    await ibpl.on_spider_open()
    assert test_item is await ibpl.process(test_item)
    data = await ibpl.pull_data('SELECT * FROM test', ibpl.pool)
    assert test_item.test == data[0]['test']

    ubpl = ItemMysqlUpdatePipeline(host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
                                   database='test', table='test', primary_key='id')
    await ubpl.on_spider_open()
    test_item.id = data[0]['id']
    test_item.test = 'I ANT'
    assert test_item is await ubpl.process(test_item)
    data = await ubpl.pull_data('SELECT * FROM test', ubpl.pool)
    assert test_item.test == data[0]['test']
    test_item.test = 'I ant'
    assert test_item is await ubpl.process(test_item)
    data = await ubpl.pull_data('SELECT * FROM test', ubpl.pool)
    assert test_item.test == data[0]['test']

    iubpl = ItemMysqlInsertUpdatePipeline(
        ['test'],
        host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
        database='test', table='test')
    await iubpl.on_spider_open()
    test_item.test = 'I love ant!'
    assert test_item is await iubpl.process(test_item)
    data = await iubpl.pull_data('SELECT * FROM test', iubpl.pool)
    assert test_item.test == data[0]['test']

    await ubpl.on_spider_close()
    await ibpl.on_spider_close()
    await iubpl.on_spider_close()
    await bpl.push_data('DROP TABLE test.test;DROP DATABASE test', pool)
    pool.close()
    await pool.wait_closed()


@pytest.mark.asyncio
async def test_redis_pipeline():
    redis_address = os.getenv('TEST_REDIS_ADDRESS', 'redis://localhost:6379')
    pl = ItemBaseRedisPipeline(redis_address)
    pool = await pl.create_redis()
    with await pool as conn:
        value = 'value'
        await conn.set('key', value)
        assert await conn.get('key') == value
    pool.close()
    await pool.wait_closed()
