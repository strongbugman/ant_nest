__all__ = ['ThingDropped', 'ItemExtractError']


class ThingDropped(Exception):
    """Raise when pipeline dropped one thing"""


class ItemExtractError(Exception):
    """For extract item"""
