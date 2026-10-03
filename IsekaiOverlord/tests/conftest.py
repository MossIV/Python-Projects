"""Shared test setup: put ``src`` on the path and locate fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_image(name: str) -> Path:
    return FIXTURES / f"{name}.png"


@pytest.fixture(scope="session")
def ocr_engine():
    """One RapidOCR instance for the whole session — model load is slow."""
    from iwol import Ocr

    return Ocr()


@pytest.fixture
def sample_frame():
    """A small synthetic frame, so most tests never touch a real screenshot."""
    import numpy as np

    from iwol import Frame

    img = np.zeros((120, 200, 3), dtype=np.uint8)
    img[:, :] = (40, 40, 40)
    img[20:40, 30:90] = (200, 180, 60)  # a bright "button"
    return Frame(img, (0, 0))
