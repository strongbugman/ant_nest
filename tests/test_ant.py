import pytest

from tenacity import RetryError

from ant_nest import *


@pytest.mark.asyncio
async def test_ant():
    class TestAnt(Ant):
        request_retries = 0

        async def run(self):
            await self.request('test.com')

        async def _request(self, req: Request):
            return Response(req, 200, b'1', {})

    ant = TestAnt()
    await ant.main()
    await ant.close()


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
                return Response(req, 200, b'1', {})

    await Test2Ant().request('www.test.com')
    ant = Test2Ant()
    ant.request_retries = 1
    with pytest.raises(RetryError):
        await ant.request('www.test.com')

    class Test3Ant(Test2Ant):
        async def _request(self, req: Request):
            if self.retries < self.min_retries:
                self.retries += 1
                return Response(req, 500, b'1', {})
            else:
                return Response(req, 200, b'1', {})

    await Test3Ant().request('www.test.com')
    ant = Test3Ant()
    ant.request_retries = 1
    with pytest.raises(RetryError):
        await ant.request('www.test.com')


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
