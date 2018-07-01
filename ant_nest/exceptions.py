import logging
import typing


__all__ = ['ThingDropped', 'ItemExtractError', 'ItemGetValueError',
           'ExceptionFilter']


class ThingDropped(Exception):
    """Raise when pipeline dropped one thing"""


class ItemExtractError(Exception):
    """For extract item"""


class ItemGetValueError(Exception):
    """Raise when get value by wrong key"""


class ExceptionFilter(logging.Filter):
    """A exception log filter class for logging.
    """

    def __init__(
            self,
            exceptions: typing.Sequence[
                typing.Type[Exception]] = (ThingDropped, ), *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exceptions = exceptions

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            for e in self.exceptions:
                if record.exc_info[0] is e:
                    return False
        return True
