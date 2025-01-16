from ut import *
from ut.ut_dummy_defs import *
from xeet.core import XeetVars, XeetVarsModel, system_var_name
from xeet.core.conf import XeetConfModel, XeetIncludeLoopException, xeet_conf
import os


@pytest.fixture(scope="module")
def conf_xvars():
    return XeetVars(start_vars=XeetVarsModel({
            system_var_name("ROOT"): xeet_ut_dir_name(),
    }))


def test_config_model_inclusion(conf_xvars: XeetVars):
    CONF0 = "conf0.yaml"
    CONF1 = "conf1.yaml"
    CONF2 = "conf2.yaml"
    CONF3 = "conf3.yaml"
    CONF4 = "conf4.yaml"

    conf0 = ConfigTestWrapper(CONF0)
    root = os.path.dirname(conf0.file_path)
    d0_0 = conf0.add_test(TEST0, arg=1)
    conf0.add_var("var0", 0)
    conf0.add_setting("setting0", {"a": 0}, save=True)

    conf1 = ConfigTestWrapper(CONF1)
    conf1.add_include(conf0.file_path)
    d1_1 = conf1.add_test(TEST1, arg=2)
    conf1.add_var("var1", 1)
    conf1.add_setting("setting1", {"a": 1}, save=True)

    model = xeet_conf(conf1.file_path, conf_xvars).model

    assert isinstance(model, XeetConfModel)
    assert len(model.tests) == 2
    assert model.tests[0] == d0_0
    assert model.tests[1] == d1_1
    assert len(model.variables) == 2
    assert model.variables["var0"] == 0
    assert model.variables["var1"] == 1
    assert len(model.settings) == 2
    assert model.settings["setting0"] == {"a": 0}
    assert model.settings["setting1"] == {"a": 1}

    conf2 = ConfigTestWrapper(CONF2)
    conf2.add_include("{XEET_ROOT}/" + CONF1)
    d2_0 = conf2.add_test(TEST0, arg=30)
    d2_1 = conf2.add_test(TEST1, arg=40)
    d2_2 = conf2.add_test(TEST2, arg=50)  # new test
    conf2.save()
    model = xeet_conf(conf2.file_path, conf_xvars).model
    assert isinstance(model, XeetConfModel)
    assert len(model.tests) == 3
    assert model.tests[0] == d2_0
    assert model.tests[1] == d2_1
    assert model.tests[2] == d2_2

    conf3 = ConfigTestWrapper(CONF3)
    conf3.add_include(f"{root}/{CONF1}")
    d3_0 = conf3.add_test(TEST0, arg=31)
    d3_3 = conf3.add_test(TEST3, arg=41)
    d3_4 = conf3.add_test(TEST4, arg=51, save=True)
    #  model = xeet_conf(BaseXeetSettings(conf3.file_path)).model

    conf4 = ConfigTestWrapper(CONF4)
    conf4.add_include(f"{root}/{CONF2}")
    conf4.add_include(f"{root}/{CONF3}")
    d4_5 = conf4.add_test(TEST5, arg=62)
    conf4.save()

    model = xeet_conf(conf4.file_path, conf_xvars).model
    assert isinstance(model, XeetConfModel)
    assert len(model.tests) == 6
    assert model.tests_dict[TEST0] == d3_0
    assert model.tests_dict[TEST1] == d1_1
    assert model.tests_dict[TEST2] == d2_2
    assert model.tests_dict[TEST3] == d3_3
    assert model.tests_dict[TEST4] == d3_4
    assert model.tests_dict[TEST5] == d4_5
    assert model.settings["setting0"] == {"a": 0}
    assert model.settings["setting1"] == {"a": 1}


def test_inclusion_loop(conf_xvars: XeetVars):
    CONF0 = "conf0.json"
    CONF1 = "conf1.json"
    CONF2 = "conf2.json"

    conf0 = ConfigTestWrapper(CONF0)
    conf0.add_include(conf0.file_path)
    conf0.save()

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf0.file_path, conf_xvars)

    conf1 = ConfigTestWrapper(CONF1)
    conf1.add_include(conf0.file_path)
    conf1.save()
    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf1.file_path, conf_xvars)
    conf0.includes = [conf1.file_path]
    conf0.save()

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf0.file_path, conf_xvars)

    conf2 = ConfigTestWrapper(CONF2)
    conf2.add_include(conf1.file_path)
    conf2.save()
    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf2.file_path, conf_xvars)

    conf0.includes = [conf2.file_path]
    conf0.save()
    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf0.file_path, conf_xvars)

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf0.file_path, conf_xvars)

    with pytest.raises(XeetIncludeLoopException):
        xeet_conf(conf0.file_path, xvars=conf_xvars)
