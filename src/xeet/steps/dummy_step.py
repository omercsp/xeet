#  Dummy step for testing purposes
from xeet.common import XeetVars
from xeet.xstep import XStep, XStepModel, XStepResult
from xeet import XeetDefs
from typing import ClassVar
from dataclasses import dataclass


class DummyStepModel(XStepModel):
    dummy_val0: str | int | dict | list | float | None = None
    dummy_val1: str | int | dict | list | float | None = None
    fail: bool = False
    completed: bool = True

    parent_fields: ClassVar[set[str]] = set(XStepModel.model_fields.keys())

    def inherit(self, parent: "DummyStepModel") -> None:  # type: ignore
        super().inherit(parent)
        for attr in self.model_fields:
            if attr in self.parent_fields or self.has_key(attr):
                continue
            setattr(self, attr, getattr(parent, attr))


@dataclass
class DummyStepResult(XStepResult):
    dummy_val0: str | int | dict | list | float | None = None
    dummy_val1: str | int | dict | list | float | None = None


class DummyStep(XStep):
    @staticmethod
    def model_class() -> type[XStepModel]:
        return DummyStepModel

    @staticmethod
    def result_class() -> type[XStepResult]:
        return DummyStepResult

    def __init__(self, model: DummyStepModel, xdefs: XeetDefs, base_name: str) -> None:
        super().__init__(model, xdefs, base_name)
        self.dummy_model = model
        self.dummy_val0 = None
        self.dummy_val1 = None

    def setup(self, xvars: XeetVars) -> None:  # type: ignore
        self.dummy_val0 = xvars.expand(self.dummy_model.dummy_val0)
        self.dummy_val1 = xvars.expand(self.dummy_model.dummy_val1)

    def _run(self, res: DummyStepResult) -> bool:  # type: ignore
        res.dummy_val0 = self.dummy_val0
        res.dummy_val1 = self.dummy_val1
        res.failed = self.dummy_model.fail
        if res.failed:
            res.err_summary = "Dummy step failure"
        ret = self.dummy_model.completed
        if not ret:
            res.err_summary = "Dummy step incomplete"
        return ret
