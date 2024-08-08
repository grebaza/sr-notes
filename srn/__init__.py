from .utils import _log

# init_logging() must be called before any call to logging.getLogger()
# # which happens at import of most modules.
_log.init_logging()

# Backwards compatibility code. Code should use `.release`.
from .release import __codename__, __version__  # noqa: F401,E402
