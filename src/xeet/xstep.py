from xeet.common import XeetVars, XeetException, KeysBaseModel
from xeet import XeetDefs
from xeet.log import log_info, log_warn, log_error, log_raw
from xeet.pr import pr_info, pr_warn, pr_error
from pydantic import ConfigDict, Field
from dataclasses import dataclass
from timeit import default_timer as timer
import sys


class XStepModel(KeysBaseModel):
    model_config = ConfigDict(extra='forbid')
    base: str = ""
    step_type: str = Field("", validation_alias="type")
    name: str = ""

    def inherit(self, _: "XStepModel") -> None:
        ...


class XeetStepException(XeetException):
    ...


class XeetStepInitException(XeetStepException):
    ...


@dataclass
class XStepResult:
    err_summary: str = ""
    completed: bool = False
    duration: float | None = None
    failed: bool = False

    def error_summary(self) -> str:
        if not self.completed:
            return f" incomplete: {self.err_summary}"
        if self.failed:
            return f" failed: {self.err_summary}"
        return ""


class XStep:
    @staticmethod
    def model_class() -> type[XStepModel]:
        return XStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return XStepResult

    def __init__(self, model: XStepModel, xdefs: XeetDefs, base_name: str) -> None:
        self.model = model
        self.xdefs = xdefs
        self.base_name = base_name

    def setup(self, _: XeetVars) -> str:
        ...

    def log_info(self, msg, *args, **kwargs) -> None:
        if self.debug_mode and kwargs.pop("dbg_pr", True):
            kwargs.pop("pr", None)  # Prevent double printing
            pr_info(msg, *args, **kwargs)
        log_info(f"{self.base_name}: {msg}", *args, depth=1, **kwargs)

    def log_warn(self, msg, *args, **kwargs) -> None:
        if self.debug_mode:
            pr_warn(msg, *args, **kwargs, pr_file=sys.stdout)
        log_warn(f"{self.base_name}: {msg}", *args, depth=1, pr=None,  **kwargs)

    def log_error(self, msg, *args, **kwargs) -> None:
        if self.debug_mode:
            pr_error(msg, *args, **kwargs, pr_file=sys.stdout)
        log_error(f"{self.base_name}: {msg}", *args, depth=1, pr=None, **kwargs)

    def log_raw(self, msg, *args, **kwargs) -> None:
        log_raw(msg, *args, pr=self.debug_mode, **kwargs)

    def pr_debug(self, msg, *args, **kwargs) -> None:
        if self.debug_mode:
            pr_info(msg, *args, **kwargs)

    def run(self) -> XStepResult:
        res = self.result_class()()
        start = timer()
        res.completed = self._run(res)
        res.duration = timer() - start
        self.log_info(f"step finished with in {res.duration:.3f}s", dbg_pr=False)
        return res

    def print_name(self) -> str:
        if self.model.name:
            return f"{self.model.step_type} ('{self.model.name}')"
        return self.model.step_type

    def summary(self) -> str:
        return self.print_name()

    @property
    def debug_mode(self) -> bool:
        return self.xdefs.debug_mode

    def _run(self, _: XStepResult) -> bool:
        raise NotImplementedError
