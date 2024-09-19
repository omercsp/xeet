#  Dummy step for testing purposes
from xeet.common import XeetVars
from xeet.xstep import XStep, XStepModel, XStepResult, XStepTestArgs
from typing import ClassVar
from typing_extensions import Any
from dataclasses import dataclass


class DummyStepModel(XStepModel):
    dummy_field: str = ""
    return_value: str | int | float | bool | None = None
    fail: bool = False
    completed: bool = True

    parent_fields: ClassVar[set[str]] = set(XStepModel.model_fields.keys())

    def inherit(self, parent: "DummyStepModel") -> None:  # type: ignore
        super().inherit(parent)
        for attr in self.model_fields:
            if attr in self.parent_fields or self._had_key(attr):
                continue
            setattr(self, attr, getattr(parent, attr))


@dataclass
class DummyStepResult(XStepResult):
    return_value: Any = None


class DummyStep(XStep):
    @staticmethod
    def model_class() -> type[XStepModel]:
        return DummyStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return DummyStepResult

    def __init__(self, model: DummyStepModel, args: XStepTestArgs):
        super().__init__(model, args)
        self.dummy_model = model
        self.dummy_field = None
        self.return_value = None

    def setup(self, xvars: XeetVars) -> None:  # type: ignore
        self.dummy_field = xvars.expand(self.dummy_model.dummy_field)
        self.return_value = xvars.expand(self.dummy_model.return_value)

    def _run(self, res: DummyStepResult) -> bool:  # type: ignore
        res.return_value = self.return_value
        res.failed = self.dummy_model.fail
        if res.failed:
            res.err_summary = "Dummy step failure"
        ret = self.dummy_model.completed
        if not ret:
            res.err_summary = "Dummy step incomplete"
        return ret
