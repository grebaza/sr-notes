"""Customize logging

Defines custom logger class for the `logger.verbose(...)` method.

init_logging() must be called before any other modules that call logging.getLogger.
"""

# mypy: disable-error-code = attr-defined

import logging
import sys
from abc import ABC, abstractmethod
from logging.handlers import TimedRotatingFileHandler
from typing import Any, cast

from .. import constants as C

# custom log level for `--verbose` output, between DEBUG and INFO
VERBOSE = 15


class VerboseLogger(logging.Logger):
    """
    Custom Logger that defines a ``verbose`` log-level.

    VERBOSE is between INFO and DEBUG.
    """

    def verbose(self, msg: str, *args: Any, **kwargs: Any) -> None:
        return self.log(VERBOSE, msg, *args, **kwargs)


def getLogger(name: str) -> VerboseLogger:
    """logging.getLogger, but ensures our VerboseLogger class is returned"""
    return cast(VerboseLogger, logging.getLogger(name))


def init_logging() -> None:
    """Register our VerboseLogger and VERBOSE log level.

    Should be called before any calls to getLogger(),
    """
    DefaultLoggingConfigurator().configure()
    logging.setLoggerClass(VerboseLogger)
    logging.addLevelName(VERBOSE, "VERBOSE")


class LoggingConfigurator(ABC):  # pylint: disable=too-few-public-methods
    @abstractmethod
    def configure(self, debug_mode: bool) -> logging.Logger:
        pass


class DefaultLoggingConfigurator(LoggingConfigurator):
    def configure(self, debug_mode: bool = False) -> logging.Logger:
        logging.captureWarnings(capture=True)
        # create a logger
        logger = logging.getLogger(C.APP_NAME)
        logger.setLevel(C.LOG_LEVEL)  # type: ignore[attr-defined]

        # create a formatter
        formatter = logging.Formatter(C.LOG_FORMAT)  # type: ignore[attr-defined]

        # in production mode, add log handler to sys.stderr.
        if not C.DEFAULT_DEBUG:  # type: ignore[attr-defined]
            stderr_handler = logging.StreamHandler(sys.stderr)
            stderr_handler.setFormatter(formatter)
            logger.addHandler(stderr_handler)

        # add a time-rotate handler
        if C.LOG_TIME_ROTATION_ENABLED and C.DEFAULT_LOG_PATH:  # type: ignore[attr-defined]
            handler = TimedRotatingFileHandler(
                C.DEFAULT_LOG_PATH,
                when=C.LOG_ROTATION,
                interval=C.LOG_INTERVAL,
                backupCount=C.LOG_BACKUP_COUNT,
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        # add filters
        for log_filter in C.DEFAULT_LOG_FILTER:  # type: ignore[attr-defined]
            logger.addFilter(log_filter)

        logger.debug("logging was configured successfully")

        return logger
