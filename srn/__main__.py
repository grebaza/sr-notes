import logging
import os
import sys

from .cli import cli

logger = logging.getLogger(__name__)


def main():
    cli()


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
