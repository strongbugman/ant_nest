__all__ = ['ThingDropped', 'ItemExtractError']


class ThingDropped(Exception):
    """Raise when pipeline dropped one thing"""


class ItemExtractError(Exception):
    """For extract item"""


class ItemGetValueError(Exception):
    """Raise when get value by wrong key"""
