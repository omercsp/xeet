from xeet.common import XeetVars, XeetException
from xeet.log import log_info
from pydantic import BaseModel, ConfigDict, Field
from dataclasses import dataclass, field
from typing import Callable
from timeit import default_timer as timer



class XStepModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    step_type: str = Field(validation_alias="type")
    name: str = ""


class XeetStepException(XeetException):
    ...


#  This class is used to pass arguments to the step classes
@dataclass
class XStepTestArgs:
    log_info: Callable = log_info
    debug_mode: bool = False
    output_dir: str = ""
    stage_prefix: str = ""
    index: int = 0


class XeetStepInitException(XeetStepException):
    def __init__(self, error: str, step_type, args: XStepTestArgs) -> None:
        super().__init__(error)
        self.step_type = step_type
        self.prefix = args.stage_prefix
        self.index = args.index

    def __str__(self) -> str:
        ret = f"Error initializing {self.prefix} step {self.index}"
        if self.step_type:
            ret += f" ({self.step_type})"
        return f"{ret}:\n{self.error}"


@dataclass
class XStepResult:
    step: "XStep"
    failed: bool = False
    err_summary: str = ""
    completed: bool = False
    duration: float | None = None

    def error_summary(self) -> str:
        ret = f"{self.step.stage_prefix} step {self.step.index}"
        if self.step.model.name:
            ret += f" ('{self.step.model.name}')"
        if not self.completed:
            ret += f" incomplete: {self.err_summary}"
        if self.failed:
            ret += f" failed: {self.err_summary}"
        return ret


class XStep:
    @staticmethod
    def model_class() -> type[XStepModel]:
        return XStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return XStepResult

    def __init__(self, model: XStepModel, args: XStepTestArgs):
        self.model = model
        self.test_settings = args
        self.log_info = args.log_info
        self.index = args.index
        self.stage_prefix = args.stage_prefix

    def expand(self, _: XeetVars) -> str:
        ...

    def run(self) -> XStepResult:
        res = self.result_class()(self)
        start = timer()
        self._run(res)
        res.duration = timer() - start
        self.log_info(f"step finished with in {res.duration:.3f}s")
        return res

    def print_name(self) -> str:
        ret = f"{self.stage_prefix} step {self.index}: {self.model.step_type}"
        if self.model.name:
            ret += f" ('{self.model.name}')"
        return ret

    def summary(self) -> str:
        return self.print_name()

    def _run(self, _: XStepResult) -> XStepResult:
        raise NotImplementedError


@dataclass
class XStepListResult:
    results: list[XStepResult] = field(default_factory=list)
    completed: bool = True
    failed: bool = False

    def error_summary(self) -> str:
        return "\n".join([r.error_summary() for r in self.results if r.failed])

    #  post_init is called after the dataclass is initialized. This is used
    #  in unittesting only. By default, results is empty, so completed and failed
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
