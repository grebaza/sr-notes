# mypy: disable-error-code = attr-defined
__metaclass__ = type


import argparse
import copy
import operator
import os
import os.path
import sys
import time

import srn as app

from ... import constants as C
from ...release import __version__
from ...utils.misc import unfrackpath
from ...utils.yaml import yaml_load


#
# Special purpose OptionParsers
#
class SortingHelpFormatter(argparse.HelpFormatter):
    def add_arguments(self, actions):
        actions = sorted(actions, key=operator.attrgetter("option_strings"))
        super(SortingHelpFormatter, self).add_arguments(actions)


class ArgumentParser(argparse.ArgumentParser):
    def add_argument(self, *args, **kwargs):
        action = kwargs.get("action")
        help = kwargs.get("help")
        if help and action in {
            "append",
            "append_const",
            "count",
            "extend",
            PrependListAction,
        }:
            help = f'{help.rstrip(".")}. This argument may be specified multiple times.'
        kwargs["help"] = help
        return super().add_argument(*args, **kwargs)


class PrintAppVersion(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        app_version = version(getattr(parser, "prog"))
        print(app_version)
        parser.exit()


class UnrecognizedArgument(argparse.Action):
    def __init__(
        self,
        option_strings,
        dest,
        const=True,
        default=None,
        required=False,
        help=None,
        metavar=None,
        nargs=0,
    ):
        super(UnrecognizedArgument, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            required=required,
            help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        parser.error("unrecognized arguments: %s" % option_string)


class PrependListAction(argparse.Action):
    """A near clone of ``argparse._AppendAction``, but designed to prepend list values
    instead of appending.
    """

    def __init__(
        self,
        option_strings,
        dest,
        nargs=None,
        const=None,
        default=None,
        type=None,
        choices=None,
        required=False,
        help=None,
        metavar=None,
    ):
        if nargs == 0:
            raise ValueError(
                "nargs for append actions must be > 0; if arg "
                "strings are not supplying the value to append, "
                "the append const action may be more appropriate"
            )
        if const is not None and nargs != argparse.OPTIONAL:
            raise ValueError("nargs must be %r to supply const" % argparse.OPTIONAL)
        super(PrependListAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=nargs,
            const=const,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        items = copy.copy(ensure_value(namespace, self.dest, []))
        items[0:0] = values
        setattr(namespace, self.dest, items)


def ensure_value(namespace, name, value):
    if getattr(namespace, name, None) is None:
        setattr(namespace, name, value)
    return getattr(namespace, name)


#
# Callbacks to validate and normalize Options
#
def unfrack_path(pathsep=False, follow=True):
    """Turn an Option's data into a single path in App locations"""

    def inner(value):
        if pathsep:
            return [unfrackpath(x, follow=follow) for x in value.split(os.pathsep) if x]

        if value == "-":
            return value

        return unfrackpath(value, follow=follow)

    return inner


def maybe_unfrack_path(beacon):
    def inner(value):
        if value.startswith(beacon):
            return beacon + unfrackpath(value[1:])
        return value

    return inner


def _git_repo_info(repo_path):
    """returns a string containing git branch, commit id and commit date"""
    result = None
    if os.path.exists(repo_path):
        # Check if the .git is a file. If it is a file, it means that we are in
        # a submodule structure.
        if os.path.isfile(repo_path):
            try:
                with open(repo_path) as f:
                    gitdir = yaml_load(f).get("gitdir")
                # There is a possibility the .git file to have an absolute path.
                if os.path.isabs(gitdir):
                    repo_path = gitdir
                else:
                    repo_path = os.path.join(repo_path[:-4], gitdir)
            except (IOError, AttributeError):
                return ""
        with open(os.path.join(repo_path, "HEAD")) as f:
            line = f.readline().rstrip("\n")
            if line.startswith("ref:"):
                branch_path = os.path.join(repo_path, line[5:])
            else:
                branch_path = None
        if branch_path and os.path.exists(branch_path):
            branch = "/".join(line.split("/")[2:])
            with open(branch_path) as f:
                commit = f.readline()[:10]
        else:
            # detached HEAD
            commit = line[:10]
            branch = "detached HEAD"
            branch_path = os.path.join(repo_path, "HEAD")

        date = time.localtime(os.stat(branch_path).st_mtime)
        if time.daylight == 0:
            offset = time.timezone
        else:
            offset = time.altzone
        result = "({0} {1}) last updated {2} (GMT {3:+04d})".format(
            branch,
            commit,
            time.strftime("%Y-%m-%d %H:%M:%S", date),
            int(offset / -36),
        )
    else:
        result = ""
    return result


def _gitinfo():
    basedir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    repo_path = os.path.join(basedir, ".git")
    return _git_repo_info(repo_path)


def version(prog=None):
    """return app version"""
    if prog:
        result = ["{0} [core {1}]".format(prog, __version__)]
    else:
        result = [__version__]

    gitinfo = _gitinfo()
    if gitinfo:
        result[0] = "{0} {1}".format(result[0], gitinfo)
    result.append("  config file = %s" % C.CONFIG_FILE)
    result.append("  app python module location = %s" % ":".join(app.__path__))
    result.append("  executable location = %s" % sys.argv[0])
    result.append(
        "  python version = %s (%s)"
        % ("".join(sys.version.splitlines()), sys.executable)
    )
    return "\n".join(result)


#
# Functions to add pre-canned options to an OptionParser
#
def create_base_parser(prog, usage="", desc=None, epilog=None):
    """
    Create an options parser for all app scripts
    """
    # base opts
    parser = ArgumentParser(
        prog=prog,
        formatter_class=SortingHelpFormatter,
        epilog=epilog,
        description=desc,
        conflict_handler="resolve",
    )
    version_help = (
        "show program's version number, config file location,"
        " module location, executable location and exit"
    )
    parser.add_argument("--version", action=PrintAppVersion, nargs=0, help=version_help)
    add_verbosity_options(parser)

    return parser


def add_verbosity_options(parser: ArgumentParser):
    """Add options for verbosity"""
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbosity",
        default=C.DEFAULT_VERBOSITY,  # type: ignore[attr-defined]
        action="count",
        help="Causes app to print more debug messages. Adding multiple -v will increase the verbosity, "
        "the builtin plugins currently evaluate up to -vvvvvv. A reasonable level to start is -vvv, "
        "connection debugging might require -vvvv.",
    )


# app options
def add_notes_path(parser: ArgumentParser):
    """Add Notes Path"""
    parser.add_argument(
        "-d",
        "--notes-path",
        action="store",
        default=C.NOTES_PATH,
        dest="notes_path",
        type=str,
        help="Path to the notes directory",
    )


def add_review_log_file(parser: ArgumentParser):
    """Add Review Log File"""
    parser.add_argument(
        "-f",
        "--review-file",
        action="store",
        default=C.REVIEW_LOG_FILE,
        dest="review_log_file",
        type=str,
        help="Path to the review log file",
    )
