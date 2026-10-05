"""Load ``scripts/manage.py`` for tests.

It lives outside the package because it is an operator entry point, so it cannot
be imported by name. Loading it once here keeps the loader logic in one place
instead of repeated in every test module that needs it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "manage.py"


def load_manage() -> ModuleType:
    """Import the manage script under a stable module name."""
    if "manage_script" in sys.modules:
        return sys.modules["manage_script"]

    spec = importlib.util.spec_from_file_location("manage_script", _SCRIPT)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"could not load {_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["manage_script"] = module
    spec.loader.exec_module(module)
    return module
