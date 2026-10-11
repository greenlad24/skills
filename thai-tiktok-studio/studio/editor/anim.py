"""CapCut-style animation curves. All times in seconds (local to the element)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PIL import Image


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out_cubic(x):
    x = clamp01(x)
    return 1 - (1 - x) ** 3


def ease_in_cubic(x):
    x = clamp01(x)
    return x ** 3


def ease_out_back(x, s=1.70158):
    x = clamp01(x) - 1
    return x * x * ((s + 1) * x + s) + 1


@dataclass
class Element:
    start: float
    end: float
    cx: float
    cy: float
    sprite: Image.Image | None = None
    draw: object = None            # callable(t_local) -> Image (dynamic elements)
    anim_in: str = "pop"           # pop | stamp | slide_left | slide_right | slide_down | slide_up | fade | caption | none
    in_dur: float = 0.3
    loop: str = ""                 # pulse | wiggle | bob | blink | spin_slow | ""
    loop_amp: float = 1.0
    out: str = "fade"              # fade | none
    out_dur: float = 0.15
    rot: float = 0.0               # static rotation (degrees)
    z: int = 0
    bob_dir: tuple = (0.0, 1.0)
    tags: dict = field(default_factory=dict)

    def active(self, t: float) -> bool:
        return self.start <= t < self.end

    def is_static_at(self, t: float) -> bool:
        lt = t - self.start
        return (self.draw is None and not self.loop and lt >= self.in_dur
                and (self.out == "none" or t < self.end - self.out_dur))

    def state(self, t: float):
        """→ (scale, dx, dy, rotation_deg, alpha)"""
        lt = t - self.start
        s, dx, dy, r, a = 1.0, 0.0, 0.0, self.rot, 1.0
        p = lt / self.in_dur if self.in_dur > 0 else 1.0
        if p < 1:
            if self.anim_in == "pop":
                s = max(0.01, ease_out_back(p, 2.2))
                a = clamp01(p * 3)
            elif self.anim_in == "caption":
                s = 0.82 + 0.18 * ease_out_back(p, 2.0)
                a = clamp01(p * 4)
            elif self.anim_in == "stamp":
                s = 1.7 - 0.7 * ease_out_back(p, 1.4)
                r = self.rot - 9 * (1 - ease_out_cubic(p))
                a = clamp01(p * 3)
            elif self.anim_in.startswith("slide"):
                e = ease_out_cubic(p)
                off = (1 - e) * 140
                dx = {"slide_left": -off, "slide_right": off}.get(self.anim_in, 0.0)
                dy = {"slide_down": -off, "slide_up": off}.get(self.anim_in, 0.0)
                a = clamp01(p * 2.5)
            elif self.anim_in == "fade":
                a = p
        elif self.anim_in == "stamp" and lt < self.in_dur + 0.18:  # post-stamp shake
            k = 1 - (lt - self.in_dur) / 0.18
            dx = math.sin(lt * 95) * 10 * k
        if self.loop and p >= 1:
            ph = lt - self.in_dur
            amp = self.loop_amp
            if self.loop == "pulse":
                s *= 1 + 0.06 * amp * (0.5 - 0.5 * math.cos(ph * 2 * math.pi / 0.7))
            elif self.loop == "wiggle":
                r += 5 * amp * math.sin(ph * 2 * math.pi / 0.5)
            elif self.loop == "bob":
                k = 14 * amp * (0.5 - 0.5 * math.cos(ph * 2 * math.pi / 0.6))
                dx += self.bob_dir[0] * k
                dy += self.bob_dir[1] * k
            elif self.loop == "blink":
                a *= 0.55 + 0.45 * (0.5 + 0.5 * math.cos(ph * 2 * math.pi / 0.5))
            elif self.loop == "spin_slow":
                r += ph * 25
        if self.out == "fade" and t > self.end - self.out_dur:
            q = clamp01((self.end - t) / self.out_dur)
            a *= q
            s *= 0.9 + 0.1 * q
        return s, dx, dy, r, a


def render_element(el: Element, t: float):
    """→ (image, x, y) top-left placement on the canvas, or None."""
    img = el.draw(t - el.start) if el.draw else el.sprite
    if img is None:
        return None
    s, dx, dy, r, a = el.state(t)
    if a <= 0.01 or s <= 0.02:
        return None
    if abs(s - 1) > 0.004:
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BILINEAR)
    if abs(r) > 0.2:
        img = img.rotate(r, resample=Image.BICUBIC, expand=True)
    if a < 0.995:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    x = int(el.cx + dx - img.width / 2)
    y = int(el.cy + dy - img.height / 2)
    return img, x, y
