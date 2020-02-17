import typing
import asyncio
import tempfile
import os
import webbrowser
from contextlib import contextmanager
from logging import Logger

from tenacity import retry as _retry
from tenacity.wait import wait_fixed
from tenacity.stop import stop_after_attempt


def default(value, default_value):
    return value if value is not None else default_value


def retry(
    retries: typing.Optional[int], delay: typing.Optional[float]
) -> typing.Callable[[typing.Callable], typing.Callable]:
    retries = default(retries, 3)
    delay = default(delay, 5)

    return _retry(wait=wait_fixed(delay), stop=stop_after_attempt(retries + 1),)


async def run_cor_func(func: typing.Callable, *args, **kwargs) -> typing.Any:
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)


@contextmanager
def suppress(logger: Logger):
    try:
        yield
    except Exception as e:
        logger.exception(f"Suppressed Exception {e}")
    finally:
        pass


def open_in_browser(content, file_type: str = ".html") -> bool:
    fd, path = tempfile.mkstemp(file_type)
    os.write(fd, content)
    os.close(fd)

    return webbrowser.open("file://" + path)
