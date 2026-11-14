"""Verify the actual app imports in a new process, independent of pytest's module cache."""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_app_imports_resolve_in_fresh_interpreter(tmp_path):
    # An isolated bytecode cache also prevents stale repository .pyc files from
    # concealing a missing definition in the current source files.
    result = subprocess.run(
        [sys.executable, "-X", f"pycache_prefix={tmp_path / 'pycache'}", "-c", """
from pathlib import Path
import inspect
import app
from core import dashboard_charts

assert Path(app.__file__).resolve() == Path.cwd() / 'app.py'
assert Path(dashboard_charts.__file__).resolve() == Path.cwd() / 'core/dashboard_charts.py'
for name in ('temperature_figure', 'comparison_temperature_figure', 'warming_rate_figure'):
    assert getattr(app, name) is getattr(dashboard_charts, name)
inspect.signature(app.temperature_figure).bind(None, 'Annual', True, color='#007F86')
inspect.signature(app.comparison_temperature_figure).bind({}, 'Monthly', {})
inspect.signature(app.warming_rate_figure).bind({}, {})
print('App import successful')
"""],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"Fresh app import failed:\n{result.stdout}\n{result.stderr}"
    assert "App import successful" in result.stdout
