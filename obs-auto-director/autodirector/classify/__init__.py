"""Local audio classification (optional YAMNet-class tagger)."""

from .tagger import AudioTagger, TagScores, fuse_vocal_confidence

__all__ = ["AudioTagger", "TagScores", "fuse_vocal_confidence"]
