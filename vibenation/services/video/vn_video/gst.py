"""GStreamer bootstrap + small helpers shared by the pipelines."""
from __future__ import annotations

import gi

gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GstVideo  # noqa: E402

Gst.init(None)

__all__ = ['Gst', 'GstApp', 'GstVideo', 'CLOCK', 'set_prop', 'abs_time', 'has']

# Every pipeline runs on the same monotonic system clock, so timestamps from the video,
# audio and output pipelines can be compared as "absolute" clock times
# (running time + that pipeline's base time).
CLOCK = Gst.SystemClock.obtain()


def has(factory: str) -> bool:
    return Gst.ElementFactory.find(factory) is not None


def set_prop(el: Gst.Element, name: str, value) -> bool:
    """Set a property if the element has it; strings go through GStreamer's parser (enums)."""
    if el.find_property(name) is None:
        return False
    try:
        if isinstance(value, str):
            Gst.util_set_object_arg(el, name, value)
        else:
            el.set_property(name, value)
        return True
    except Exception:  # noqa: BLE001
        return False


def abs_time(sample: Gst.Sample, pipeline: Gst.Pipeline) -> int | None:
    """Clock time at which this sample's buffer is due (ns)."""
    buf = sample.get_buffer()
    ts = buf.pts if buf.pts != Gst.CLOCK_TIME_NONE else buf.dts
    if ts == Gst.CLOCK_TIME_NONE:
        return None
    seg = sample.get_segment()
    rt = seg.to_running_time(Gst.Format.TIME, ts) if seg else ts
    if rt == Gst.CLOCK_TIME_NONE or rt < 0:
        return None
    return rt + pipeline.get_base_time()
