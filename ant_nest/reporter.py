import typing
from collections import defaultdict
import logging
import asyncio


class Record:
    def __init__(self):
        self.last_count = 0  # last report slot count
        self.count = 0
        self.dropped_last_count = 0
        self.dropped_count = 0

    def add(self, dropped: bool):
        if dropped:
            self.dropped_count += 1
        else:
            self.count += 1


class Reporter:
    def __init__(self, slot: float = 60):
        self._records: typing.DefaultDict[str, Record] = defaultdict(Record)
        self._slot = slot  # report once after one minute by default
        self._log_task = asyncio.ensure_future(self._log())
        self.logger = logging.getLogger(self.__class__.__name__)

    def report(self, obj: typing.Any, dropped: bool = False):
        self._records[obj.__class__.__name__].add(dropped)

    def close(self):
        self._log_task.cancel()
        for name, record in self._records.items():
            self.logger.warning(f"Get {record.count} {name} in total")
            self.logger.warning(f"Drop {record.dropped_count} {name} in total")

    async def _log(self):
        while True:
            await asyncio.sleep(self._slot)
            for name, record in self._records.items():
                count = record.count - record.last_count
                dropped_count = record.dropped_count - record.last_count
                record.last_count = record.count
                record.dropped_last_count = record.dropped_count
                self.logger.info(
                    f"Get {record.count} {name} in total with {count}/{self._slot} rate"
                )
                self.logger.info(
                    f"Drop {record.dropped_count} {name} in total with {dropped_count}/{self._slot} rate"
                )
