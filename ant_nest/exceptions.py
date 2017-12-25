__all__ = ['ThingDropped', 'FieldValidationError', 'ItemExtractError', 'QueenError']


class ThingDropped(Exception):
    """Raise when pipeline dropped one thing"""


class FieldValidationError(Exception):
    pass


class ItemExtractError(Exception):
    """For extract item"""


class QueenError(Exception):
    """For "queen" module"""
