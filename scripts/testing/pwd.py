import os
from pathlib import PureWindowsPath


def in_windows() -> bool:
    return os.name == "nt"


cwd = os.getcwd()
if in_windows():
    cwd = PureWindowsPath(cwd).as_posix()


print(cwd)
