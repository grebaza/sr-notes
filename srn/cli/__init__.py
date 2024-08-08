__metaclass__ = type
import logging
import sys

# Used for determining if the system is running a new enough python version
# and should only restrict on our documented minimum versions
if sys.version_info < (3, 10):
    raise SystemExit(
        "ERROR: App requires Python 3.10 or newer. "
        "Current version: %s" % "".join(sys.version.splitlines())
    )

import errno
import traceback
from abc import ABC, abstractmethod
from pathlib import Path

try:
    from .. import constants as C
except Exception as e:
    print("ERROR: %s" % e, file=sys.stderr)
    sys.exit(5)

from ..exceptions import AppError, ConfigurationError
from ..release import __version__
from .arguments import option_helpers as opt_help

try:
    import argcomplete

    HAS_ARGCOMPLETE = True
except ImportError:
    HAS_ARGCOMPLETE = False

logger = logging.getLogger(__name__)


class CLIArgs(dict):
    """
    Hold a parsed copy of cli arguments
    """

    def __init__(self, mapping):
        toplevel = {}
        for key, value in mapping.items():
            toplevel[key] = value
        super(CLIArgs, self).__init__(toplevel)

    @classmethod
    def from_mapping(cls, mapping):
        return cls(vars(mapping))


class CLI(ABC):
    def __init__(self, args, callback=None):
        """
        Base init method for all command line programs
        """

        if not args:
            raise ValueError("A non-empty list for args is required")

        self.args = args
        self.parser = None
        self.callback = callback
        self.cli_args = None  # parsed options

    @abstractmethod
    def run(self):
        """Run the application command

        Subclasses must implement this method.  It does the actual work of
        running a command.
        """

        self.parse()

        logger.debug(opt_help.version(self.parser.prog))

        if C.CONFIG_FILE:
            logger.verbose("Using %s as config file" % C.CONFIG_FILE)
        else:
            logger.verbose("No config file found; using defaults")

        # warn about deprecated config options
        try:
            for deprecated in C.config.DEPRECATED:
                name = deprecated[0]
                why = deprecated[1]["why"]
                if "alternatives" in deprecated[1]:
                    alt = ", use %s instead" % deprecated[1]["alternatives"]
                else:
                    alt = ""
                ver = deprecated[1].get("version")  # noqa: F841
                date = deprecated[1].get("date")  # noqa: F841
                logger.warn("%s option, %s%s" % (name, why, alt))
        except AttributeError:
            return

    @abstractmethod
    def init_parser(self, usage="", desc=None, epilog=None):
        """
        Create an options parser for application scripts

        Subclasses need to implement this method.  They will usually call the
        base class's init_parser to create a basic version and then add their
        own options on top of that.

        An implementation will look something like this::

            def init_parser(self):
                super(MyCLI, self).init_parser(usage="My App CLI")
                app.arguments.option_helpers.add_verbosity_options(self.parser)
                self.parser.add_option('--my-option', dest='my_option', action='store')
        """
        self.parser = opt_help.create_base_parser(
            self.name, usage=usage, desc=desc, epilog=epilog
        )

    @abstractmethod
    def post_process_args(self, options):
        """Process the command line args

        Subclasses need to implement this method.  This method validates and
        transforms the command line arguments.  It can be used to check whether
        conflicting values were given, whether filenames exist, etc.

        An implementation will look something like this::

            def post_process_args(self, options):
                options = super(MyCLI, self).post_process_args(options)
                if options.addition and options.subtraction:
                    raise ConfigurationError('Only one of --addition and --subtraction can be specified')
                if isinstance(options.listofhosts, string_types):
                    options.listofhosts = string_types.split(',')
                return options
        """

        return options

    def parse(self):
        """Parse the command line args

        This method parses the command line arguments.  It uses the parser
        stored in the self.parser attribute and saves the args and options in
        self.cli_args.

        Subclasses need to implement two helper methods, init_parser() and
        post_process_args() which are called from this function before and
        after parsing the arguments.
        """
        self.init_parser()

        if HAS_ARGCOMPLETE:
            argcomplete.autocomplete(self.parser)

        try:
            options = self.parser.parse_args(self.args[1:])
        except SystemExit as ex:
            if ex.code != 0:
                self.parser.exit(status=2, message=" \n%s" % self.parser.format_help())
            raise
        options = self.post_process_args(options)
        self.cli_args = CLIArgs.from_mapping(options)

    @staticmethod
    def version_info(gitinfo=False):
        """return full version info"""
        if gitinfo:
            # expensive call, user with care
            app_version_string = opt_help.version()
        else:
            app_version_string = __version__
        app_version = app_version_string.split()[0]
        app_versions = app_version.split(".")
        for counter in range(len(app_versions)):
            if app_versions[counter] == "":
                app_versions[counter] = 0
            try:
                app_versions[counter] = int(app_versions[counter])
            except Exception:
                pass
        if len(app_versions) < 3:
            for counter in range(len(app_versions), 3):
                app_versions.append(0)
        return {
            "string": app_version_string.strip(),
            "full": app_version,
            "major": app_versions[0],
            "minor": app_versions[1],
            "revision": app_versions[2],
        }

    @classmethod
    def cli_executor(cls, args=None):
        if args is None:
            args = sys.argv

        try:
            logger.debug("starting run")

            app_dir = Path(C.APP_HOME).expanduser()
            try:
                app_dir.mkdir(mode=0o700)
            except OSError as exc:
                if exc.errno != errno.EEXIST:
                    logger.warning(
                        "Failed to create the directory '%s': %s" % (app_dir, exc)
                    )
            else:
                logger.debug("Created the '%s' directory" % app_dir)

            cli = cls(args)
            exit_code = cli.run()

        except ConfigurationError as e:
            cli.parser.print_help()
            logger.error(e)
            exit_code = 5
        except AppError as e:
            logger.error(e)
            exit_code = 1
        except KeyboardInterrupt:
            logger.error("User interrupted execution")
            exit_code = 99
        except Exception as e:
            if C.DEFAULT_DEBUG:
                # Show raw stacktraces in debug mode, It also allow pdb to
                # enter post mortem mode.
                raise
            have_cli_options = bool(cli.cli_args)
            logger.error(
                "Unexpected Exception, this is probably a bug: %s" % e,
            )
            if (
                not have_cli_options
                or have_cli_options
                and cli.cli_args["verbosity"] > 2
            ):
                log_only = False
                if hasattr(e, "orig_exc"):
                    toe = type(e.orig_exc)
                    logger.verbose(f"\nexception type: {toe}")  # noqa: F821
                    if e != e.orig_exc:
                        logger.verbose("\noriginal msg: %s" % e.orig_exc)  # noqa: F821
            else:
                print("to see the full traceback")
                log_only = True
            msg = "the full traceback was:\n\n%s" % traceback.format_exc()
            logger.error(msg)
            if not log_only:
                print(msg)
            exit_code = 250

        sys.exit(exit_code)
