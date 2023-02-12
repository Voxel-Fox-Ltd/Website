from typing import TYPE_CHECKING

from vfflags import Flags


__all__ = (
    'RequiredLogins',
)


class RequiredLogins(Flags):

    if TYPE_CHECKING:

        def __init__(self, value: int = 0, **kwargs):
            ...

        discord: bool
        google: bool
        facebook: bool
        everlasting: bool

    CREATE_FLAGS = {
        "discord": 0b0001,
        "google": 0b0010,
        "facebook": 0b0100,
        "everlasting": 0b1000,
    }
