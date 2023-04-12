from xeet.core.step import Step
from .exec_step import ExecStep
from .dummy_step import DummyStep


_XSTEP_CLASSES: dict[str, type[Step]] = {
    "exec": ExecStep,
    "dummy": DummyStep,
}


def get_xstep_class(step_type: str) -> type[Step] | None:
    return _XSTEP_CLASSES.get(step_type)
