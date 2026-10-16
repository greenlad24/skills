"""Minimal ctypes LV2 host for offline tests of the VibeNation plugins.

Loads <bundle>/<name>.so directly, parses the generated TTL for port indices,
and renders numpy audio block by block, recording control-output ports per block.
Only for our own plugins (no features required).
"""
import ctypes as C
import os
import re
import numpy as np

LV2_DIRS = [os.environ.get("VN_LV2_DIR", "/usr/local/lib/lv2")]


class Desc(C.Structure):
    _fields_ = [("URI", C.c_char_p),
                ("instantiate", C.c_void_p), ("connect_port", C.c_void_p),
                ("activate", C.c_void_p), ("run", C.c_void_p),
                ("deactivate", C.c_void_p), ("cleanup", C.c_void_p),
                ("extension_data", C.c_void_p)]


INST = C.CFUNCTYPE(C.c_void_p, C.POINTER(Desc), C.c_double, C.c_char_p, C.c_void_p)
CONN = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32, C.c_void_p)
ACT = C.CFUNCTYPE(None, C.c_void_p)
RUN = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32)


def parse_ttl(path):
    txt = open(path).read()
    ports = []
    for blk in re.split(r"\n    \] , \[\n|lv2:port \[\n", txt)[1:]:
        idx = int(re.search(r"lv2:index (\d+)", blk).group(1))
        sym = re.search(r'lv2:symbol "([^"]+)"', blk).group(1)
        audio = "lv2:AudioPort" in blk
        out = "lv2:OutputPort" in blk
        m = re.search(r"lv2:default ([-0-9.e]+)", blk)
        dflt = float(m.group(1)) if m else 0.0
        ports.append(dict(index=idx, symbol=sym, audio=audio, output=out, default=dflt))
    return sorted(ports, key=lambda p: p["index"])


class Plugin:
    def __init__(self, name, sr=48000, lv2dir=None):
        d = lv2dir or LV2_DIRS[0]
        self.bundle = os.path.join(d, name + ".lv2")
        self.lib = C.CDLL(os.path.join(self.bundle, name + ".so"))
        self.lib.lv2_descriptor.restype = C.POINTER(Desc)
        self.desc = self.lib.lv2_descriptor(0)
        self.ports = parse_ttl(os.path.join(self.bundle, name + ".ttl"))
        feats = (C.c_void_p * 1)(None)
        inst = INST(self.desc.contents.instantiate)
        self.h = inst(self.desc, float(sr), (self.bundle + "/").encode(), C.cast(feats, C.c_void_p))
        assert self.h, "instantiate failed"
        self._conn = CONN(self.desc.contents.connect_port)
        self._run = RUN(self.desc.contents.run)
        self.ctl = {}
        for p in self.ports:
            if not p["audio"]:
                buf = np.array([p["default"]], dtype=np.float32)
                self.ctl[p["symbol"]] = buf
                self._conn(self.h, p["index"], buf.ctypes.data)
        self.ain = [p for p in self.ports if p["audio"] and not p["output"]]
        self.aout = [p for p in self.ports if p["audio"] and p["output"]]
        ACT(self.desc.contents.activate)(self.h)

    def set(self, **kw):
        for k, v in kw.items():
            self.ctl[k][0] = v

    def outputs(self):
        return [p["symbol"] for p in self.ports if not p["audio"] and p["output"]]

    def process(self, x, block=256):
        """x: (n,) or (n, ch). Returns (y, {outport: per-block values})."""
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 1:
            x = x[:, None]
        if x.shape[1] < len(self.ain):
            x = np.repeat(x[:, :1], len(self.ain), axis=1)
        n = x.shape[0]
        y = np.zeros((n, len(self.aout)), dtype=np.float32)
        ib = [np.zeros(block, np.float32) for _ in self.ain]
        ob = [np.zeros(block, np.float32) for _ in self.aout]
        for p, b in zip(self.ain, ib):
            self._conn(self.h, p["index"], b.ctypes.data)
        for p, b in zip(self.aout, ob):
            self._conn(self.h, p["index"], b.ctypes.data)
        meters = {s: [] for s in self.outputs()}
        for s in range(0, n, block):
            m = min(block, n - s)
            for c, b in enumerate(ib):
                b[:m] = x[s:s + m, c]
            self._run(self.h, m)
            for c, b in enumerate(ob):
                y[s:s + m, c] = b[:m]
            for k in meters:
                meters[k].append(float(self.ctl[k][0]))
        return (y[:, 0] if y.shape[1] == 1 else y), {k: np.array(v) for k, v in meters.items()}
