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

    class Pl(ItemJsonDumpPipeline):
        def _dump(self, file_path: str, data: dict):
            pass

    pl = Pl()
    item = TItem()
    item.count = 1
    assert pl.process(item) is item
    item = TItem()
    item.info = 'hi'
    pl.process(item)
    await pl.on_spider_close()


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
