import os


def ut_base_dir():
    return os.path.dirname(os.path.abspath(__file__))

_MOC_DIR = os.path.join(ut_base_dir(), "moc")

def moc_file(*tokens) -> str:
    return os.path.join(_MOC_DIR, *tokens)
    #  return os.path.join(ut_base_dir(), "moc", file_name)
