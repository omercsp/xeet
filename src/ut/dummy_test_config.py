from ut import XeetUnittest
from xeet.steps.dummy_step import DummyStepResult, DummyStepModel
from xeet.common import XeetVars


#  Unittest wrapper for dummy tests
class DummyTestConfig(XeetUnittest):
    def assertStepResultEqual(self, res: DummyStepResult, expected: DummyStepResult  # type: ignore
                              ) -> None:
        super().assertStepResultEqual(res, expected)
        self.assertIsInstance(res, DummyStepResult)
        self.assertIsInstance(expected, DummyStepResult)
        self.assertEqual(res.dummy_val0, expected.dummy_val0)

    def assertDummyDescsEqual(self, res: dict, expected: dict) -> None:
        self.assertIsInstance(res, dict)
        self.assertIsInstance(expected, dict)
        for k, v in expected.items():
            self.assertIn(k, res)
            self.assertEqual(res[k], v)
        for k in res.keys():
            self.assertIn(k, expected)


def gen_dummy_step_result(desc: dict, completed: bool = True, failed: bool = False,
                          xvars: XeetVars | None = None) -> DummyStepResult:
    dummy_val0 = desc.get("dummy_val0")
    dummy_val1 = desc.get("dummy_val1")
    if xvars is not None:
        dummy_val0 = xvars.expand(dummy_val0)
        dummy_val1 = xvars.expand(dummy_val1)
    return DummyStepResult(dummy_val0=dummy_val0, dummy_val1=dummy_val1, completed=completed,
                           failed=failed)


_dummy_fields = set(DummyStepModel.model_fields.keys())


def gen_dummy_step_desc(**kwargs) -> dict:
    for k in list(kwargs.keys()):
        if k != "type" and k not in _dummy_fields:
            raise ValueError(f"Invalid DummyStep field '{k}'")
    if "type" not in kwargs:
        kwargs["type"] = "dummy"
    return kwargs


def gen_dummy_step_model(**kwargs) -> DummyStepModel:
    return DummyStepModel(**gen_dummy_step_desc(**kwargs))


OK_STEP_DESC = gen_dummy_step_desc(dummy_val0="test")
OK_STEP_RESULT = gen_dummy_step_result(OK_STEP_DESC)
FAILING_STEP_DESC = gen_dummy_step_desc(fail=True)
FAILING_STEP_RESULT = gen_dummy_step_result(FAILING_STEP_DESC, failed=True)
INCOMPLETED_STEP_DESC = gen_dummy_step_desc(completed=False)
INCOMPLETED_STEP_RESULT = gen_dummy_step_result(INCOMPLETED_STEP_DESC, completed=False)
