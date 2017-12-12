class ThingDropped(Exception):
    """Raise when pipeline dropped a thing"""


class FieldValidationError(Exception):
    pass


class ItemExtractError(Exception):
    """Raise when extract item when error"""
