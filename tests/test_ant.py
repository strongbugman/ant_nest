import asyncio
import os

import pytest
import httpx
from tenacity import RetryError

from ant_nest.pipelines import Pipeline
from ant_nest.ant import CliAnt, Ant
from ant_nest.exceptions import ThingDropped
from .test_things import fake_response


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

        async def _send(self, req, *args, **kwargs):
            return fake_response(b"")

    ant = TestAnt()
    assert ant.name == "TestAnt"
    await ant.main()

    class Test2Ant(TestAnt):
        async def run(self):
            raise Exception("This exception will be suppressed")

    await Test2Ant().main()


@pytest.mark.asyncio
async def test_ant_with_retry():
    class Test2Ant(Ant):
        def __init__(self):
            super().__init__()
            self.min_retries = 2
            self.retries = 0

        async def run(self):
            pass

        async def _send(self, req, *args, **kwargs):
            if self.retries < self.min_retries:
                self.retries += 1
                raise httpx.exceptions.ConnectTimeout()
            else:
                return fake_response(b"")

    ant = Test2Ant()
    # default retry params
    res = await ant.request("https://www.test.com", retry_delay=0.1)
    assert res.status_code == 200
    # set retry params
    ant.retries = 0
    with pytest.raises(RetryError):
        await ant.request("https://www.test.com", retries=1, retry_delay=0.1)
    # disable retry
    ant.retries = 0
    with pytest.raises(httpx.ConnectTimeout):
        await ant.request("https://www.test.com", retries=0)
    await ant.main()


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
async def test_ant_report():
    class FakePipeline(Pipeline):
        def process(self, thing):
            if thing.host == "error":
                raise ThingDropped
            return thing

    class FakeAnt(Ant):
        request_pipelines = [FakePipeline()]
        request_retries = 0

        async def run(self):
            pass

        async def _send(self, req, *args, **kwargs):
            return fake_response(b"")

    ant = FakeAnt()
    # request report
    await ant.request("http://test.com")
    assert ant._reports["Request"][1] == 1
    assert ant._reports["Request"][0] == 0
    with pytest.raises(ThingDropped):
        await ant.request("http://error")
    assert ant._drop_reports["Request"][1] == 1

    ant._last_time -= ant._last_time + 1  # report
    ant.report(httpx.Request("GET", "http://test"))
    assert ant._reports["Request"][0] == 1
    ant.report(httpx.Request("GET", "http://test"), dropped=True)
    assert ant._drop_reports["Request"][0] == 1

    await ant.main()


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
        # short way
        res = await ant.request(httpbin_base_url + "anything", method=method)
        assert res.status_code == 200
        if method != "HEAD":
            assert res.json()["method"] == method
        else:
            assert res.text == ""
    # params
    res = await ant.request(httpbin_base_url + "get?k1=v1&k2=v2")
    assert res.status_code == 200
    assert res.json()["args"]["k1"] == "v1"
    assert res.json()["args"]["k2"] == "v2"
    res = await ant.request(httpbin_base_url + "get", params={"k1": "v1", "k2": "v2"})
    assert res.status_code == 200
    assert res.json()["args"]["k1"] == "v1"
    assert res.json()["args"]["k2"] == "v2"
    # data with str
    res = await ant.request(httpbin_base_url + "post", data="Test data", method="POST")
    assert res.status_code == 200
    assert res.json()["data"] == "Test data"
    # data with dict
    res = await ant.request(httpbin_base_url + "post", method="POST", data={"k1": "v1"})
    assert res.status_code == 200
    assert res.json()["form"]["k1"] == "v1"
    # data with bytes
    res = await ant.request(httpbin_base_url + "post", method="POST", data=b"12345")
    assert res.status_code == 200
    assert res.json()["data"] == "12345"
    # data with file
    with open("tests/test.html", "r") as f:
        file_content = f.read()
        f.seek(0)
        res = await ant.request(httpbin_base_url + "post", method="POST", files=f)
        assert res.status_code == 200
        assert res.json()["data"] == file_content
    # headers
    res = await ant.request(
        httpbin_base_url + "headers", headers={"Custom-Key": "test"}
    )
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "application/json"
    assert res.json()["headers"]["Custom-Key"] == "test"
    # cookies
    res = await ant.request(
        httpbin_base_url + "cookies", cookies={"Custom-Key": "test"}
    )
    assert res.status_code == 200
    assert res.json()["cookies"]["Custom-Key"] == "test"
    # get cookies
    ant.request_allow_redirects = False
    res = await ant.request(httpbin_base_url + "cookies/set?k1=v1&k2=v2")
    assert res.status_code == 302
    assert res.cookies["k1"] == "v1"
    assert res.cookies["k2"] == "v2"
    # redirects
    ant.request_allow_redirects = True
    ant.request_max_redirects = 3
    res = await ant.request(httpbin_base_url + "redirect/2")
    assert res.status_code == 200
    ## with http proxy
    # proxy = os.getenv("TEST_HTTP_PROXY", "http://bugman:letmein@localhost:3128")
    # ant.request_proxies.append(proxy)
    # res = await ant.request("http://httpbin.org/anything")
    # assert res.status_code == 200
    ## no proxy anymore
    # ant.request_proxies.pop()
    # res = await ant.request("http://httpbin.org/anything")
    # assert res.status_code == 200
    ## set proxy by request
    # res = await ant.request("http://httpbin.org/anything", proxy=proxy)
    # assert res.status_code == 200
    # with stream
    res = await ant.request(httpbin_base_url + "anything", stream=True)
    assert res.status_code == 200
    async for _ in res.aiter_bytes():
        pass
    assert res.is_stream_consumed

    await ant.close()


@pytest.mark.asyncio
async def test_schedule_task():
    count = 0
    max_count = 10

    async def cor():
        nonlocal count
        count += 1

    ant = CliAnt()

    ant.schedule_tasks((cor() for i in range(max_count)))
    await ant.wait_scheduled_tasks()
    assert count == max_count
    # test with limit
    count = 0
    running_count = 0
    max_running_count = -1
    concurrent_limit = 3

    async def cor():
        nonlocal count, running_count, max_running_count
        running_count += 1
        max_running_count = max(running_count, max_running_count)
        await asyncio.sleep(0.1)
        count += 1
        running_count -= 1

    ant.concurrent_limit = concurrent_limit
    ant.schedule_tasks(cor() for i in range(max_count))
    assert ant.is_running
    await ant.wait_scheduled_tasks()
    assert count == max_count
    assert max_running_count <= concurrent_limit
    # test with exception
    count = 0
    max_count = 3

    async def coro():
        nonlocal count
        count += 1
        raise Exception("Test exception")

    ant.schedule_tasks(coro() for i in range(max_count))
    await ant.wait_scheduled_tasks()
    assert count == max_count

    # test with closed ant
    await ant.close()

    x = coro()
    ant.schedule_task(x)  # this coroutine will not be running
    await ant.close()
    assert count == max_count
    with pytest.raises(Exception):
        await x


@pytest.mark.asyncio
async def test_as_completed():
    ant = CliAnt(loop=asyncio.get_event_loop())
    count = 3

    async def cor(i):
        return i

    right_result = 0
    for c in ant.as_completed((cor(i) for i in range(count)), limit=-1):
        await c
        right_result += 1
    assert right_result == count

    async def cor(i):
        await asyncio.sleep(i * 0.1)
        return i

    right_result = 0  # 0, 1, 2
    for c in ant.as_completed((cor(i) for i in reversed(range(count)))):
        result = await c
        assert result == right_result
        right_result += 1
    assert right_result == count
    # with limit
    right_result = 2  # 2, 1, 0
    for c in ant.as_completed((cor(i) for i in reversed(range(count))), limit=1):
        result = await c
        assert result == right_result
        right_result -= 1
    assert right_result == -1

    await ant.close()


@pytest.mark.asyncio
async def test_as_completed_with_async():

    ant = CliAnt()

    async def cor(x):
        if x < 0:
            raise Exception("Test exception")
        return x

    result_sum = 0
    async for result in ant.as_completed_with_async((cor(i) for i in range(5))):
        result_sum += result
    assert result_sum == sum(range(5))

    result_sum = 0
    async for result in ant.as_completed_with_async(
        (cor(i - 2) for i in range(5)), raise_exception=False
    ):
        result_sum += result
    assert result_sum == sum(range(3))

    async for _ in ant.as_completed_with_async([cor(-1)], raise_exception=False):
        assert _
        raise Exception("This loop should not be entered!")

    with pytest.raises(Exception):
        async for _ in ant.as_completed_with_async([cor(-1)]):
            assert _

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
            self.schedule_task(self.long_cor())

        async def long_cor(self):
            await asyncio.sleep(1)
            self.in_error = not self.item_pipelines[0].awake

    ant = TestAnt()
    await ant.main()
    assert not ant.in_error
