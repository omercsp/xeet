from xeet.core.step import Step, StepModel, StepOwner, XeetStepInitException
from xeet.common import pydantic_errmsg
from pydantic import ValidationError
from .exec_step import ExecStep
from .dummy_step import DummyStep


_XSTEP_CLASSES: dict[str, type[Step]] = {
    "exec": ExecStep,
    "dummy": DummyStep,
}


def get_xstep_class(step_type: str) -> type[Step] | None:
    return _XSTEP_CLASSES.get(step_type)


_DFLT_STEP_TYPE_PATH = "settings.xeet.default_step_type"


#  Generate a step model from its descriptor, resolving its base step and type
def gen_step_model(owner: StepOwner, desc: dict, included: set[str] | None = None) -> StepModel:
    if included is None:
        included = set()
    base = desc.get("base")
    if base in included:
        raise XeetStepInitException(f"Include loop detected - '{base}'")

    base_step_model = None
    base_type = None
    if base:
        #  TODO: add refernce by name in addition to path
        base_desc, found = owner.rti.config_ref(base)
        if not found:
            raise XeetStepInitException(f"Base step '{base}' not found")
        if not isinstance(base_desc, dict):
            raise XeetStepInitException(f"Invalid base step '{base}'")
        base_step_model = gen_step_model(owner, base_desc, included)
        base_type = base_step_model.step_type

    model_type = desc.get("type")
    if model_type:
        if base_type and model_type != base_type:
            raise XeetStepInitException(
                f"Step type '{model_type}' doesn't match base type '{base_type}'")
    else:
        if not base_type:
            base_type, found = owner.rti.config_ref(_DFLT_STEP_TYPE_PATH)
            if found and base_type and isinstance(base_type, str):
                owner.notify(f"using default step type '{base_type}'")
            else:
                raise XeetStepInitException("Step type not specified")
        model_type = base_type
        desc["type"] = base_type

    step_class = get_xstep_class(model_type)
    if step_class is None:
        raise XeetStepInitException(f"Unknown step type '{model_type}'")
    step_model_class = step_class.model_class()
    try:
        step_model = step_model_class(**desc)
        if base_step_model:
            step_model.set_parent(base_step_model)
    except ValidationError as e:
        raise XeetStepInitException(f"{pydantic_errmsg(e)}")
    return step_model
