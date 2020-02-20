import asyncio

import pytest

from ant_nest.pool import Pool


@pytest.mark.asyncio
async def test_schedule_task():
    pool = Pool()

    count = 0
    max_count = 10

    async def cor():
        nonlocal count
        count += 1

    for i in range(max_count):
        pool.spawn(cor())
    await pool.wait_done()
    assert count == max_count
    assert pool.done
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

    pool = Pool(limit=concurrent_limit)
    for i in range(max_count):
        pool.spawn(cor())
    assert not pool.done
    assert not pool.closed
    await pool.wait_done()
    assert count == max_count
    assert max_running_count <= concurrent_limit
    # test with exception
    count = 0
    max_count = 3

    async def coro():
        nonlocal count
        count += 1
        raise Exception("Test exception")

    for i in range(max_count):
        pool.spawn(coro())
    await pool.wait_close()
    assert pool.closed
    assert count == max_count
    # test with closed pool
    x = coro()
    pool.spawn(x)  # this coroutine will not be running
    await pool.wait_close()
    assert count == max_count
    with pytest.raises(Exception):
        await x


@pytest.mark.asyncio
async def test_as_completed():
    pool = Pool()
    count = 3

    async def cor(i):
        return i

    right_result = 0
    for c in pool.as_completed((cor(i) for i in range(count)), limit=-1):
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

    await pool.wait_close()


@pytest.mark.asyncio
async def test_as_completed_with_async():
    pool = Pool()

    async def cor(x):
        if x < 0:
            raise Exception("Test exception")
        return x

    result_sum = 0
    async for result in pool.as_completed_with_async((cor(i) for i in range(5))):
        result_sum += result
    assert result_sum == sum(range(5))

    result_sum = 0
    async for result in pool.as_completed_with_async(
        (cor(i - 2) for i in range(5)), raise_exception=False
    ):
        result_sum += result
    assert result_sum == sum(range(3))

    async for _ in pool.as_completed_with_async([cor(-1)], raise_exception=False):
        assert _
        raise Exception("This loop should not be entered!")

    with pytest.raises(Exception):
        async for _ in pool.as_completed_with_async([cor(-1)]):
            assert _

    pool.close()
