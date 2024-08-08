import argparse
import logging
import os
import sys
from importlib.metadata import distribution

from . import constants as C

logger = logging.getLogger(__name__)


def _short_name(name: str):
    app_name = f"{C.APP_NAME.lower()}"
    return name.removeprefix(f"{app_name}-").replace(f"{app_name}", "help")


def main():
    dist = distribution(C.APP_NAME)
    ep_map = {
        _short_name(ep.name): ep
        for ep in dist.entry_points
        if ep.group == "console_scripts"
    }

    parser = argparse.ArgumentParser(
        prog=f"python -m {C.APP_NAME.lower()}", add_help=False
    )
    parser.add_argument("entry_point", choices=list(ep_map))
    args, extra = parser.parse_known_args()

    _main = ep_map[args.entry_point].load()

    _main([args.entry_point] + extra)


# If we are running from a wheel, add the wheel to sys.path
# This allows the usage python pip-*.whl/pip install pip-*.whl
if __package__ == "":
    # __file__ is *.whl/app/__main__.py
    # first dirname call strips of '/__main__.py', second strips off '/app'
    # Resulting path is the name of the wheel itself
    # Add that to sys.path so we can import pip
    path = os.path.dirname(os.path.dirname(__file__))
    sys.path.insert(0, path)

if __name__ == "__main__":
    main()
