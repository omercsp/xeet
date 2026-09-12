import logging
from . import system_var_name, RuntimeInfo
from .result import StepResult, time_result
from xeet.common import XeetVars, XeetException, yes_no_str, platform_path
from pydantic import BaseModel, ConfigDict, Field
from typing import Any, TYPE_CHECKING
from threading import Lock
import os

if TYPE_CHECKING:
    from .test import Test, Phase


class StepModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base: str = ""
    step_type: str = Field("", validation_alias="type")
    name: str = ""
    parent: "StepModel | None" = Field(None, exclude=True)

    def set_parent(self, parent: "StepModel") -> None:
        self.parent = parent
        parent_field_keys = parent.user_keys()
        self_keys = self.user_keys(include_parent=False)
        for attr in parent_field_keys:
            if attr not in self_keys and hasattr(parent, attr):
                setattr(self, attr, getattr(parent, attr))

    def user_keys(self, include_parent: bool = True) -> set[str]:
        ret = set(self.model_dump(exclude_unset=True).keys())
        if self.parent and include_parent:
            ret = ret.union(self.parent.user_keys(include_parent=True))
        return ret


class XeetStepException(XeetException):
    ...


class XeetStepInitException(XeetStepException):
    ...


class Step:
    @staticmethod
    def model_class() -> type[StepModel]:
        return StepModel

    @staticmethod
    def result_class() -> type[StepResult]:
        return StepResult

    def __init__(self, model: StepModel, test: "Test", phase: "Phase", step_index) -> None:
        self.model = model
        self.test = test
        self.phase = phase
        self.step_index = step_index
        self.xvars: XeetVars = None  # type: ignore
        self.output_dir = ""
        self.step_run_lock = Lock()
        self.stop_requested = False

    @property
    def rti(self) -> RuntimeInfo:
        return self.test.rti

    def setup(self, xvars: XeetVars, base_dir: str):
        self.xvars = xvars
        self.output_dir = os.path.join(base_dir, f"{self.phase.short_name}{self.step_index}")
        self.output_dir = platform_path(self.output_dir)
        self.xvars.set_vars({
            system_var_name("STEP_OUT_DIR"): self.output_dir,
            system_var_name("STEP_INDEX"): self.step_index,
        })

    @property
    def was_setup(self) -> bool:
        return self.xvars is not None

    def notify(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, **kwargs)

    def warn(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, severity=logging.WARN, **kwargs)

    def error(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, severity=logging.ERROR, **kwargs)

    def debug(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, dbg_pr=True, **kwargs)

    def output(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_output(self, *args, **kwargs)

    @time_result
    def run(self) -> StepResult:
        res = self.result_class()(step=self)
        os.makedirs(self.output_dir, exist_ok=True)
        res.completed = self._run(res)
        return res

    def print_name(self) -> str:
        if self.model.name:
            return f"{self.model.step_type} ('{self.model.name}')"
        return self.model.step_type

    def summary(self) -> str:
        return self.print_name()

    @property
    def debug_mode(self) -> bool:
        return self.test.rti.debug_mode

    def _run(self, _: StepResult) -> bool:
        raise NotImplementedError

    def stop(self):
        with self.step_run_lock:
            self.stop_requested = True
            self._stop()

    def _stop(self) -> None:
        ...

    _DFLT_KEYS = ["name", "step_type", "base"]

    #  Internal model fields, never reported as step details. Filtered here rather
    #  than in _details_keys() so derived classes can't reintroduce them.
    _INTERNAL_KEYS = {"model_config", "parent"}

    def details(self, full: bool, printable: bool) -> dict[str, Any]:
        keys = self._details_keys(full=full) - self._INTERNAL_KEYS

        ret = dict()
        order = self._DFLT_KEYS + self._field_details_order()
        #  Sort the leftovers, otherwise set iteration makes the output order
        #  vary between runs (str hashing is randomized per process)
        order = order + sorted(keys - set(order))
        for key in order:
            if key not in keys:
                continue
            key_name = self._printable_field_name(key) if printable else key
            ret[key_name] = self._detail_value(key=key, printable=printable, setup=self.was_setup)
        return ret

    #  Return a valid output path for the step.
    def _output_file(self, name: str) -> str:
        if not name:
            raise XeetStepException("Empty output file name")
        if os.path.isabs(name):
            raise XeetStepException(f"Output file '{name}' must be relative")
        ret = os.path.join(self.output_dir, name)
        return platform_path(ret)

    def _details_keys(self, full: bool) -> set[str]:
        if full:
            return set(StepModel.model_fields.keys())
        return self.model.user_keys()

    #  Sets the order of the fields in the printable details list. Fields that
    #  shoudl be printed but not on the list, will be printed after the fields
    #  in this list in arbitrary order.
    def _field_details_order(self) -> list[str]:
        return []

    def _detail_value(self, key: str, printable: bool, **_) -> Any:
        try:
            value = getattr(self.model, key)
        except AttributeError:
            return "<Not set>"
        return self._printable_value(value) if printable else value

    _EMPTY = "<empty>"

    def _printable_value(self, value: Any) -> Any:
        if isinstance(value, bool):
            return yes_no_str(value)
        if isinstance(value, (list, tuple)):
            if not value:
                return self._EMPTY
            return ", ".join([str(x) for x in value])
        if isinstance(value, str) and not value:
            return f"'' {self._EMPTY}"
        if isinstance(value, dict) and not value:
            return self._EMPTY
        return str(value)

    #  Converts the field name to a printable string. Derived classes can override
    #  this method to provide custom formatting
    def _printable_field_name(self, name: str) -> str:
        if not name:
            return name
        ret = name.replace("_", " ")
        ret = ret[0].upper() + ret[1:]
        return ret
