"""Utilities box"""
import typing
import asyncio

import async_timeout


__all__ = ['timeout_wrapper']


def timeout_wrapper(
        coro_or_func: typing.Union[typing.Coroutine, typing.Callable],
        timeout: typing.Union[float, int]
) -> typing.Union[typing.Coroutine, typing.Callable]:
    """Add timeout limit to coroutine or coroutine function"""
    is_coroutinefunction = asyncio.iscoroutinefunction(coro_or_func)

    async def wrapper(*args, **kwargs):
        with async_timeout.timeout(timeout):
            if is_coroutinefunction:
                return await coro_or_func(*args, **kwargs)
            else:
                return await coro_or_func

    if timeout < 0:
        return coro_or_func
    elif is_coroutinefunction:
        return wrapper
    else:
        return wrapper()
