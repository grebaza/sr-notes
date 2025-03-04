from .release import __version__, __codename__
from .utils import _log as l

__all__ = ["__version__", "__codename__"]
l.init_logging()  # must be called before any logging.getLogger()
