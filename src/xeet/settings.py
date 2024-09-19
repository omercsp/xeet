from xeet.common import json_value
from typing import Any

_settings = {}


def set_settings(settings: dict[str, Any]):
    global _settings
    _settings = settings


#  Return the first value found by the JSONPath expression. If no value is found, return None
#  If multiple values are found, raise an exception
def setting_value(path: str) -> tuple[Any, bool]:
    return json_value(_settings, path)
