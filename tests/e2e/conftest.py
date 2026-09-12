"""The REAL layout against REAL core.

The pure suite one directory up runs with Home Assistant absent and proves
the rule. This one installs core plus pytest-homeassistant-custom-component
and proves the integration: entries, subentries, devices, areas, entities,
the button and the three actions. It stages the repo root as
`custom_components/house_cleaning` in a temp dir -- the layout HACS installs
-- and appends that to the harness's own `custom_components` package, which
it imports first and which would otherwise shadow ours (its
`testing_config/custom_components` wins the import, and the loader then
reports "Integration not found" over a package that is right there).

Needs Python 3.14 and the core version hacs.json names; tools/run_e2e.sh
builds that venv with uv. The pure suite must never depend on this.
"""

import atexit
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent

_stage = Path(tempfile.mkdtemp(prefix="house_cleaning_e2e_"))
atexit.register(shutil.rmtree, _stage, True)
_pkg = _stage / "custom_components" / "house_cleaning"
_pkg.mkdir(parents=True)
for src in ROOT.iterdir():
    if src.suffix == ".py" or src.name in ("manifest.json", "services.yaml"):
        shutil.copy(src, _pkg / src.name)
shutil.copytree(ROOT / "translations", _pkg / "translations")

try:
    import custom_components  # the harness's package, already imported by its plugin
except ModuleNotFoundError:
    sys.path.insert(0, str(_stage))
    import custom_components
if str(_stage / "custom_components") not in custom_components.__path__:
    custom_components.__path__.append(str(_stage / "custom_components"))


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield
