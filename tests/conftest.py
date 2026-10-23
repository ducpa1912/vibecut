import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("VIBECUT_DATA", tempfile.mkdtemp(prefix="vibecut-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
