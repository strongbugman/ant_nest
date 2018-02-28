import asyncio
from asyncio.unix_events import _UnixSelectorEventLoop

import pytest

from ant_nest import CoroutinesPool, timeout_wrapper


@pytest.yield_fixture()
def event_loop():
    loop = _UnixSelectorEventLoop()
    yield loop
    loop.close()


def test_pool():
    loop = _UnixSelectorEventLoop()
    pool = CoroutinesPool(loop=loop, timeout=3)
    pool.__repr__()

    assert pool.loop is loop
    assert pool.limit == -1
    assert pool.timeout == 3
    assert pool.raise_exception
    assert pool.running_count == 0
    assert not pool.is_running
    assert pool.status == 'ready'

    pool.reset(limit=1, raise_exception=False)
    assert pool.limit == 1
    assert pool.timeout == 3
    assert not pool.raise_exception

    pool._running_count = 1
    del pool
    pool = CoroutinesPool()
    del pool


@pytest.mark.asyncio
async def test_schedule_coroutine():
    count = 0
    max_count = 10

    async def cor():
        nonlocal count
        count += 1

    pool = CoroutinesPool(limit=20)

    pool.schedule_coroutines((cor() for i in range(max_count)))
    await pool.wait_scheduled_coroutines()
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

    pool.reset(limit=concurrent_limit)
    pool.schedule_coroutines(cor() for i in range(max_count))
    await pool.wait_scheduled_coroutines()
    assert count == max_count
    assert max_running_count <= concurrent_limit

    # test with exception
    count = 0
    max_count = 3

    async def coro():
        nonlocal count
        count += 1
        raise Exception('Test exception')

    pool.schedule_coroutines(coro() for i in range(max_count))
    await pool.wait_scheduled_coroutines()
    assert count == max_count

    pool.reset(raise_exception=False)
    pool.schedule_coroutines(coro() for i in range(max_count))
    assert pool.status == 'running'
    await pool.close()
    assert count == max_count * 2
    assert pool.status == 'closed'

    x = coro()
    pool.schedule_coroutine(x)  # this coroutine will not be running
    await pool.close()
    assert count == max_count * 2

    with pytest.raises(Exception):
        await x


@pytest.mark.asyncio
async def test_as_completed(event_loop):
    pool = CoroutinesPool(loop=event_loop)

    count = 3

    async def cor(i):
        return i

    right_result = 0
    for c in pool.as_completed((cor(i) for i in range(count))):
        await c
        right_result += 1
    assert right_result == count

    async def cor(i):
        await asyncio.sleep(i * 0.1)
        return i

    right_result = 0  # 0, 1, 2
    for c in pool.as_completed((cor(i) for i in reversed(range(count)))):
        result = await c
        assert result == right_result
        right_result += 1
    assert right_result == count

    # with limit
    right_result = 2  # 2, 1, 0
    for c in pool.as_completed((cor(i) for i in reversed(range(count))), limit=1):
        result = await c
        assert result == right_result
        right_result -= 1
    assert right_result == -1

    await pool.close()


@pytest.mark.asyncio
async def test_timeout():

    async def cor():
        await asyncio.sleep(2)

    with pytest.raises(asyncio.TimeoutError):
        await timeout_wrapper(cor(), timeout=0.1)

    with pytest.raises(asyncio.TimeoutError):
        await timeout_wrapper(cor, timeout=0.1)()

    async def bar():
        await timeout_wrapper(cor(), timeout=0.1)

    with pytest.raises(asyncio.TimeoutError):
        await timeout_wrapper(bar(), timeout=0.2)


@pytest.mark.asyncio
async def test_as_completed_with_async():

    pool = CoroutinesPool(loop=asyncio.get_event_loop(), raise_exception=False)

    async def cor(x):
        if x < 0:
            raise Exception('Test exception')
        return x

    result_sum = 0
    async for result in pool.as_completed_with_async((cor(i) for i in range(5))):
        result_sum += result
    assert result_sum == sum(range(5))

    result_sum = 0
    async for result in pool.as_completed_with_async((cor(i - 2) for i in range(5))):
        result_sum += result
    assert result_sum == sum(range(3))

    async for result in pool.as_completed_with_async([cor(-1)]):
        raise Exception('This loop should not be entered!')

    with pytest.raises(Exception):
        async for result in pool.as_completed_with_async([cor(-1)], raise_exception=True):
            pass

    await pool.close()
