import logging

try:
    from ._version import version
    xeet_version = version
except ImportError:
    xeet_version = "0.0.0"


class LogLevel(object):
    NOTSET = logging.NOTSET
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARN = logging.WARN
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    ALWAYS = logging.CRITICAL + 1
