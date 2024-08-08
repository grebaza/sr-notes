"""Exceptions used throughout package.

This is expected to be importable from any/all files within the
subpackage and, thus, should not depend on them.
"""

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass


#
# Scaffolding
#
def _is_kebab_case(s: str) -> bool:
    return re.match(r"^[a-z]+(-[a-z]+)*$", s) is not None


class AppError(Exception):
    """The base app error."""

    def __init__(self, message="", orig_exc=None):
        super(AppError, self).__init__(message)

        self._message = message
        self.orig_exc = orig_exc

    @property
    def message(self):
        message = [self._message]
        if self.orig_exc:
            message.append(". %s" % self.orig_exc)

        return "".join(message)

    @message.setter
    def message(self, val):
        self._message = val

    def __str__(self):
        return self.message

    def __repr__(self):
        return self.message


#
# Actual Errors
#
class ConfigurationError(AppError):
    """General exception in configuration"""


class BadCommand(AppError):
    """Raised when virtualenv or a command is not found"""


class CommandError(AppError):
    """Raised when there is an error in command-line arguments"""


class ConfigurationFileCouldNotBeLoaded(ConfigurationError):
    """When there are errors while loading a configuration file"""

    def __init__(
        self,
        reason: str = "could not be loaded",
        fname: Optional[str] = None,
        error: Optional[Exception] = None,
    ) -> None:
        super().__init__(error)
        self.reason = reason
        self.fname = fname
        self.error = error

    def __str__(self) -> str:
        if self.fname is not None:
            message_part = f" in {self.fname}."
        else:
            assert self.error is not None
            message_part = f".\n{self.error}\n"
        return f"Configuration file {self.reason}{message_part}"
