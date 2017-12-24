import asyncio
from asyncio.unix_events import _UnixSelectorEventLoop

import pytest

from ant_nest import queen


@pytest.yield_fixture()
def event_loop():
    loop = _UnixSelectorEventLoop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_schedule_coroutine():
    count = 0
    max_count = 10

    async def cor():
        nonlocal count
        count += 1

    queen.init_loop(loop=asyncio.get_event_loop())
    queen.reset_concurrent_limit(30)
    queen.schedule_coroutines((cor() for i in range(max_count)))
    await queen.wait_scheduled_coroutines()
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

    queen.reset_concurrent_limit(concurrent_limit)
    queen.schedule_coroutines(cor() for i in range(max_count))
    await queen.wait_scheduled_coroutines()
    assert count == max_count
    assert max_running_count <= concurrent_limit


@pytest.mark.asyncio
async def test_as_completed(event_loop):
    count = 3

    async def cor(i):
        await asyncio.sleep(i * 0.1)
        return i

    right_result = 0  # 0, 1, 2
    for c in queen.as_completed((cor(i) for i in reversed(range(count))), loop=event_loop):
        result = await c
        assert result == right_result
        right_result += 1

    # with limit
    right_result = 2  # 2, 1, 0
    for c in queen.as_completed((cor(i) for i in reversed(range(count))), loop=event_loop, limit=1):
        result = await c
        assert result == right_result
        right_result -= 1


def test_get_loop():
    loop = _UnixSelectorEventLoop()
    queen.init_loop(loop)

    assert queen.get_loop() is loop


@pytest.mark.asyncio
async def test_timeout():

    async def cor():
        await asyncio.sleep(2)

    with pytest.raises(asyncio.TimeoutError):
        await queen.timeout_wrapper(cor(), timeout=0.1)

    async def bar():
        await queen.timeout_wrapper(cor(), timeout=0.1)

    with pytest.raises(asyncio.TimeoutError):
        await queen.timeout_wrapper(bar(), timeout=0.2)
