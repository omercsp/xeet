from ut import register_res_comparison
from xeet.steps.dummy_step import DummyStepResult, DummyStepModel
from xeet.common import XeetVars


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


DUMMY_OK_STEP_DESC = gen_dummy_step_desc(dummy_val0="test")
DUMMY_OK_STEP_RES = gen_dummy_step_result(DUMMY_OK_STEP_DESC)
DUMMY_FAILING_STEP_DESC = gen_dummy_step_desc(fail=True)
DUMMY_FAILING_STEP_RES = gen_dummy_step_result(DUMMY_FAILING_STEP_DESC, failed=True)
DUMMY_INCOMPLETED_STEP_DESC = gen_dummy_step_desc(completed=False)
DUMMY_INCOMPLETED_STEP_RES = gen_dummy_step_result(DUMMY_INCOMPLETED_STEP_DESC, completed=False)


def _compare_dummy_test_result(res: DummyStepResult, expected: DummyStepResult) -> None:
    assert isinstance(res, DummyStepResult)
    assert isinstance(expected, DummyStepResult)
    assert res.dummy_val0 == expected.dummy_val0
    assert res.dummy_val1 == expected.dummy_val1


register_res_comparison(DummyStepResult, _compare_dummy_test_result)


__all__ = ["gen_dummy_step_result", "gen_dummy_step_desc", "gen_dummy_step_model",
           "DUMMY_OK_STEP_DESC", "DUMMY_OK_STEP_RES", "DUMMY_FAILING_STEP_DESC",
           "DUMMY_FAILING_STEP_RES", "DUMMY_INCOMPLETED_STEP_DESC", "DUMMY_INCOMPLETED_STEP_RES"]
