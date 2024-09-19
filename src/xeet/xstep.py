from xeet.common import XeetVars, XeetException
from xeet import XeetDefs
from pydantic import BaseModel, ConfigDict, Field
from dataclasses import dataclass, field
from timeit import default_timer as timer
from typing import Callable


class XStepModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base: str = ""
    step_type: str = Field("", validation_alias="type")
    name: str = ""
    field_keys: set[str] = Field(default_factory=set, exclude=True)

    def inherit(self, _: "XStepModel") -> None:
        ...

    def _keys(self) -> set[str]:
        if not self.field_keys:
            self.field_keys = set(self.model_dump(exclude_unset=True).keys())
        return self.field_keys

    def _had_key(self, key: str) -> bool:
        return key in self._keys()


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

    def __init__(self, model: XStepModel, xdefs: XeetDefs, base_name: str, log_info: Callable
                 ) -> None:
        self.model = model
        self.xdefs = xdefs
        self.base_name = base_name
        self.log_info = log_info

    def setup(self, _: XeetVars) -> str:
        ...

    def run(self) -> XStepResult:
        res = self.result_class()()
        start = timer()
        res.completed = self._run(res)
        res.duration = timer() - start
        self.log_info(f"step finished with in {res.duration:.3f}s")
        return res

    def print_name(self) -> str:
        if self.model.name:
            return f"{self.model.step_type} ('{self.model.name}')"
        return self.model.step_type

    def summary(self) -> str:
        return self.print_name()

    def _run(self, _: XStepResult) -> bool:
        raise NotImplementedError


@dataclass
class XStepListResult:
    prefix: str = ""
    results: list[XStepResult] = field(default_factory=list)
    completed: bool = True
    failed: bool = False

    def error_summary(self) -> str:
        for i, r in enumerate(self.results):
            if not r.completed or r.failed:
                return f"{self.prefix} step #{i}: {r.error_summary()}"
        return ""

    #  post_init is called after the dataclass is initialized. This is used
    #  in unittesting only. By default, results is empty, so completed and failed
    #  are True and False, respectively.
    def __post_init__(self) -> None:
        if not self.results:
            return
        self.completed = all([r.completed for r in self.results])
        self.failed = any([r.failed for r in self.results])


#  stop_on_err will stop if either a step fails or is incomplete
def run_xstep_list(step_list: list[XStep] | None, res: XStepListResult, stop_on_err: bool) -> None:
    if not step_list:
        return

    for step in step_list:
        step_res = step.run()
        res.results.append(step_res)
        if not step_res.completed:
            res.completed = False
            if stop_on_err:
                break
        if step_res.failed:
            res.failed = True
            if stop_on_err:
                break
