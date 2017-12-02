import pytest

from yarl import URL

from ant_nest import pipelines
from ant_nest import things
from ant_nest import ant


def test_report_pipeline():
    pl = pipelines.ReportPipeline()
    thing = things.Item()
    for _ in range(10):
        assert pl.process(None, thing) is thing
    assert pl.count == 10


def test_response_fileter_error_pipeline():
    pl = pipelines.ResponseFilterErrorPipeline()
    res = things.Response(things.Request('http://test.com'), 200, b'')
    err_res = things.Response(things.Request('http://test.com'), 403, b'')
    assert res is pl.process(None, res)
    assert pl.process(None, err_res) is None


@pytest.mark.asyncio
async def test_response_retry_pipeline():
    pl = pipelines.ResponseRetryPipeline()
    res = things.Response(things.Request('http://test.com'), 200, b'')
    err_res = things.Response(things.Request('http://test.com'), 403, b'')

    class TAnt(ant.Ant):
        count = 0

        async def _request(self, req):
            self.count += 1
            if self.count == 3:
                return things.Response(things.Request('http://retry.com'), 200, b'')
            else:
                return things.Response(things.Request('http://retryf.com'), 403, b'')

        async def run(self):
            return None

    a = TAnt()
    assert await pl.process(a, res) is res
    assert (await pl.process(a, err_res)).url == URL('http://retry.com')


def test_request_no_redirects_pipeline():
    pl = pipelines.RequestNoRedirectsPipeline()
    req = things.Request('http://test.com')
    assert pl.process(None, req) is req
    assert not req.allow_redirects
    assert req.max_redirects == 0


def test_request_proxy_pipeline():
    proxy = 'http://user:pwd@localhost:3128'
    pl = pipelines.RequestProxyPipeline(proxy)
    req = things.Request('http://test.com')
    assert pl.process(None, req) is req
    assert req.proxy == proxy


def test_request_duplicate_filter_pipeline():
    pl = pipelines.RequestDuplicateFilterPipeline()
    req = things.Request('http://test.com')
    assert pl.process(None, req) is req
    assert pl.process(None, req) is None


class TItem(things.Item):
    count = things.IntField()
    info = things.StringField()


def test_item_print_pipeline():
    pl = pipelines.ItemPrintPipeline()
    item = TItem()
    item.count = 3
    item.info = 'hi'
    assert pl.process(None, item) is item


def test_item_validate_pipeline():
    pl = pipelines.ItemValidatePipeline()
    item = TItem()
    item.count = '3'
    assert pl.process(None, item) is None

    item.info = 'hi'
    pl.process(None, item)
    assert item.count == 3


def test_item_filed_replace_pipeline():
    pl = pipelines.ItemFieldReplacePipeline(['info'])
    item = TItem()
    item.info = 'hi\n,\t\r ant\n'
    pl.process(None, item)
    assert item.info == 'hi, ant'


@pytest.mark.asyncio
async def test_item_json_dump_pipeline():

    class Pl(pipelines.ItemJsonDumpPipeline):
        def dump(self, file_path: str, data: dict):
            pass

    class TAnt(ant.Ant):
        async def run(self):
            pass

    pl = Pl()
    a = TAnt()
    item = TItem()
    item.count = 1
    assert pl.process(a, item) is item
    item = TItem()
    item.info = 'hi'
    pl.process(a, item)
    await pl.on_spider_close(a)


def test_request_user_agent_pipeline():
    pl = pipelines.RequestUserAgentPipeline(user_agent='ant')
    req = things.Request('www.hi.com')
    assert pl.process(None, req) is req
    assert req.headers['User-Agent'] == 'ant'
