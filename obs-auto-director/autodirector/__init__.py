"""AutoDirector — an automatic scene director for OBS Studio on macOS.

v2 architecture: a standalone app that captures audio itself, analyzes it
(DSP + local classifier), directs scene changes through a relaxed
evidence-based switcher, and drives OBS over obs-websocket v5 — including
an adaptive per-speaker voice chain (expander/compressor/EQ) with an
optional AI review loop.

See docs/ARCHITECTURE.md for the full design and docs/TEAM_REVIEW_SYNTHESIS.md
for the engineering review that produced it.
"""

__version__ = "2.0.0.dev0"
