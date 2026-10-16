#!/usr/bin/env python3
"""Polyphase IIR half-band designer (elliptic, after L. de Soras' hiir algorithm).
Prints C coefficient arrays for vn_os.h. Usage: halfband_design.py NCOEFS TRANSITION"""
import math, sys

def transition_param(tbw):
    k = math.tan((1 - tbw * 2) * math.pi / 4) ** 2
    kksqrt = (1 - k * k) ** 0.25
    e = 0.5 * (1 - kksqrt) / (1 + kksqrt)
    e2 = e * e; e4 = e2 * e2
    q = e * (1 + e4 * (2 + e4 * (15 + 150 * e4)))
    return k, q

def acc_num(q, order, c):
    i, j, acc = 0, 1, 0.0
    while True:
        t = q ** (i * (i + 1)) * math.sin((i * 2 + 1) * c * math.pi / order) * j
        acc += t; j = -j; i += 1
        if abs(t) <= 1e-100: return acc

def acc_den(q, order, c):
    i, j, acc = 1, -1, 0.0
    while True:
        t = q ** (i * i) * math.cos(i * 2 * c * math.pi / order) * j
        acc += t; j = -j; i += 1
        if abs(t) <= 1e-100: return acc

def coefs(n, tbw):
    k, q = transition_param(tbw)
    order = n * 2 + 1
    out = []
    for idx in range(n):
        c = idx + 1
        num = acc_num(q, order, c) * q ** 0.25
        den = acc_den(q, order, c) + 0.5
        ww = num / den; wwsq = ww * ww
        x = math.sqrt((1 - wwsq * k) * (1 - wwsq / k)) / (1 + wwsq)
        out.append((1 - x) / (1 + x))
    return out

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    t = float(sys.argv[2]) if len(sys.argv) > 2 else 0.04
    print(", ".join("%.17g" % c for c in coefs(n, t)))
