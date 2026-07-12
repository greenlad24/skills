"""Mackie Control (MCU) emulation: how AutoDirector moves Studio One's
faders.

Two virtual MIDI ports are exposed — "AutoDirector MCU 1" (channels
1-8) and "AutoDirector MCU 2" (channels 9-16). In Studio One, add
External Devices: a "Mackie Control" bound to port 1 and a "Mackie
Control XT" bound to port 2. No bank switching, 16 dedicated fader
strips.

Fader positions are MIDI pitch-bend messages (14-bit, one per strip).
We work RELATIVELY around a soundcheck snapshot: Studio One echoes
fader positions to the surface, we record them at snapshot time, and
apply bounded dB deltas using a local taper slope. That sidesteps
absolute-taper mismatches — a ±6 dB ride around a known position is
accurate to a fraction of a dB.

Safety: this module only ever moves faders through MixRails (clamped,
slewed). If AutoDirector exits, faders simply stay where they are —
Studio One is never left in a weird state.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional

log = logging.getLogger("autodirector.mcu")

FADER_MAX = 16383
# Near unity gain the Mackie taper is ~ linear; empirically ≈ 170
# position units per dB. Only used for RELATIVE moves within ±6 dB.
UNITS_PER_DB = 170.0
STRIPS_PER_PORT = 8


MCU_LCD_SYSEX = [0xF0, 0x00, 0x00, 0x66]  # Mackie header; 0x14=MCU, 0x12=LCD


def parse_lcd_sysex(msg) -> Optional[tuple]:
    """Parse an MCU LCD sysex (how the DAW writes channel names to the
    surface's scribble strips). Returns (offset, text) or None.
    Layout: F0 00 00 66 dd 12 <offset> <ascii...> F7 — the top LCD line
    is offsets 0-55, 7 characters per strip."""
    if len(msg) < 8 or msg[:4] != MCU_LCD_SYSEX or msg[5] != 0x12:
        return None
    offset = msg[6]
    text = "".join(chr(b) for b in msg[7:-1] if 32 <= b < 127)
    return offset, text


class MidiPort:
    """Real virtual-MIDI port pair (python-rtmidi). Optional dependency —
    the Mix Engineer degrades to analysis-only without it."""

    def __init__(self, name: str, on_pitchbend: Callable[[int, int], None],
                 on_lcd: Optional[Callable[[int, str], None]] = None):
        import rtmidi  # type: ignore
        self._out = rtmidi.MidiOut()
        self._in = rtmidi.MidiIn()
        try:
            # macOS/Linux: create our own virtual ports.
            self._out.open_virtual_port(name)
            self._in.open_virtual_port(name)
        except NotImplementedError:
            # Windows: the OS cannot create virtual MIDI ports. The user
            # creates ports with these names in loopMIDI (free) and we
            # attach to them instead.
            self._open_named(name)
        self._in.ignore_types(sysex=False)  # we want LCD name sysex
        self._on_pb = on_pitchbend
        self._on_lcd = on_lcd
        self._in.set_callback(self._cb)

    def _open_named(self, name: str) -> None:
        low = name.lower()
        outs = self._out.get_ports()
        ins = self._in.get_ports()
        oi = next((i for i, p in enumerate(outs) if low in p.lower()), None)
        ii = next((i for i, p in enumerate(ins) if low in p.lower()), None)
        if oi is None or ii is None:
            raise RuntimeError(
                f"MIDI port '{name}' not found. On Windows, create ports "
                f"named 'AutoDirector MCU 1' and 'AutoDirector MCU 2' in "
                f"loopMIDI (free), then restart AutoDirector.")
        self._out.open_port(oi)
        self._in.open_port(ii)
        # Note: loopMIDI ports are loopbacks, so we also hear our own
        # fader messages back — harmless: the positions we 'hear' are the
        # positions we set.

    def _cb(self, event, _data=None):
        msg, _dt = event
        status = msg[0] & 0xF0
        if status == 0xE0 and len(msg) >= 3:  # pitch bend = fader echo
            strip = msg[0] & 0x0F
            value = (msg[2] << 7) | msg[1]
            self._on_pb(strip, value)
        elif msg[0] == 0xF0 and self._on_lcd:
            parsed = parse_lcd_sysex(msg)
            if parsed:
                self._on_lcd(*parsed)

    def send_pitchbend(self, strip: int, value: int) -> None:
        value = max(0, min(FADER_MAX, int(value)))
        self._out.send_message([0xE0 | (strip & 0x0F),
                                value & 0x7F, (value >> 7) & 0x7F])

    def close(self):
        try:
            self._in.close_port()
            self._out.close_port()
        except Exception:
            pass


class MCUFaders:
    """16 fader strips across two MCU ports, relative-move API.

    port_factory(name, on_pitchbend) -> port  is injectable for tests.
    """

    def __init__(self, n_channels: int = 16,
                 port_factory: Optional[Callable] = None,
                 port_prefix: str = "AutoDirector MCU"):
        self.n = n_channels
        self.available = False
        self.positions: List[Optional[int]] = [None] * n_channels
        self.baseline: List[Optional[int]] = [None] * n_channels
        self.names: List[Optional[str]] = [None] * n_channels
        self._lock = threading.Lock()
        self._ports = []
        factory = port_factory or MidiPort
        n_ports = (n_channels + STRIPS_PER_PORT - 1) // STRIPS_PER_PORT
        try:
            for p in range(n_ports):
                offset = p * STRIPS_PER_PORT

                def on_pb(strip, value, off=offset):
                    self._note_position(off + strip, value)

                def on_lcd(text_offset, text, off=offset):
                    self._note_lcd(off, text_offset, text)

                self._ports.append(factory(f"{port_prefix} {p + 1}",
                                           on_pb, on_lcd))
            self.available = True
        except Exception as e:
            log.warning("MCU ports unavailable (%s) — mix control disabled, "
                        "analysis continues", e)

    # ------------------------------------------------------------------
    def _note_position(self, ch: int, value: int) -> None:
        if 0 <= ch < self.n:
            with self._lock:
                self.positions[ch] = value

    def _note_lcd(self, port_offset: int, text_offset: int,
                  text: str) -> None:
        """Scribble-strip text -> channel names. The top LCD line holds
        7 chars per strip; the DAW rewrites it with track names."""
        if text_offset >= 56:  # bottom line: values, not names
            return
        with self._lock:
            for strip in range(STRIPS_PER_PORT):
                cell_start = strip * 7
                cell_end = cell_start + 7
                if text_offset < cell_end and \
                        text_offset + len(text) > cell_start:
                    s = max(0, cell_start - text_offset)
                    e = min(len(text), cell_end - text_offset)
                    cell = text[s:e].strip()
                    ch = port_offset + strip
                    if cell and ch < self.n:
                        self.names[ch] = cell

    def heard_from_daw(self) -> bool:
        """True once Studio One has echoed at least one fader position —
        the setup UI asks the user to wiggle a fader to confirm wiring."""
        return any(p is not None for p in self.positions)

    def snapshot_baseline(self) -> int:
        """Capture current fader positions as the soundcheck baseline.
        Channels never heard from default to fader center (0 dB moves
        still work relatively). Returns how many were actually heard."""
        heard = 0
        with self._lock:
            for ch in range(self.n):
                if self.positions[ch] is not None:
                    self.baseline[ch] = self.positions[ch]
                    heard += 1
                elif self.baseline[ch] is None:
                    self.baseline[ch] = FADER_MAX * 3 // 4  # ~unity region
        return heard

    def set_rel_db(self, ch: int, rel_db: float) -> bool:
        """Move channel ch's fader to baseline + rel_db (already railed
        by the caller). No-op when MIDI is unavailable."""
        if not self.available or not (0 <= ch < self.n):
            return False
        base = self.baseline[ch]
        if base is None:
            return False
        pos = max(0, min(FADER_MAX, int(base + rel_db * UNITS_PER_DB)))
        port = self._ports[ch // STRIPS_PER_PORT]
        port.send_pitchbend(ch % STRIPS_PER_PORT, pos)
        with self._lock:
            self.positions[ch] = pos
        return True

    def close(self) -> None:
        for p in self._ports:
            p.close()
