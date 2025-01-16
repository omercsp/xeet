#  Dummy step for testing purposes
from xeet.core.step import Step, StepModel, StepResult
from typing import ClassVar, Any
from dataclasses import dataclass


class DummyStepModel(StepModel):
    dummy_val0: str | int | dict | list | float | bool | None = None
    dummy_val1: str | int | dict | list | float | bool | None = None
    fail: bool = False
    completed: bool = True

    parent_fields: ClassVar[set[str]] = set(StepModel.model_fields.keys())

    def inherit(self, parent: "DummyStepModel") -> None:  # type: ignore
        super().inherit(parent)
        for attr in DummyStepModel.model_fields:
            if attr in self.parent_fields or self.has_key(attr):
                continue
            setattr(self, attr, getattr(parent, attr))


@dataclass
class DummyStepResult(StepResult):
    dummy_val0: str | int | dict | list | float | bool | None = None
    dummy_val1: str | int | dict | list | float | bool | None = None


DUMMY_EXTRA = "dummy_extra"
DUMMY_EXTRA_PRINT = "Dummy extra print"


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
        self.dummy_val0 = None
        self.dummy_val1 = None

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

    def _details_keys(self, full: bool, setup: bool = False, **_) -> set[str]:
        ret = super()._details_keys(full=full)
        if setup:
            ret |= {DUMMY_EXTRA}
        return ret

    def _printable_field_order(self) -> list[str]:
        return ["dummy_val1", "dummy_val0"]

    def _detail_value(self, key: str, printable: bool, setup: bool = False, **_) -> Any:
        if not setup:
            return super()._detail_value(key=key, printable=printable)

        if key == DUMMY_EXTRA:
            return id(self)
        if key == "dummy_val0":
            return self.dummy_val0
        if key == "dummy_val1":
            return self.dummy_val1
        return super()._detail_value(key=key, printable=printable)

    def _printable_field_name(self, name: str) -> str:
        if name == DUMMY_EXTRA:
            return DUMMY_EXTRA_PRINT
        return super()._printable_field_name(name)
