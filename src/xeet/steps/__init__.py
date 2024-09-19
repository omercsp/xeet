from xeet.xstep import XStep, XStepTestArgs, XeetStepInitException
from xeet.steps.exec_step import ExecStep
from xeet.steps.dummy_step import DummyStep
from xeet.common import pydantic_errmsg
from pydantic import ValidationError


_XSTEP_CLASSES: dict[str, type[XStep]] = {
    "exec": ExecStep,
    "dummy": DummyStep,
}


def gen_xstep(desc: dict, args: XStepTestArgs) -> XStep:
    model_type = desc.get("type")
    if not model_type:
        raise XeetStepInitException("Step type not specified", "", args)
    if model_type not in _XSTEP_CLASSES:
        raise XeetStepInitException(f"Unknown step type '{model_type}'", model_type, args)
    xstep_class = _XSTEP_CLASSES[model_type]
    xstep_model_class = xstep_class.model_class()
    try:
        xstep_model = xstep_model_class(**desc)
    except ValidationError as e:
        raise XeetStepInitException(f"{pydantic_errmsg(e)}", model_type, args)
    return xstep_class(xstep_model, args=args)
