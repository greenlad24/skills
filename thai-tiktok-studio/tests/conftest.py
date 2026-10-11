import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def pytest_configure(config):
    os.environ.setdefault("TTS_STUDIO_NO_BROWSER", "1")
