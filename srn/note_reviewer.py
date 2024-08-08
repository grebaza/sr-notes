import os
import sys
import json
import datetime
import typing as t

from schema import Use, And, SchemaError
from fsrs import FSRS, Card, ReviewLog
import logging

logger = logging.getLogger(__name__)


difficulty_schema = And(Use(int), lambda n: 1 <= n <= 4)


class NoteReviewer:
    def __init__(self, notes_path: str, review_log_file: t.Optional[str]):
        self.notes_path = os.path.expanduser(notes_path)
        if review_log_file is None:
            self.review_log_file = os.path.join(self.notes_path, "review_log.json")
        else:
            self.review_log_file = os.path.expanduser(review_log_file)
        self.fsrs = FSRS()

        # Load review log
        if os.path.exists(self.review_log_file):
            with open(self.review_log_file, "r") as f:
                self.review_log = json.load(f)
        else:
            self.review_log = {}

    def select_notes_for_review(self, q: int = 5):
        notes = [
            os.path.join(root, file)
            for root, _, files in os.walk(self.notes_path)
            for file in files
            if file.endswith(".md")
        ]

        notes_due = []
        for note in notes:
            if note in self.review_log:
                card_data = self.review_log[note]
                card = Card.from_dict(card_data["card"])
                if card.due.timestamp() <= datetime.datetime.now().timestamp():
                    notes_due.append(note)
            else:
                notes_due.append(note)  # New notes to be reviewed

        return notes_due[:q]

    def update_review_log(self, note, rating):
        today = datetime.date.today().strftime("%Y-%m-%d")
        if note in self.review_log:
            card_data = self.review_log[note]
            card = Card.from_dict(card_data["card"])
            review_log = ReviewLog.from_dict(card_data["review_log"])
        else:
            card = Card()

        # Update the card and review log using the review_card method with the given rating
        card, review_log = self.fsrs.review_card(card, rating)

        self.review_log[note] = {
            "last_reviewed": today,
            "card": card.to_dict(),
            "review_log": review_log.to_dict(),
        }

    def save_review_log(self):
        with open(self.review_log_file, "w") as f:
            json.dump(self.review_log, f, indent=4)

    def review_notes(self):
        notes_for_review = self.select_notes_for_review()
        finish_review = False
        for note in notes_for_review:
            while True:
                try:
                    print(f"\nReview: {note}")
                    input("Press Enter when done reviewing...")
                    answer = input(
                        "How difficult was it to review this note? (1-4). Press q to quit: "
                    )
                    if answer == "q":
                        finish_review = True
                        break
                    difficulty = difficulty_schema.validate(int(answer))
                except SchemaError:
                    print(
                        "> Error! difficulty should be between 1 and 4. Please retry.",
                        file=sys.stderr,
                    )
                    # autos_to_show = [a for a in reversed(se.autos) if a][0:2]
                    # print("\n".join(autos_to_show), file=sys.stderr)
                    continue
                break

            if finish_review:
                return
            else:
                rating = 5 - difficulty
                self.update_review_log(note, rating)
                self.save_review_log()
