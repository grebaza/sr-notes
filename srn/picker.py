"""
Call a command line fuzzy matcher to select a figure to edit.

Current supported matchers are:

* rofi for Linux platforms
* choose (https://github.com/chipsenkbeil/choose) on MacOS
"""

import os
import subprocess
import platform

SYSTEM_NAME = platform.system()


def is_wayland():
    """Return True if the current session is using Wayland."""
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY")
    )


def get_picker_cmd(picker_args=None, fuzzy=True, prompt="Input"):
    """
    Create the shell command that will be run to start the picker.
    """

    if SYSTEM_NAME == "Linux":
        args = ["rofi", "-sort", "-no-levenshtein-sort"]
        if fuzzy:
            args += ["-matching", "fuzzy"]
        args += ["-dmenu", "-p", prompt, "-format", "s", "-i", "-lines", "5"]
        if is_wayland():
            args += ["-normal-window"]
    elif SYSTEM_NAME == "Darwin":
        args = ["choose"]
    else:
        raise ValueError("No supported picker for {}".format(SYSTEM_NAME))

    if picker_args is not None:
        args += picker_args

    return [str(arg) for arg in args]


def pick(options, picker_args=None, fuzzy=True, prompt="Input"):
    optionstr = "\n".join(option.replace("\n", " ") for option in options)
    cmd = get_picker_cmd(picker_args=picker_args, fuzzy=fuzzy, prompt=prompt)
    result = subprocess.run(
        cmd, input=optionstr, stdout=subprocess.PIPE, universal_newlines=True
    )
    returncode = result.returncode
    stdout = result.stdout.strip()

    selected = stdout.strip()
    try:
        index = [opt.strip() for opt in options].index(selected)
    except ValueError:
        index = -1

    if returncode == 0:
        key = 0
    elif returncode == 1:
        key = -1
    elif returncode > 9:
        key = returncode - 9

    return key, index, selected
