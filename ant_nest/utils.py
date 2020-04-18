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


def retry(
    retries: int, delay: float
) -> typing.Callable[[typing.Callable], typing.Callable]:
    return _retry(
        wait=wait_fixed(delay), stop=stop_after_attempt(retries + 1), reraise=True
    )


async def run_cor_func(func: typing.Callable, *args, **kwargs) -> typing.Any:
    ret = func(*args, **kwargs)
    if asyncio.iscoroutine(ret):
        ret = await ret

    return ret


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
