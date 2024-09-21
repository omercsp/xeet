try:
    from ._version import version
    xeet_version = version
except ImportError:
    xeet_version = "0.0.0"
