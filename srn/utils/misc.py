import contextlib
import errno
import getpass
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import urllib.parse
from functools import partial
from io import StringIO
from itertools import filterfalse, tee, zip_longest
from pathlib import Path
from types import FunctionType, TracebackType
from typing import (
    Any,
    BinaryIO,
    Callable,
    ContextManager,
    Generator,
    Iterable,
    Iterator,
    List,
    Optional,
    TextIO,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from tenacity import retry, stop_after_delay, wait_fixed

from ..exceptions import AppError, ConfigurationError
from .virtualenv import running_under_virtualenv

__all__ = [
    "rmtree",
    "display_path",
    "backup_dir",
    "ask",
    "format_size",
    "normalize_path",
    "renames",
    "captured_stdout",
    "ensure_dir",
    "remove_auth_from_url",
]


T = TypeVar("T")
ExcInfo = Tuple[Type[BaseException], BaseException, TracebackType]
VersionInfo = Tuple[int, int, int]
NetlocTuple = Tuple[str, Tuple[Optional[str], Optional[str]]]
OnExc = Callable[[FunctionType, Path, BaseException], Any]
OnErr = Callable[[FunctionType, Path, ExcInfo], Any]


def _try_json_readkey(
    key: str, filepath: Optional[str] = None, content: Optional[str] = None
):
    try:
        if filepath is None and content:
            _json = json.loads(content)
        elif filepath:
            with open(filepath, "r") as f:
                _json = json.load(f)
        return _json.get(key)
    except Exception:  # pylint: disable=broad-except
        return None


def _try_json_readversion(
    filepath: Optional[str] = None, content: Optional[str] = None
) -> Optional[str]:
    return _try_json_readkey(
        "version",
        filepath,
        content,
    )


def _try_json_readsha(
    length: int, filepath: Optional[str] = None, content: Optional[str] = None
) -> Optional[str]:
    return _try_json_readkey(
        "GIT_SHA",
        filepath,
        content,
    )


def normalize_version_info(py_version_info: Tuple[int, ...]) -> Tuple[int, int, int]:
    """
    Convert a tuple of ints representing a Python version to one of length
    three.

    :param py_version_info: a tuple of ints representing a Python version,
        or None to specify no version. The tuple can have any length.

    :return: a tuple of length three if `py_version_info` is non-None.
        Otherwise, return `py_version_info` unchanged (i.e. None).
    """
    if len(py_version_info) < 3:
        py_version_info += (3 - len(py_version_info)) * (0,)
    elif len(py_version_info) > 3:
        py_version_info = py_version_info[:3]

    return cast("VersionInfo", py_version_info)


def ensure_dir(path: str) -> None:
    """os.path.makedirs without EEXIST."""
    try:
        os.makedirs(path)
    except OSError as e:
        # Windows can raise spurious ENOTEMPTY errors. See #6426.
        if e.errno != errno.EEXIST and e.errno != errno.ENOTEMPTY:
            raise


# Retry every half second for up to 3 seconds
# Tenacity raises RetryError by default, explicitly raise the original exception
@retry(reraise=True, stop=stop_after_delay(3), wait=wait_fixed(0.5))
def rmtree(
    dir: str,
    ignore_errors: bool = False,
    onexc: Optional[OnExc] = None,
) -> None:
    if ignore_errors:
        onexc = _onerror_ignore
    if onexc is None:
        onexc = _onerror_reraise
    handler: OnErr = partial(
        # `[func, path, Union[ExcInfo, BaseException]] -> Any` is equivalent to
        # `Union[([func, path, ExcInfo] -> Any), ([func, path, BaseException] -> Any)]`.
        cast(Union[OnExc, OnErr], rmtree_errorhandler),
        onexc=onexc,
    )
    if sys.version_info >= (3, 12):
        # See https://docs.python.org/3.12/whatsnew/3.12.html#shutil.
        shutil.rmtree(dir, onexc=handler)  # type: ignore
    else:
        shutil.rmtree(dir, onerror=handler)  # type: ignore


def _onerror_ignore(*_args: Any) -> None:
    pass


def _onerror_reraise(*_args: Any) -> None:
    raise


def rmtree_errorhandler(
    func: FunctionType,
    path: Path,
    exc_info: Union[ExcInfo, BaseException],
    *,
    onexc: OnExc = _onerror_reraise,
) -> None:
    """
    `rmtree` error handler to 'force' a file remove (i.e. like `rm -f`).

    * If a file is readonly then it's write flag is set and operation is
      retried.

    * `onerror` is the original callback from `rmtree(... onerror=onerror)`
      that is chained at the end if the "rm -f" still fails.
    """
    try:
        st_mode = os.stat(path).st_mode
    except OSError:
        # it's equivalent to os.path.exists
        return

    if not st_mode & stat.S_IWRITE:
        # convert to read/write
        try:
            os.chmod(path, st_mode | stat.S_IWRITE)
        except OSError:
            pass
        else:
            # use the original function to repeat the operation
            try:
                func(path)
                return
            except OSError:
                pass

    if not isinstance(exc_info, BaseException):
        _, exc_info, _ = exc_info
    onexc(func, path, exc_info)


def display_path(path: str) -> str:
    """Gives the display value for a given path, making it relative to cwd
    if possible."""
    path = os.path.normcase(os.path.abspath(path))
    if path.startswith(os.getcwd() + os.path.sep):
        path = "." + path[len(os.getcwd()) :]
    return path


def backup_dir(dir: str, ext: str = ".bak") -> str:
    """Figure out the name of a directory to back up the given dir to
    (adding .bak, .bak2, etc)"""
    n = 1
    extension = ext
    while os.path.exists(dir + extension):
        n += 1
        extension = ext + str(n)
    return dir + extension


def ask_path_exists(message: str, options: Iterable[str]) -> str:
    for action in os.environ.get("PIP_EXISTS_ACTION", "").split():
        if action in options:
            return action
    return ask(message, options)


def _check_no_input(message: str) -> None:
    """Raise an error if no input is allowed."""
    if os.environ.get("PIP_NO_INPUT"):
        raise Exception(
            f"No input was expected ($PIP_NO_INPUT set); question: {message}"
        )


def ask(message: str, options: Iterable[str]) -> str:
    """Ask the message interactively, with the given possible responses"""
    while 1:
        _check_no_input(message)
        response = input(message)
        response = response.strip().lower()
        if response not in options:
            print(
                "Your response ({!r}) was not one of the expected responses: "
                "{}".format(response, ", ".join(options))
            )
        else:
            return response


def ask_input(message: str) -> str:
    """Ask for input interactively."""
    _check_no_input(message)
    return input(message)


def ask_password(message: str) -> str:
    """Ask for a password interactively."""
    _check_no_input(message)
    return getpass.getpass(message)


def strtobool(val: str) -> int:
    """Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError(f"invalid truth value {val!r}")


def format_size(bytes: float) -> str:
    if bytes > 1000 * 1000:
        return f"{bytes / 1000.0 / 1000:.1f} MB"
    elif bytes > 10 * 1000:
        return f"{int(bytes / 1000)} kB"
    elif bytes > 1000:
        return f"{bytes / 1000.0:.1f} kB"
    else:
        return f"{int(bytes)} bytes"


def tabulate(rows: Iterable[Iterable[Any]]) -> Tuple[List[str], List[int]]:
    """Return a list of formatted rows and a list of column sizes.

    For example::

    >>> tabulate([['foobar', 2000], [0xdeadbeef]])
    (['foobar     2000', '3735928559'], [10, 4])
    """
    rows = [tuple(map(str, row)) for row in rows]
    sizes = [max(map(len, col)) for col in zip_longest(*rows, fillvalue="")]
    table = [" ".join(map(str.ljust, row, sizes)).rstrip() for row in rows]
    return table, sizes


def read_chunks(
    file: BinaryIO, size: int = io.DEFAULT_BUFFER_SIZE
) -> Generator[bytes, None, None]:
    """Yield pieces of data from a file-like object until EOF."""
    while True:
        chunk = file.read(size)
        if not chunk:
            break
        yield chunk


def normalize_path(path: str, resolve_symlinks: bool = True) -> str:
    """
    Convert a path to its canonical, case-normalized, absolute version.

    """
    path = os.path.expanduser(path)
    if resolve_symlinks:
        path = os.path.realpath(path)
    else:
        path = os.path.abspath(path)
    return os.path.normcase(path)


def renames(old: str, new: str) -> None:
    """Like os.renames(), but handles renaming across devices."""
    # Implementation borrowed from os.renames().
    head, tail = os.path.split(new)
    if head and tail and not os.path.exists(head):
        os.makedirs(head)

    shutil.move(old, new)

    head, tail = os.path.split(old)
    if head and tail:
        try:
            os.removedirs(head)
        except OSError:
            pass


def is_local(path: str) -> bool:
    """
    Return True if path is within sys.prefix, if we're running in a virtualenv.

    If we're not in a virtualenv, all paths are considered "local."

    Caution: this function assumes the head of path has been normalized
    with normalize_path.
    """
    if not running_under_virtualenv():
        return True
    return path.startswith(normalize_path(sys.prefix))


class StreamWrapper(StringIO):
    orig_stream: TextIO

    @classmethod
    def from_stream(cls, orig_stream: TextIO) -> "StreamWrapper":
        ret = cls()
        ret.orig_stream = orig_stream
        return ret

    # compileall.compile_dir() needs stdout.encoding to print to stdout
    # type ignore is because TextIOBase.encoding is writeable
    @property
    def encoding(self) -> str:  # type: ignore
        return self.orig_stream.encoding


@contextlib.contextmanager
def captured_output(stream_name: str) -> Generator[StreamWrapper, None, None]:
    """Return a context manager used by captured_stdout/stdin/stderr
    that temporarily replaces the sys stream *stream_name* with a StringIO.

    Taken from Lib/support/__init__.py in the CPython repo.
    """
    orig_stdout = getattr(sys, stream_name)
    setattr(sys, stream_name, StreamWrapper.from_stream(orig_stdout))
    try:
        yield getattr(sys, stream_name)
    finally:
        setattr(sys, stream_name, orig_stdout)


def captured_stdout() -> ContextManager[StreamWrapper]:
    """Capture the output of sys.stdout:

       with captured_stdout() as stdout:
           print('hello')
       self.assertEqual(stdout.getvalue(), 'hello\n')

    Taken from Lib/support/__init__.py in the CPython repo.
    """
    return captured_output("stdout")


def captured_stderr() -> ContextManager[StreamWrapper]:
    """
    See captured_stdout().
    """
    return captured_output("stderr")


# Simulates an enum
def enum(*sequential: Any, **named: Any) -> Type[Any]:
    enums = dict(zip(sequential, range(len(sequential))), **named)
    reverse = {value: key for key, value in enums.items()}
    enums["reverse_mapping"] = reverse
    return type("Enum", (), enums)


def build_netloc(host: str, port: Optional[int]) -> str:
    """
    Build a netloc from a host-port pair
    """
    if port is None:
        return host
    if ":" in host:
        # Only wrap host with square brackets when it is IPv6
        host = f"[{host}]"
    return f"{host}:{port}"


def build_url_from_netloc(netloc: str, scheme: str = "https") -> str:
    """
    Build a full URL from a netloc.
    """
    if netloc.count(":") >= 2 and "@" not in netloc and "[" not in netloc:
        # It must be a bare IPv6 address, so wrap it with brackets.
        netloc = f"[{netloc}]"
    return f"{scheme}://{netloc}"


def parse_netloc(netloc: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Return the host-port pair from a netloc.
    """
    url = build_url_from_netloc(netloc)
    parsed = urllib.parse.urlparse(url)
    return parsed.hostname, parsed.port


def split_auth_from_netloc(netloc: str) -> NetlocTuple:
    """
    Parse out and remove the auth information from a netloc.

    Returns: (netloc, (username, password)).
    """
    if "@" not in netloc:
        return netloc, (None, None)

    # Split from the right because that's how urllib.parse.urlsplit()
    # behaves if more than one @ is present (which can be checked using
    # the password attribute of urlsplit()'s return value).
    auth, netloc = netloc.rsplit("@", 1)
    pw: Optional[str] = None
    if ":" in auth:
        # Split from the left because that's how urllib.parse.urlsplit()
        # behaves if more than one : is present (which again can be checked
        # using the password attribute of the return value)
        user, pw = auth.split(":", 1)
    else:
        user, pw = auth, None

    user = urllib.parse.unquote(user)
    if pw is not None:
        pw = urllib.parse.unquote(pw)

    return netloc, (user, pw)


def redact_netloc(netloc: str) -> str:
    """
    Replace the sensitive data in a netloc with "****", if it exists.

    For example:
        - "user:pass@example.com" returns "user:****@example.com"
        - "accesstoken@example.com" returns "****@example.com"
    """
    netloc, (user, password) = split_auth_from_netloc(netloc)
    if user is None:
        return netloc
    if password is None:
        user = "****"
        password = ""
    else:
        user = urllib.parse.quote(user)
        password = ":****"
    return f"{user}{password}@{netloc}"


def _transform_url(
    url: str, transform_netloc: Callable[[str], Tuple[Any, ...]]
) -> Tuple[str, NetlocTuple]:
    """Transform and replace netloc in a url.

    transform_netloc is a function taking the netloc and returning a
    tuple. The first element of this tuple is the new netloc. The
    entire tuple is returned.

    Returns a tuple containing the transformed url as item 0 and the
    original tuple returned by transform_netloc as item 1.
    """
    purl = urllib.parse.urlsplit(url)
    netloc_tuple = transform_netloc(purl.netloc)
    # stripped url
    url_pieces = (purl.scheme, netloc_tuple[0], purl.path, purl.query, purl.fragment)
    surl = urllib.parse.urlunsplit(url_pieces)
    return surl, cast("NetlocTuple", netloc_tuple)


def _get_netloc(netloc: str) -> NetlocTuple:
    return split_auth_from_netloc(netloc)


def _redact_netloc(netloc: str) -> Tuple[str]:
    return (redact_netloc(netloc),)


def split_auth_netloc_from_url(
    url: str,
) -> Tuple[str, str, Tuple[Optional[str], Optional[str]]]:
    """
    Parse a url into separate netloc, auth, and url with no auth.

    Returns: (url_without_auth, netloc, (username, password))
    """
    url_without_auth, (netloc, auth) = _transform_url(url, _get_netloc)
    return url_without_auth, netloc, auth


def remove_auth_from_url(url: str) -> str:
    """Return a copy of url with 'username:password@' removed."""
    # username/pass params are passed to subversion through flags
    # and are not recognized in the url.
    return _transform_url(url, _get_netloc)[0]


def redact_auth_from_url(url: str) -> str:
    """Replace the password in a given url with ****."""
    return _transform_url(url, _redact_netloc)[0]


class HiddenText:
    def __init__(self, secret: str, redacted: str) -> None:
        self.secret = secret
        self.redacted = redacted

    def __repr__(self) -> str:
        return f"<HiddenText {str(self)!r}>"

    def __str__(self) -> str:
        return self.redacted

    # This is useful for testing.
    def __eq__(self, other: Any) -> bool:
        if type(self) != type(other):
            return False

        # The string being used for redaction doesn't also have to match,
        # just the raw, original string.
        return self.secret == other.secret


def hide_value(value: str) -> HiddenText:
    return HiddenText(value, redacted="****")


def hide_url(url: str) -> HiddenText:
    redacted = redact_auth_from_url(url)
    return HiddenText(url, redacted=redacted)


def is_console_interactive() -> bool:
    """Is this console interactive?"""
    return sys.stdin is not None and sys.stdin.isatty()


def hash_file(path: str, blocksize: int = 1 << 20) -> Tuple[Any, int]:
    """Return (hash, length) for path using hashlib.sha256()"""

    h = hashlib.sha256()
    length = 0
    with open(path, "rb") as f:
        for block in read_chunks(f, size=blocksize):
            length += len(block)
            h.update(block)
    return h, length


def pairwise(iterable: Iterable[Any]) -> Iterator[Tuple[Any, Any]]:
    """
    Return paired elements.

    For example:
        s -> (s0, s1), (s2, s3), (s4, s5), ...
    """
    iterable = iter(iterable)
    return zip_longest(iterable, iterable)


def partition(
    pred: Callable[[T], bool],
    iterable: Iterable[T],
) -> Tuple[Iterable[T], Iterable[T]]:
    """
    Use a predicate to partition entries into false entries and true entries,
    like

        partition(is_odd, range(10)) --> 0 2 4 6 8   and  1 3 5 7 9
    """
    t1, t2 = tee(iterable)
    return filterfalse(pred, t1), filter(pred, t2)


# FIXME: generic file type?
def get_config_type(cfile) -> str | None:
    ftype = None
    if cfile is not None:
        ext = os.path.splitext(cfile)[-1]
        if ext in (".ini", ".cfg"):
            ftype = "ini"
        elif ext in (".yaml", ".yml"):
            ftype = "yaml"
        else:
            raise AppError(
                f"Unsupported configuration file extension for {cfile}: {ext}"
            )

    return ftype


def get_ini_config_value(p, entry):
    """returns the value of last ini entry found"""
    value = None
    if p is not None:
        try:
            value = p.get(
                entry.get("section", "defaults"), entry.get("key", ""), raw=True
            )
        except Exception as e:
            raise ConfigurationError("can't get ini entry", orig_exc=e)
    return value


####################
#  path functions  #
####################
def resolve_path(path: str, basedir=None):
    """resolve relative or 'variable' paths"""
    if "{{CWD}}" in path:  # allow users to force CWD using 'magic' {{CWD}}
        path = path.replace("{{CWD}}", os.getcwd())

    return unfrackpath(path, follow=False, basedir=basedir)


def unfrackpath(path, follow=True, basedir=None):
    """
    Returns a path that is free of symlinks (if follow=True), environment
    variables, relative path traversals and symbols (~)

    Parameters:
        :arg path: A byte or text string representing a path to be canonicalized
        :arg follow: A boolean to indicate of symlinks should be resolved or not
    :raises UnicodeDecodeError: If the canonicalized version of the path
        contains non-utf8 byte sequences.
    :rtype: A text string (unicode on pyyhon2, str on python3).
    :returns: An absolute path with symlinks, environment variables, and tilde
        expanded.  Note that this does not check whether a path exists.

    example::
        '$HOME/../../var/mail' becomes '/var/spool/mail'
    """
    # from [Ansible](https://github.com/ansible/ansible/blob/v2.16.3/lib/ansible/utils/path.py)

    if basedir is None:
        basedir = os.getcwd()
    elif os.path.isfile(basedir):
        basedir = os.path.dirname(basedir)

    b_final_path = os.path.expanduser(os.path.expandvars(path))

    if not os.path.isabs(b_final_path):
        b_final_path = os.path.join(basedir, b_final_path)

    if follow:
        b_final_path = os.path.realpath(b_final_path)

    return os.path.normpath(b_final_path)


def makedirs_safe(path, mode=None):
    """
    A *potentially insecure* way to ensure the existence of a directory chain.
    The "safe" in this function's name refers only to its ability to ignore
    `EEXIST` in the case of multiple callers operating on the same part of the
    directory chain. This function is not safe to use under world-writable
    locations when the first level of the path to be created contains a
    predictable component. Always create a randomly-named element first if
    there is any chance the parent directory might be world-writable (eg, /tmp)
    to prevent symlink hijacking and potential disclosure or modification of
    sensitive file contents.

    :arg path: A byte or text string representing a directory chain to be created
    :kwarg mode: If given, the mode to set the directory to
    :raises AnsibleError: If the directory cannot be created and does not already exist.
    :raises UnicodeDecodeError: if the path is not decodable in the utf-8 encoding.
    """

    rpath = unfrackpath(path)
    b_rpath = bytes(rpath)
    if not os.path.exists(b_rpath):
        try:
            if mode:
                os.makedirs(b_rpath, mode)
            else:
                os.makedirs(b_rpath)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise AppError(
                    "Unable to create local directories(%s): %s" % (rpath, e)
                )


def cleanup_tmp_file(path, warn=False):
    """
    Removes temporary file or directory. Optionally display a warning if unable
    to remove the file or directory.

    :arg path: Path to file or directory to be removed
    :kwarg warn: Whether or not to display a warning when the file or directory
        cannot be removed
    """
    try:
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.isfile(path):
                    os.unlink(path)
            except Exception:
                pass
    except Exception:
        pass
