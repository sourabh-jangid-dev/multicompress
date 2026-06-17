"""
conftest.py
-----------
pytest loads this automatically before running tests. We use it to put our
`src/` folder on the import path so tests can `import compressor...` cleanly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
