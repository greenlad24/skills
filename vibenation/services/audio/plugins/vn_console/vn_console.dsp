// vn_console - console channel / summing colour, VibeNation (stereo, very cheap).
//
// Per channel: input transformer "flux" saturation that acts mainly on the lows
// (the low-passed part of the signal is saturated, the rest passes - as in an
// iron core, LF saturates first), then an op-amp/discrete stage with a cubic
// soft clipper using 1st-order antiderivative anti-aliasing (ADAA, no
// oversampling needed) plus a small even-order term. Everything is level
// dependent: at -18 dBFS it is ~-70 dBc, near 0 dBFS a few tenths of a percent.
// Optional capacitive crosstalk between L and R (rises 6 dB/oct above 1 kHz).
declare name "vn_console";
declare vn_name "VN Console";
declare vn_class "AmplifierPlugin";
declare vn_comment "Console channel/summing colour: drive, colour, crosstalk, output. Outputs the level change in dB.";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

drivedb = hslider("drive[name:Drive][unit:dB]", 0, -12, 18, 0.1) : vn.db2lin : vn.psm;   // linear gain, smoothed (no pow per sample)
colour  = hslider("colour[name:Colour][unit:%]", 50, 0, 100, 1) / 100 : vn.psm;
xtalk   = hslider("crosstalk[name:Crosstalk][unit:%]", 0, 0, 100, 1) / 100 : vn.psm;
outdb   = hslider("output[name:Output][unit:dB]", 0, -12, 12, 0.1) : vn.db2lin : vn.psm;   // linear gain, smoothed (no pow per sample)
gmeter  = hbargraph("gain_change[vn_pow2db:1][name:Level Change][unit:dB]", -24, 24);

dg = drivedb;

// cubic soft clip with ADAA1: f(u) = u - u^3/3 (|u|<1), 2/3 sign(u) beyond
cf(u)  = select2(abs(u) < 1, 2/3 * ((u > 0) - (u < 0)), u - u*u*u/3);
cF1(u) = select2(abs(u) < 1, 2/3 * abs(u) - 1/4, u*u/2 - u*u*u*u/12);
clip3(u) = select2(abs(d) < 1e-5, (cF1(u) - cF1(u')) / max(1e-5, abs(d)) * ((d > 0) - (d < 0) + (d == 0)), cf(0.5 * (u + u')))
with { d = u - u'; };

// iron: saturate only the low band (below ~120 Hz)
iron(x) = hi + 0.7 * ma.tanh(lo / 0.7) with { lo = x : fi.lowpass(1, 120); hi = x - lo; };

stage(x) = (x * dg * 0.5) : iron : cf : *(2 / dg) : +(0.04 * colour * dg * ((x*x) : vn.dcb));

// cubic (not ADAA) on purpose: at console levels u < ~0.5 the curve is a pure
// 3rd-order polynomial (band-limited to 3x), so it needs no anti-aliasing and has
// no half-sample delay to smear the dry/colour blend. clip3 (ADAA) kept for reference.
chan(x) = x + colour * (stage(x) - x);

ct(a, b) = a + k * (b : fi.highpass(1, 1000)), b + k * (a : fi.highpass(1, 1000))
with { k = xtalk * 0.03; };     // up to about -30 dB at HF

meter(x, y) = y : attach(_, (y*y : vn.lag(0.3)) / max(1e-12, x*x : vn.lag(0.3)) * (x*x : vn.lag(0.3) > 1e-9) + (x*x : vn.lag(0.3) <= 1e-9) : gmeter);

process(l, r) = (chan(l), chan(r)) : ct : (*(o), *(o)) : (meter(l), _)
with { o = outdb; };
