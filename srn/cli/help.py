#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

from . import CLI


class HelpCLI(CLI):
    """Show help for commands"""

    name = "srn-help"

    def __init__(self, args, callback=None):
        super(HelpCLI, self).__init__(args, callback)

    def init_parser(self):
        super(HelpCLI, self).init_parser(
            desc="View help.",
        )

    def post_process_args(self, options):
        options = super(HelpCLI, self).post_process_args(options)

        return options

    def run(self):
        super(HelpCLI, self).run()
        self.parser.print_help()


def main(args=None):
    HelpCLI.cli_executor(args)


if __name__ == "__main__":
    main()
