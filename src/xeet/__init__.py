import os.path
import importlib.util


__version_path = os.path.join(os.path.dirname(__file__), "_version.py")
try:
    __spec = importlib.util.spec_from_file_location("_version", __version_path)
    __module = importlib.util.module_from_spec(__spec)  # type: ignore
    __spec.loader.exec_module(__module)  # type: ignore
    xeet_version = __module.__version__
except (FileNotFoundError, ModuleNotFoundError, AttributeError):
    xeet_version = "0.0.0"
