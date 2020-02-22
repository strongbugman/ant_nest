import asyncio
import os

import pytest
import httpx

from ant_nest.pipelines import Pipeline
from ant_nest.ant import CliAnt, Ant


@pytest.mark.asyncio
async def test_ant():
    class TestPipeline(Pipeline):
        def __init__(self):
            super().__init__()
            self.count = 0

        async def on_spider_open(self):
            pass

        async def on_spider_close(self):
            raise Exception("This exception will be suppressed")

        def process(self, thing):
            self.count += 1
            return thing

    class TestAnt(Ant):
        item_pipelines = [TestPipeline()]
        request_retries = 0

        async def run(self):
            await self.request("http://test.com")
            await self.collect(object())
            assert self.item_pipelines[0].count == 1

        async def requset(self, *args, **kwargs):
            return httpx.Response(200, content=b"")

    ant = TestAnt()
    assert ant.name == "TestAnt"
    await ant.main()

    class Test2Ant(TestAnt):
        async def run(self):
            raise Exception("This exception will be suppressed")

    await Test2Ant().main()


@pytest.mark.asyncio
async def test_pipelines():
    class TestPipeline(Pipeline):
        async def process(self, thing):
            raise TypeError("Test error")

        def on_spider_open(self):
            raise TypeError("Test error")

        def on_spider_close(self):
            raise TypeError("Test error")

    class TestAnt(Ant):
        item_pipelines = [TestPipeline()]

        async def run(self):
            return None

    pls = [Pipeline() for x in range(10)]
    thing = object()
    ant = TestAnt()
    assert thing is await ant._handle_thing_with_pipelines(thing, pls)
    # with exception
    pls[5] = TestPipeline()
    with pytest.raises(TypeError):
        await ant._handle_thing_with_pipelines(thing, pls)
    # exception will be ignored in "open" and "close" method
    with pytest.raises(TypeError):
        await ant.open()
    with pytest.raises(TypeError):
        await ant.close()


@pytest.mark.asyncio
async def test_with_real_send():
    httpbin_base_url = os.getenv("TEST_HTTPBIN", "http://localhost:8080/")

    ant = CliAnt()
    res = await ant.request(httpbin_base_url)
    assert res.status_code == 200
    # method
    for method in ["GET", "POST", "DELETE", "PUT", "PATCH", "HEAD"]:
        res = await ant.request(httpbin_base_url + "anything", method=method)
        assert res.status_code == 200
        if method != "HEAD":
            assert res.json()["method"] == method
        else:
            assert res.text == ""
    # with stream
    res = await ant.request(httpbin_base_url + "anything", stream=True)
    assert res.status_code == 200
    async for _ in res.aiter_bytes():
        pass
    assert res.is_stream_consumed

    await ant.close()


@pytest.mark.asyncio
async def test_ant_main():
    """Pipeline closed before scheduled coroutines done?"""

    class TestPipeline(Pipeline):
        awake = True

        async def on_spider_close(self):
            self.awake = False

    class TestAnt(Ant):
        item_pipelines = [TestPipeline()]

        in_error = False

        async def run(self):
            self.pool.spawn(self.long_cor())

        async def long_cor(self):
            await asyncio.sleep(1)
            self.in_error = not self.item_pipelines[0].awake

    ant = TestAnt()
    await ant.main()
    assert not ant.in_error
