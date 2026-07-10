"""DSP: front-end features, vocal-in-mix detection, calibration."""

from .frontend import Frontend, HopFeatures, NEG_INF_DB
from .vocal import (CalibrationResult, Calibrator, PitchPrior, VocalPresence)

__all__ = ["Frontend", "HopFeatures", "NEG_INF_DB", "CalibrationResult",
           "Calibrator", "PitchPrior", "VocalPresence"]
