from xeet.core.xstep import XStep
from .exec_step import ExecStep
from .dummy_step import DummyStep


_XSTEP_CLASSES: dict[str, type[XStep]] = {
    "exec": ExecStep,
    "dummy": DummyStep,
}


def get_xstep_class(step_type: str) -> type[XStep] | None:
    return _XSTEP_CLASSES.get(step_type)
