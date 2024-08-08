#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

from ..note_reviewer import NoteReviewer
from . import CLI
from .arguments import option_helpers as oh


class ReviewCLI(CLI):
    """Review Notes using spaced repetition"""

    name = "srn-review"

    def __init__(self, args, callback=None):
        super(ReviewCLI, self).__init__(args, callback)

    def init_parser(self):
        super(ReviewCLI, self).init_parser(
            usage="usage: %prog [options]",
            desc=ReviewCLI.__doc__,
        )
        # notes path
        oh.add_notes_path(self.parser)
        # review log file
        oh.add_review_log_file(self.parser)

    def post_process_args(self, options):
        options = super(ReviewCLI, self).post_process_args(options)
        return options

    def run(self):
        super(ReviewCLI, self).run()

        showing_args = {
            k: v
            for k, v in self.cli_args.items()
            if k in ["notes_path", "review_log_file"]
        }
        print(f"Review Note\n args: {showing_args}")
        reviewer = NoteReviewer(
            self.cli_args["notes_path"], self.cli_args["review_log_file"]
        )
        reviewer.review_notes()


def main(args=None):
    ReviewCLI.cli_executor(args)


if __name__ == "__main__":
    main()
