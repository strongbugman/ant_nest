import typing
import asyncio
import logging
from collections import defaultdict
import ujson
import os
import random
import re

import aiofiles
from aiohttp.http import SERVER_SOFTWARE
from aiohttp import hdrs

from .things import (Things, Response, Request, Item, set_value_to_item,
                     get_value_from_item)
from .exceptions import ThingDropped


class Pipeline:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    async def on_spider_open(self) -> None:
        """Call when ant open, this method can be coroutine function"""

    async def on_spider_close(self) -> None:
        """Call when ant close, this method can be coroutine function"""

    async def process(self, thing: Things) -> Things:
        """Process things, this method can be coroutine function
        Raise ThingDropped when drop one thing

        :raise ThingDropped
        """
        return thing


# Response pipelines
class ResponseFilterErrorPipeline(Pipeline):
    def process(self, thing: Response) -> typing.Union[Things, Exception]:
        if thing.status >= 400:
            raise ThingDropped('Respose status is {:d}'.format(thing.status))
        else:
            return thing


# Request pipelines
class RequestDuplicateFilterPipeline(Pipeline):
    def __init__(self):
        self.__request_urls = set()
        super().__init__()

    def process(self, thing: Request) -> typing.Union[Things, Exception]:
        if thing.url in self.__request_urls:
            raise ThingDropped('Request duplicate!')
        else:
            self.__request_urls.add(thing.url)
            return thing


class RequestUserAgentPipeline(Pipeline):
    user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' \
                 '(KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'

    def __init__(self, user_agent=user_agent):
        super().__init__()
        self.user_agent = user_agent

    def process(self, thing: Request) -> Request:
        if thing.headers.get(hdrs.USER_AGENT) == SERVER_SOFTWARE:
            thing.headers[hdrs.USER_AGENT] = self.user_agent
        return thing


class RequestRandomUserAgentPipeline(Pipeline):
    """Create simple and common user agent for request by random,
    It`s easy to add new rule.
    """
    USER_AGENT_FORMAT = 'Mozilla/5.0 ({system}) {browser}'
    SYSTEM_FORMATS = {
        'UnixLike': 'X11; {unix-like_os} {cpu_type}',
        'MacOS': 'Macintosh; Intel Mac OS X {macos_version}',
        'Windows': 'Windows NT {windows_version}',
        'Android': 'Android {android_version}; Linux',
        'iOS': '{ios_driver}; CPU OS {ios_version} like Mac OS X',
    }
    BROWSER_FORMATS = {
        'Firefox': 'Gecko/20100101 Firefox/{firefox_version}',
        'Safari': 'AppleWebKit/{webkit_version} (KHTML, like Gecko) '
                  'Version/{safari_version} Safari/{safari_version2}',
        'Chrome': 'AppleWebKit/{webkit_version} (KHTML, like Gecko) '
                  'Chrome/{chrome_version} Safari/{safari_version2}',
    }
    FORMAT_VARS = {
        'unix-like_os': ('Linux', 'FreeBSD'),
        'cpu_type': ('x86_64', 'i386', 'amd64'),
        'macos_version': (
            '10_10_1', '10_11_1', '10_11_2', '10_12_2', '10_12_3', '10_13_3'),
        'windows_version': ('5_0', '5_1', '5_2', '6_0', '6_1', '10_0'),
        'android_version': (
            '4_4', '5_0', '5_1', '6_0', '6_1', '7_0', '7_1', '8_0'),
        'ios_driver': ('iPone', 'iPod', 'iPad'),
        'ios_version': (
            '6_0', '7_0', '8_1', '9_2', '10_3', '10_2_3', '11_3_3'),
        'firefox_version': ('27.3', '28.0', '31.0', '40.1'),
        'webkit_version': ('533.18.1', '533.19.4', '533.20.25', '534.55.3'),
        'safari_version': ('4.0.1', '5.0.4', '5.1.3', '6.0', '7.0.3'),
        'safari_version2': ('530.19.1', '531.9', '533.16', '533.20.27'),
        'chrome_version': (
            '41.0.2226.0', '60.0.1325.223', '62.0.1532.123', '64.0.3282.119')
    }

    def __init__(self, system: str = 'random', browser: str = 'random'):
        if system != 'random' and system not in self.SYSTEM_FORMATS.keys():
            raise ValueError(
                'The system {:s} is not supported!'.format(system))
        if browser != 'random' and browser not in self.BROWSER_FORMATS.keys():
            raise ValueError(
                'The browser {:s} is not supported!'.format(browser))

        self.system = system
        self.browser = browser
        super().__init__()

    @staticmethod
    def choice(data: typing.Sequence[str]) -> str:
        return random.choice(data)

    def _format(self, pattern: str) -> str:
        """format system or browser pattern string"""
        kv = {}
        keys = re.findall('{(\S+?)}', pattern)

        for key in keys:
            kv[key] = self.choice(self.FORMAT_VARS[key])

        return pattern.format(**kv)

    def create(self) -> str:
        if self.system != 'random':
            system_format = self.SYSTEM_FORMATS[self.system]
        else:
            system_format = self.SYSTEM_FORMATS[
                self.choice(list(self.SYSTEM_FORMATS.keys()))]

        if self.browser != 'random':
            browser_format = self.BROWSER_FORMATS[self.browser]
        else:
            browser_format = self.BROWSER_FORMATS[
                self.choice(list(self.BROWSER_FORMATS.keys()))]

        return self.USER_AGENT_FORMAT.format(
            system=self._format(system_format),
            browser=self._format(browser_format))

    def process(self, thing: Request) -> Request:
        if thing.headers.get(hdrs.USER_AGENT) == SERVER_SOFTWARE:
            thing.headers[hdrs.USER_AGENT] = self.create()
        return thing


class RequestRandomComputerUserAgentPipeline(Pipeline):
    SYSTEM_FORMATS = {
        'UnixLike': 'X11; {unix-like_os} {cpu_type}',
        'MacOS': 'Macintosh; Intel Mac OS X {macos_version}',
        'Windows': 'Windows NT {windows_version}',
    }


class RequestRandomMobileUserAgentPipeline(Pipeline):
    SYSTEM_FORMATS = {
        'Android': 'Android {android_version}; Linux',
        'iOS': '{ios_driver}; CPU OS {ios_version} like Mac OS X',
    }


# Item pipelines
class ItemPrintPipeline(Pipeline):
    def process(self, thing: Item) -> Item:
        self.logger.info(thing.__repr__())
        return thing


class ItemFieldReplacePipeline(Pipeline):
    """Replace some chars in item`s field string"""
    def __init__(self, fields: typing.Sequence[str],
                 excess_chars: typing.Tuple[str, ...] = ('\r', '\n', '\t')):
        self.fields = fields
        self.excess_chars = excess_chars
        super().__init__()

    def process(self, thing: Item) -> Item:
        for field in self.fields:
            value: str = get_value_from_item(thing, field)
            for char in self.excess_chars:
                value = value.replace(char, '')
            set_value_to_item(thing, field, value)
        return thing


class ItemBaseFileDumpPipeline(Pipeline):

    @classmethod
    async def dump(cls, file_path: str,
                   data: typing.Union[typing.AnyStr, typing.IO],
                   buffer_size: int = 1024 * 1024) -> None:
        """Dump data(binary or text, stream or normal, async or not) to disk file.
        typing.IO data will be closed.
        """
        chunk: typing.Optional[typing.AnyStr] = None
        if isinstance(data, str):
            file_mode = 'w'
        elif isinstance(data, bytes):
            file_mode = 'wb'
        elif hasattr(data, 'read'):  # readable
            chunk = data.read(buffer_size)
            if asyncio.iscoroutine(chunk):
                chunk = await chunk

            if isinstance(chunk, str):
                file_mode = 'w'
            else:
                file_mode = 'wb'
        else:
            raise ValueError('The type {:s} is not supported'.format(
                type(data).__class__.__name__))

        async with aiofiles.open(file_path, file_mode) as file:
            if chunk is not None:  # in streaming
                await file.write(chunk)
                while True:

                    chunk = data.read(buffer_size)
                    if asyncio.iscoroutine(chunk):
                        chunk = await chunk

                    if len(chunk) == 0:
                        break
                    else:
                        await file.write(chunk)

                result = data.close()
                if asyncio.iscoroutine(result):
                    await result
            else:
                await file.write(data)


class ItemJsonDumpPipeline(ItemBaseFileDumpPipeline):
    """Dump item to json during pipeline closing"""

    def __init__(
            self, *, to_dict: typing.Callable[[Item], typing.Dict],
            file_dir: str = '.'):
        super().__init__()
        self.file_dir = file_dir
        self.data: typing.DefaultDict[
            str, typing.List[typing.Dict]] = defaultdict(list)
        self.to_dict = to_dict

    def process(self, thing: Item) -> Item:
        self.data[thing.__class__.__name__].append(self.to_dict(thing))
        return thing

    async def on_spider_close(self) -> None:
        for file_name, data in self.data.items():
            data = ujson.dumps(data)
            await self.dump(os.path.join(self.file_dir, file_name + '.json'),
                            data)


__all__ = [var for var in vars().keys() if 'Pipeline' in var]
