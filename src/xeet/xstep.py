from xeet.common import XeetVars, XeetException, KeysBaseModel, yes_no_str
from xeet import XeetDefs
from xeet.log import log_info, log_warn, log_error, log_raw
from xeet.pr import pr_info, pr_warn, pr_error
from pydantic import ConfigDict, Field
from dataclasses import dataclass
from timeit import default_timer as timer
from typing import Any
import sys


class XStepModel(KeysBaseModel):
    model_config = ConfigDict(extra='forbid')
    base: str = ""
    step_type: str = Field("", validation_alias="type")
    name: str = ""
    parent: "XStepModel | None" = Field(None, exclude=True)

    def inherit(self, parent: "XStepModel") -> None:
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


DetailList = list[tuple[str, Any]]


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

    #  The base list for details to print is the entire model dump. After which
    #  fields can be added or removed by the _details_include() and _details_exclude()
    #  methods. Values can be formatted by the _printable_value() method.
    def details(self, full: bool, printable: bool, setup: bool) -> DetailList:
        keys = self._detail_keys(full, setup)
        dflt_exclude = KeysBaseModel.model_fields.keys() | {"model_config", "parent"}

        for key in dflt_exclude:
            keys.discard(key)

        ret = []
        #  For printabel details request, we first insert the fields in the order
        #  defined by _printable_field_order() and then the rest of the fields.
        if printable:
            for key in self._printable_field_order():
                if key not in keys:
                    self.log_warn(f"Ordered key '{key}' not in valid keys")
                    continue
                keys.discard(key)
                key_name = self._printable_field_name(key)
                value = self._detail_value(key, setup, printable)
                ret.append((key_name, value))

        if printable:
            keys = sorted(keys)

        for key in keys:
            key_name = self._printable_field_name(key)
            value = self._detail_value(key, setup, printable)
            ret.append((key_name, value))
        return ret

    def _detail_keys(self, full: bool, setup: bool) -> set[str]:
        if full:
            return set(self.model.model_dump().keys())
        else:
            return self.model.field_keys | self.model.inherited_keys

    #  Sets the order of the fields in the printable details list. Fields that
    #  shoudl be printed but not on the list, will be printed after the fields
    #  in this list in arbitrary order.
    def _printable_field_order(self) -> list[str]:
        return ["name", "step_type", "base"]

    #  Converts the value of the field to a printable string. Derived classes
    #  can override this method to provide custom formatting
    def _detail_value(self, key: str, setup: bool, printable: bool) -> Any:
        base_obj = self if setup else self.model
        try:
            value = getattr(base_obj, key)
        except AttributeError:
            return "<Not set>"

        if not printable:
            return value
        if isinstance(value, bool):
            return yes_no_str(value)
        if isinstance(value, list):
            if not value:
                return "<empty list>"
            return ", ".join([str(x) for x in value])
        if isinstance(value, str) and not value:
            return "''"
        if isinstance(value, dict) and not value:
            return "{}"
        return str(value)

    #  Converts the field name to a printable string. Derived classes can override
    #  this method to provide custom formatting
    def _printable_field_name(self, name: str) -> str:
        if not name:
            return name
        ret = name.replace("_", " ")
        ret = ret[0].upper() + ret[1:]
        return ret
