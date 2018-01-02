import asyncio
from multidict import CIMultiDictProxy, CIMultiDict

import pytest
from tenacity import RetryError
from aiohttp.backport_cookies import SimpleCookie

from ant_nest import *


@pytest.mark.asyncio
async def test_ant():
    class TestPipeline(Pipeline):
        def __init__(self):
            super().__init__()
            self.count = 0

        def process(self, thing):
            self.count += 1
            return thing

    class TestAnt(Ant):
        item_pipelines = [TestPipeline()]
        request_retries = 0

        async def run(self):
            await self.request('test.com')
            await self.collect(Item(x=1))
            assert self.item_pipelines[0].count == 1

        async def _request(self, req: Request):
            return Response(req, 200, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())

    ant = TestAnt()
    await ant.main()

    class Test2Ant(TestAnt):
        async def run(self):
            raise Exception('Test exception')

    await Test2Ant().main()


@pytest.mark.asyncio
async def test_ant_with_retry():
    # with retry
    class Test2Ant(Ant):
        request_retries = 2
        request_retry_delay = 0.1

        def __init__(self):
            super().__init__()
            self.min_retries = 2
            self.retries = 0

        async def run(self):
            return None

        async def _request(self, req: Request):
            if self.retries < self.min_retries:
                self.retries += 1
                raise IOError()
            else:
                return Response(req, 200, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())

    await Test2Ant().request('www.test.com')
    ant = Test2Ant()
    ant.request_retries = 1
    with pytest.raises(RetryError):
        await ant.request('www.test.com')

    class Test3Ant(Test2Ant):
        async def _request(self, req: Request):
            if self.retries < self.min_retries:
                self.retries += 1
                return Response(req, 500, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())
            else:
                return Response(req, 200, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())

    await Test3Ant().request('www.test.com')
    ant = Test3Ant()
    ant.request_retries = 1
    with pytest.raises(RetryError):
        await ant.request('www.test.com')


@pytest.mark.asyncio
async def test_with_timeout():
    class TestAnt(Ant):
        request_retries = 0
        request_timeout = 0.2

        def __init__(self):
            super().__init__()
            self.sleep_time = 0.1
            self.retries = 0

        async def run(self):
            return None

        async def _request(self, req: Request):
            self.retries += 1
            await asyncio.sleep(self.sleep_time)
            return Response(req, 200, b'1', CIMultiDictProxy(CIMultiDict()), SimpleCookie())

    ant = TestAnt()
    await ant.request('www.test.com')

    ant.request_timeout = 0.05
    with pytest.raises(asyncio.TimeoutError):
        await ant.request('www.test.com')

    ant.request_retries = 3
    ant.request_retry_delay = 0.1
    ant.retries = 0
    with pytest.raises(RetryError):
        await ant.request('www.test.com')
    assert ant.retries == ant.request_retries + 1


@pytest.mark.asyncio
async def test_pipelines():
    class TestAnt(Ant):
        async def run(self):
            return None

    pls = [Pipeline() for x in range(10)]
    thing = Request('test_url')
    ant = TestAnt()
    assert thing is await ant._handle_thing_with_pipelines(thing, pls)

    class TestPipeline(Pipeline):
        async def process(self, thing):
            return None

    pls[5] = TestPipeline()
    with pytest.raises(ThingDropped):
        await ant._handle_thing_with_pipelines(thing, pls)


@pytest.mark.asyncio
async def test_with_real_request():
    httpbin_base_url = 'http://localhost:8080/'

    class TestAnt(Ant):
        async def run(self):
            return None

    ant = TestAnt()
    res = await ant.request(httpbin_base_url)
    assert res.status == 200
    # method
    for method in ['GET', 'POST', 'DELETE', 'PUT', 'PATCH']:
        res = await ant.request(httpbin_base_url + 'anything', method=method)
        assert res.status == 200
        assert res.json['method'] == method
    # params
    res = await ant.request(httpbin_base_url + 'get?k1=v1&k2=v2')
    assert res.status == 200
    assert res.json['args']['k1'] == 'v1'
    assert res.json['args']['k2'] == 'v2'
    # data with str
    res = await ant.request(httpbin_base_url + 'post', method='POST', data='Test data')
    assert res.status == 200
    assert res.json['data'] == 'Test data'
    # data with dict
    res = await ant.request(httpbin_base_url + 'post', method='POST', data={'k1': 'v1'})
    assert res.status == 200
    assert res.json['form']['k1'] == 'v1'
    # data with bytes
    res = await ant.request(httpbin_base_url + 'post', method='POST', data=b'12345')
    assert res.status == 200
    assert res.json['data'] == '12345'
    # data with file
    with open('tests/test.html', 'r') as f:
        file_content = f.read()
        f.seek(0)
        res = await ant.request(httpbin_base_url + 'post', method='POST', data=f)
        assert res.status == 200
        assert res.json['data'] == file_content
    # headers
    res = await ant.request(httpbin_base_url + 'headers', headers={'Custom-Key': 'test'})
    assert res.status == 200
    assert res.headers['Content-Type'] == 'application/json'
    assert res.json['headers']['Custom-Key'] == 'test'
    # cookies
    res = await ant.request(httpbin_base_url + 'cookies', cookies={'Custom-Key': 'test'})
    assert res.status == 200
    assert res.json['cookies']['Custom-Key'] == 'test'
    # get cookies
    ant.request_allow_redirects = False
    res = await ant.request(httpbin_base_url + 'cookies/set?k1=v1&k2=v2')
    assert res.status == 302
    assert res.cookies['k1'].value == 'v1'
    assert res.cookies['k2'].value == 'v2'
    # redirects
    ant.request_allow_redirects = True
    ant.request_max_redirects = 3
    res = await ant.request(httpbin_base_url + 'redirect/2')
    assert res.status == 200
    res = await ant.request(httpbin_base_url + 'redirect/3')
    assert res.status == 302

    await ant.close()
