from xeet.xprint import pr_err, pr_warn, pr_info, pr_verbose
import logging
import datetime
import inspect
from os.path import basename
from typing import Callable


__logger = None

INFO = logging.INFO
WARN = logging.WARN
ERROR = logging.ERROR
VERBOSE = logging.DEBUG


def _frame_str(extra_frames: int = 0) -> str:
    frame = inspect.stack()[4 + extra_frames]
    return f"[{basename(frame.filename)}:{frame.lineno}] {frame.function}".ljust(38, '.')


class _XeetLogging(object):
    def __init__(self, log_file: str, log_level: int) -> None:
        self._logger = logging.getLogger()
        self._raw_formatter = logging.Formatter('%(message)s')
        self._default_formatter = logging.Formatter('%(levelname).1s %(message)s')
        self._file_handler = logging.FileHandler(log_file, encoding='utf-8')
        self._file_handler.setFormatter(self._default_formatter)
        self._file_handler.setLevel(log_level)
        self._logger.addHandler(self._file_handler)
        self._logger.setLevel(log_level)
        self.raw_format = False

    def set_raw_format(self) -> None:
        self.raw_format = True
        self._file_handler.setFormatter(self._raw_formatter)

    def set_default_format(self) -> None:
        self.raw_format = False
        self._file_handler.setFormatter(self._default_formatter)

    def is_enabled_for(self, level: int) -> bool:
        return self._logger.isEnabledFor(level)

    def log(self, verbosity, msg, extra_frames: int = 0) -> None:
        if not self.raw_format:
            frame_str = _frame_str(extra_frames=extra_frames)
        else:
            frame_str = ""
        self._logger.log(verbosity, frame_str + msg)


def start_raw_logging() -> None:
    if __logger is None:
        return
    __logger.set_raw_format()


def stop_raw_logging() -> None:
    if __logger is None:
        return
    __logger.set_default_format()


def log_blank(count=1) -> None:
    if __logger is None:
        return
    __logger.set_raw_format()
    for _ in range(0, count):
        __logger.log(logging.INFO, "")
    __logger.set_default_format()


def init_logging(log_file: str, logfile_verbosity: int) -> None:
    global __logger
    assert __logger is None
    if not log_file:
        return
    __logger = _XeetLogging(log_file, logging.INFO if logfile_verbosity == 0 else logging.DEBUG)
    log_blank(2)
    __logger.set_raw_format()
    log_info("======================================================================")
    log_info("Xeet: {}".format(datetime.datetime.now().strftime("%I:%M:%S on %B %d, %Y")))
    log_info("======================================================================")
    __logger.set_default_format()


def logging_enabled_for(level: int) -> bool:
    if not __logger:
        return False
    return __logger.is_enabled_for(level)


def gen_log_func(verbosity: int, pr_func: Callable) -> Callable:
    def _log_func(*args, **kwargs) -> None:
        if kwargs.pop('pr', False):
            pr_func(*args, **kwargs)
        if __logger is None:
            return
        extra_frames = kwargs.pop('extra_frames', 0)
        msg = " ".join([str(x) for x in args])
        __logger.log(verbosity, msg, extra_frames=extra_frames)
    return _log_func


log_verbose = gen_log_func(logging.DEBUG, pr_verbose)
log_info = gen_log_func(logging.INFO, pr_info)
log_warn = gen_log_func(logging.WARN, pr_warn)
log_error = gen_log_func(logging.ERROR, pr_err)


def log_raw(*args, **kwargs) -> None:
    if __logger is None:
        return
    __logger.set_raw_format()
    log_info(*args, **kwargs)
    __logger.set_default_format()
