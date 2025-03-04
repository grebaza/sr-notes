import os
import sys
import json
import subprocess
import typing as t

from schema import Use, And, SchemaError
from datetime import datetime
from pathlib import Path
from fsrs import FSRS, Card, ReviewLog
from .picker import pick
import logging

logger = logging.getLogger(__name__)


difficulty_schema = And(Use(int), lambda n: 1 <= n <= 4)


def editor(path):
    app = os.environ.get("EDITOR")
    if app:
        subprocess.run([app, str(path)])


class NoteReviewer:
    REVIEW_FILE = "review_log.json"
    REVIEW_LOG_KEY = "review_log"
    REVIEW_STATE_KEY = "card"

    def __init__(self, root: str, review_file: t.Optional[str]):
        self.root = Path(root).expanduser()
        self.review_file = (
            Path(review_file).expanduser()
            if review_file
            else self.root / NoteReviewer.REVIEW_FILE
        )

        # Load review log
        self.review_data = {}
        try:
            with open(self.review_file, "r") as f:
                self.review_data = json.load(f)
        except Exception:
            logger.error("Could not load review json file")

        self.fsrs = FSRS()

    def get_due_list(self, q=None):
        """
        Get due notes from root dir.

        Due time comes from review file for each file in `self.root` dir. It
        includes non-reviewed files.
        """
        notes = list(self.root.rglob("*.md"))
        ids = [str(f) for f in notes]  # note's id is its full path
        due = []

        for k, _id in enumerate(ids):
            if _id in self.review_data:
                reviewed_note = self.review_data[_id]
                state = Card.from_dict(reviewed_note[NoteReviewer.REVIEW_STATE_KEY])
                if state.due.timestamp() <= datetime.now().timestamp():
                    due.append(notes[k])
            else:
                due.append(notes[k])

        return due[:q] if q else due

    def update(self, note_id, rating):
        if note_id in self.review_data:
            reviewed_note = self.review_data[note_id]
            state = Card.from_dict(reviewed_note[NoteReviewer.REVIEW_STATE_KEY])
            log = ReviewLog.from_dict(reviewed_note[NoteReviewer.REVIEW_LOG_KEY])
        else:
            state = Card()

        # Update the review state and log
        state, log = self.fsrs.review_card(state, rating)
        self.review_data[note_id] = {
            NoteReviewer.REVIEW_STATE_KEY: state.to_dict(),
            NoteReviewer.REVIEW_LOG_KEY: log.to_dict(),
        }

    def save_review(self):
        with open(self.review_file, "w") as f:
            json.dump(self.review_data, f, indent=2)

    def review(self):
        """
        Rewiew due notes.
        """
        notes = self.get_due_list()

        # Open a selection dialog using a gui picker
        names = [str(f.relative_to(self.root)) for f in notes]
        _, index, selected = pick(
            names, picker_args=["-normal-window"], prompt="Select Note"
        )
        if selected:
            path = notes[index]
            note_id = str(notes[index])
            editor(path)
            print(f"Reviewed: {names[index]}")

            # get rating
            difficulty = None
            while True:
                returncode, _, answer = pick(
                    [],
                    ["-normal-window"],
                    prompt="Enter Recall Difficulty (1:easy - 4:hard)",
                )
                if returncode == 0:
                    try:
                        difficulty = difficulty_schema.validate(int(answer))
                    except SchemaError:
                        print(
                            "> Error! difficulty should be between 1 and 4. Please retry.",
                            file=sys.stderr,
                        )
                        continue
                    break
                else:
                    break

            if difficulty:
                print(f"Recall difficulty: {difficulty}")
                self.update(note_id, 5 - difficulty)
                self.save_review()
                print(f"Updated review file: {str(self.review_file)}")
