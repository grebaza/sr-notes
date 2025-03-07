import logging
import click

from . import constants as C
from .note_reviewer import NoteReviewer

logger = logging.getLogger(__name__)


@click.group()
def cli():
    pass


@cli.command()
@click.argument(
    "notes-path",
    default=C.NOTES_PATH,
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
)
@click.option(
    "--review-file",
    "-f",
    default=C.REVIEW_LOG_FILE,
    type=click.Path(exists=False, file_okay=True, dir_okay=False),
)
def review(notes_path: str, review_file: str):
    """
    Rewiew Notes with Spaced Repetition Algorithm.
    """
    print(f"Spaced Repetition Review\nArgs: {notes_path=}, {review_file=}")
    reviewer = NoteReviewer(notes_path, review_file)
    reviewer.review()


if __name__ == "__main__":
    cli()
