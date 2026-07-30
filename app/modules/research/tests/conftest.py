"""Test harness: DRY_RUN + isolated temp SQLite, no network, $0.

Env is set BEFORE any app.core import so the cached `settings` singleton and the DB
engine bind to the temp database and DRY_RUN mode.
"""

from __future__ import annotations

import os
import struct
import tempfile

# Must precede app.core imports (settings + engine are built at import time).
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".sqlite3", prefix="research_test_")
os.environ.setdefault("DRY_RUN", "true")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"

import pytest  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core import models as _core_models  # noqa: E402,F401  (register core tables)
from app.modules.research import models as _res_models  # noqa: E402,F401  (register research tables)


@pytest.fixture()
def db():
    """Function-scoped session over a freshly (re)created schema — full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Fabricated image bytes (no Pillow needed — sniff_image reads headers only)
# --------------------------------------------------------------------------- #
def make_png(width: int, height: int, salt: bytes = b"") -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = b"\x00\x00\x00\x0d" + b"IHDR" + struct.pack(">II", width, height)
    ihdr += b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00"  # bit depth/color + crc filler
    tail = b"\x00\x00\x00\x00IEND\xaeB`\x82"
    return sig + ihdr + salt + tail


def make_jpeg(width: int, height: int, salt: bytes = b"") -> bytes:
    soi = b"\xff\xd8"
    sof = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width)
    sof += b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    return soi + sof + salt + b"\xff\xd9"


@pytest.fixture()
def images_helpers():
    return {"png": make_png, "jpeg": make_jpeg}
