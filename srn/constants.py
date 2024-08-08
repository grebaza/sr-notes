import os
import subprocess
import logging
import importlib
import typing as t
from contextlib import contextmanager

from .release import __version__

logger = logging.getLogger(__name__)


# log functions
def _warning(msg):
    import sys

    sys.stderr.write(" [WARNING] %s\n" % (msg))


def _deprecated(msg, version):
    import sys

    sys.stderr.write(" [DEPRECATED] %s, to be removed in %s\n" % (msg, version))


# git parse functions
@contextmanager
def change_directory(new_directory):
    original_directory = os.getcwd()
    try:
        os.chdir(new_directory)
        yield
    finally:
        os.chdir(original_directory)


def get_package_path(package_name):
    try:
        package = importlib.import_module(package_name)
        package_path = os.path.normpath(
            os.path.join(os.path.dirname(package.__file__), "..", "..")
        )
        return package_path
    except ImportError:
        return None


def get_last_commit_sha(package_name):
    package_path = get_package_path(package_name)
    if package_path:
        try:
            with change_directory(package_path):
                # Get the SHA of the last commit
                sha = (
                    subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], stderr=subprocess.STDOUT
                    )
                    .decode("utf-8")
                    .strip()
                )
                return sha
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.debug(f"Error: {e}")
            return None


# CONSTANTS ### yes, actual ones
APP_NAME = "srn"
VERSION_STRING = __version__
VERSION_SHA = get_last_commit_sha(APP_NAME)

APP_HOME = "~/.srn"
CONFIG_FILE = None
DEFAULT_DEBUG = False
DEFAULT_LOG_FILTER: t.List[t.Any] = []
DEFAULT_LOG_PATH = "~"
DEFAULT_VERBOSITY = 0
LOG_BACKUP_COUNT = 30
LOG_FORMAT = "[%(asctime)s] %(levelname)s %(module)s:%(message)s"
LOG_INTERVAL = 1
LOG_LEVEL = "ERROR"
LOG_ROTATION = "midnight"
LOG_TIME_ROTATION_ENABLED = True
NOTES_PATH = "~/wiki"
REVIEW_LOG_FILE = "~/wiki/review_log.json"

# http://nezzen.net/2008/06/23/colored-text-in-python-using-ansi-escape-sequences/
COLOR_CODES = {
    "black": "0;30",
    "bright gray": "0;37",
    "blue": "0;34",
    "white": "1;37",
    "green": "0;32",
    "bright blue": "1;34",
    "cyan": "0;36",
    "bright green": "1;32",
    "red": "0;31",
    "bright cyan": "1;36",
    "purple": "0;35",
    "bright red": "1;31",
    "yellow": "0;33",
    "bright purple": "1;35",
    "dark gray": "1;30",
    "bright yellow": "1;33",
    "magenta": "0;35",
    "bright magenta": "1;35",
    "normal": "0",
}
BOOL_TRUE = True
LOCALHOST = ("127.0.0.1", "localhost", "::1")
