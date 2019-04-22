import typing
import asyncio


async def run_cor_func(func: typing.Callable, *args, **kwargs) -> typing.Any:
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)
