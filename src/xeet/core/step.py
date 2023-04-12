import logging
from . import system_var_name, RuntimeInfo
from .result import StepResult, time_result
from xeet.common import XeetVars, XeetException, KeysBaseModel, yes_no_str, platform_path
from pydantic import ConfigDict, Field
from typing import Any, TYPE_CHECKING
import os

if TYPE_CHECKING:
    from .test import Test, Phase


class StepModel(KeysBaseModel):
    model_config = ConfigDict(extra='forbid')
    base: str = ""
    step_type: str = Field("", validation_alias="type")
    name: str = ""
    parent: "StepModel | None" = Field(None, exclude=True)

    def inherit(self, parent: "StepModel") -> None:
        self.parent = parent
        parent_field_keys = parent.field_keys | parent.inherited_keys
        for attr in parent_field_keys:
            if self.has_key(attr):
                continue
            self.inherit_attr(attr, getattr(parent, attr))


class XeetStepException(XeetException):
    ...


class XeetStepInitException(XeetStepException):
    ...


DetailList = list[tuple[str, Any]]


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

    def notify(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, **kwargs)

    def warn(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, severity=logging.WARN, **kwargs)

    def error(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, severity=logging.ERROR, **kwargs)

    def debug(self, *args, **kwargs) -> None:
        self.rti.notifier.on_step_message(self, *args, dbg_pr=True, **kwargs)

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

    _DFLT_KEYS = ["name", "step_type", "base"]

    #  The base list for details to print is the entire model dump. After which
    #  fields can be added or removed by the _details_include() and _details_exclude()
    #  methods. Values can be formatted by the _printable_value() method.
    def details(self, full: bool, printable: bool, setup: bool) -> DetailList:
        keys = self._details_keys(full=full, setup=setup)
        dflt_exclude = KeysBaseModel.model_fields.keys() | {"model_config", "parent"}

        for key in dflt_exclude:
            keys.discard(key)

        ret = []
        #  For printabel details request, we first insert the fields in the order
        #  defined by _printable_field_order() and then the rest of the fields.
        if printable:
            order = self._DFLT_KEYS + self._printable_field_order()
            for key in order:
                if key not in keys:  # name and base are optional
                    continue
                keys.discard(key)
                key_name = self._printable_field_name(key)
                value = self._detail_value(key=key, setup=setup, printable=printable)
                ret.append((key_name, value))

        if printable:
            keys = sorted(keys)

        for key in keys:
            key_name = self._printable_field_name(key) if printable else key
            if key_name in self._DFLT_KEYS:
                value = getattr(self.model, key)
            value = self._detail_value(key=key, setup=setup, printable=printable)
            ret.append((key_name, value))
        return ret

    #  Return a valid output path for the step.
    def _output_file(self, name: str) -> str:
        if not name:
            raise XeetStepException("Empty output file name")
        if os.path.isabs(name):
            raise XeetStepException(f"Output file '{name}' must be relative")
        ret = os.path.join(self.output_dir, name)
        return platform_path(ret)

    def _details_keys(self, full: bool, **_) -> set[str]:
        if full:
            return set(self.model.model_dump().keys())
        else:
            return self.model.field_keys | self.model.inherited_keys

    #  Sets the order of the fields in the printable details list. Fields that
    #  shoudl be printed but not on the list, will be printed after the fields
    #  in this list in arbitrary order.
    def _printable_field_order(self) -> list[str]:
        return []

    #  Converts the value of the field to a printable string. Derived classes
    #  can override this method to provide custom formatting. By default, keys
    #  are searched in the model and returned as is. Derived classes can override
    #  this method to provide custom formatting. The setup parameter is used to
    #  distinguish between the fields that are used in the setup() method and the
    #  and is hidden here in the **_ parameter.
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
        if isinstance(value, (float, int, bool, str)):
            return value
        return str(value)

    #  Converts the field name to a printable string. Derived classes can override
    #  this method to provide custom formatting
    def _printable_field_name(self, name: str) -> str:
        if not name:
            return name
        ret = name.replace("_", " ")
        ret = ret[0].upper() + ret[1:]
        return ret
