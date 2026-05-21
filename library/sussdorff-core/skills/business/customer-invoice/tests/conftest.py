"""conftest.py — sys.path bootstrap for pytest importlib mode.

When pytest runs in importlib mode (--import-mode=importlib), it no longer
prepends the test's parent directory to sys.path automatically. This conftest
inserts the skill's source directory so that `from invoice_number import ...`
and `from timing_helper import ...` resolve correctly.
"""
import sys
from pathlib import Path

_SKILL_DIR = Path(__file__).parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))
