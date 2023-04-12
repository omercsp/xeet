#  Dummy step for testing purposes
from xeet.core.step import Step, StepModel, StepResult
from typing import Any
from dataclasses import dataclass


class DummyStepModel(StepModel):
    dummy_val0: str | int | dict | list | float | bool | None = None
    dummy_val1: str | int | dict | list | float | bool | None = None
    fail: bool = False
    completed: bool = True


@dataclass
class DummyStepResult(StepResult):
    dummy_val0: str | int | dict | list | float | bool | None = None
    dummy_val1: str | int | dict | list | float | bool | None = None


class DummyStep(Step):
    @staticmethod
    def model_class() -> type[StepModel]:
        return DummyStepModel

    @staticmethod
    def result_class() -> type[StepResult]:
        return DummyStepResult

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.dummy_model: DummyStepModel = kwargs["model"]
        self.dummy_val0 = self.dummy_model.dummy_val0
        self.dummy_val1 = self.dummy_model.dummy_val1

    def setup(self, **kwargs) -> None:  # type: ignore
        super().setup(**kwargs)
        self.dummy_val0 = self.xvars.expand(self.dummy_model.dummy_val0)
        self.dummy_val1 = self.xvars.expand(self.dummy_model.dummy_val1)

    def _run(self, res: DummyStepResult) -> bool:  # type: ignore
        res.dummy_val0 = self.dummy_val0
        res.dummy_val1 = self.dummy_val1
        res.failed = self.dummy_model.fail
        if res.failed:
            res.errmsg = "Dummy step failure"
        ret = self.dummy_model.completed
        if not ret:
            res.errmsg = "Dummy step incomplete"
        return ret

    def _field_details_order(self) -> list[str]:
        return ["dummy_val1", "dummy_val0"]

    def _detail_value(self, key: str, printable: bool, setup: bool = False, **_) -> Any:
        if key == "dummy_val0":
            value = self.dummy_val0 if setup else self.dummy_model.dummy_val0
            return f"Printable {value}" if printable else value
        if key == "dummy_val1":
            value = self.dummy_val1 if setup else self.dummy_model.dummy_val1
            return str(value) if printable else value
        if key == "self_id":
            ret = id(self)
            return str(id) if printable else ret
        return super()._detail_value(key=key, printable=printable)

    def _printable_field_name(self, name: str) -> str:
        if name == "dummy_val0":
            return "Printable dummy value 0"
        if name == "self_id":
            return "Step ID"
        return super()._printable_field_name(name)

    def _details_keys(self, full: bool) -> set[str]:
        ret = super()._details_keys(full).union({"dummy_val0", "dummy_val1"})
        if full:
            ret.add("self_id")
        return ret
