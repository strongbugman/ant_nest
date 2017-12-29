import os

import pytest

from ant_nest import *


@pytest.mark.asyncio
async def test_pipeline():
    pl = Pipeline()
    await pl.process(Request(url='test.com'))


def test_report_pipeline():
    pl = ReportPipeline()
    thing = Item()
    for _ in range(10):
        assert pl.process(thing) is thing
    assert pl.count == 10


def test_response_fileter_error_pipeline():
    pl = ResponseFilterErrorPipeline()
    res = Response(Request('http://test.com'), 200, b'')
    err_res = Response(Request('http://test.com'), 403, b'')
    assert res is pl.process(res)
    assert pl.process(err_res) is None


def test_request_duplicate_filter_pipeline():
    pl = RequestDuplicateFilterPipeline()
    req = Request('http://test.com')
    assert pl.process(req) is req
    assert pl.process(req) is None


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
    assert pl.process(item) is None

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
    ci = os.getenv('CI', 'localhost')
    if ci == 'localhost':
        os.remove('./Titem.json')


def test_request_user_agent_pipeline():
    pl = RequestUserAgentPipeline(user_agent='ant')
    req = Request('www.hi.com')
    assert pl.process(req) is req
    assert req.headers['User-Agent'] == 'ant'


@pytest.mark.asyncio
async def test_item_email_pipeline():

    class TestPipeline(ItemEmailPipeline):
        async def open_smtp(self):

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
    mysql_database = os.getenv('TEST_MYSQL_DATABASE)', 'test')

    bpl = ItemBaseMysqlPipeline(host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
                                database=mysql_database, table='test')
    await bpl.on_spider_open()
    await bpl.push_data('DROP TABLE IF EXISTS test;')
    await bpl.push_data('''CREATE TABLE `test` (
                           `id` int(11) unsigned NOT NULL AUTO_INCREMENT,
                           `test` text DEFAULT NULL,
                           PRIMARY KEY (`id`)
                           ) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8;''')

    test_item = Item(test='I ant')
    ibpl = ItemMysqlInsertPipeline(host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
                                   database=mysql_database, table='test')
    await ibpl.on_spider_open()
    assert test_item is await ibpl.process(test_item)
    data = await ibpl.pull_data('SELECT * FROM test')
    assert test_item.test == data[0]['test']

    ubpl = ItemMysqlUpdatePipeline(host=mysql_server, port=mysql_port, user=mysql_user, password=mysql_password,
                                   database=mysql_database, table='test', primary_key='id')
    await ubpl.on_spider_open()
    test_item.id = data[0]['id']
    test_item.test = 'I ANT'
    assert test_item is await ubpl.process(test_item)
    data = await ubpl.pull_data('SELECT * FROM test')
    assert test_item.test == data[0]['test']
    test_item.test = 'I ant'
    assert test_item is await ubpl.process(test_item)
    data = await ubpl.pull_data('SELECT * FROM test')
    assert test_item.test == data[0]['test']

    await ubpl.on_spider_close()
    await ibpl.on_spider_close()
    await bpl.push_data('DROP TABLE test;')
    await bpl.on_spider_close()
