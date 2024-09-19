from ut import XeetUnittest
from xeet.steps.dummy_step import DummyStepResult
from xeet.steps.dummy_step import DummyStepModel
from xeet.steps.dummy_step import DummyStep
from xeet.xstep import XStepTestArgs


#  Unittest wrapper for dummy tests
class DummyTestConfig(XeetUnittest):
    def assertStepResultEqual(self, res: DummyStepResult, expected: DummyStepResult  # type: ignore
                              ) -> None:
        super().assertStepResultEqual(res, expected)
        self.assertIsInstance(res, DummyStepResult)
        self.assertIsInstance(expected, DummyStepResult)
        self.assertEqual(res.return_value, expected.return_value)


_dummy_fields = set(DummyStepModel.model_fields.keys())


def gen_dummy_step_desc(**kwargs) -> dict:
    for k in list(kwargs.keys()):
        if k not in _dummy_fields:
            raise ValueError(f"Invalid DummyStep field '{k}'")
    return {"type": "dummy", **kwargs}


_step_args = XStepTestArgs()


def gen_dummy_step(args: dict) -> DummyStep:
    model = DummyStepModel(**args)
    return DummyStep(model, _step_args)


def gen_dummy_step_result(step: DummyStep, completed: bool, failed: bool) -> DummyStepResult:
    return DummyStepResult(step=step, return_value=step.dummy_model.return_value,
                           completed=completed, failed=failed)


OK_STEP_DESC = gen_dummy_step_desc(return_value="test")
OK_STEP = gen_dummy_step(OK_STEP_DESC)
OK_STEP_RESULT = gen_dummy_step_result(OK_STEP, completed=True, failed=False)
FAILING_STEP_DESC = gen_dummy_step_desc(fail=True)
FAILING_STEP = gen_dummy_step(FAILING_STEP_DESC)
FAILING_STEP_RESULT = gen_dummy_step_result(FAILING_STEP, completed=True, failed=True)
INCOMPLETED_STEP_DESC = gen_dummy_step_desc(completed=False)
INCOMPLETED_STEP = gen_dummy_step(INCOMPLETED_STEP_DESC)
INCOMPLETED_STEP_RESULT = gen_dummy_step_result(INCOMPLETED_STEP, completed=False, failed=False)
