import logging
import typing


__all__ = ["Dropped", "ItemGetValueError", "ExceptionFilter"]


class Dropped(Exception):
    """Raise when pipeline dropped one object"""


class ItemGetValueError(Exception):
    """Raise when get value by wrong key"""


class ExceptionFilter(logging.Filter):
    """A exception log filter class for logging."""

    def __init__(
        self,
        exceptions: typing.Sequence[typing.Type[Exception]] = (Dropped,),
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.exceptions = exceptions

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info:
            for e in self.exceptions:
                if record.exc_info[0] is e:
                    return False
        return True
