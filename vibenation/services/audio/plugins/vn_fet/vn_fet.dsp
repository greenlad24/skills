// vn_fet - 1176 style FET compressor/limiter, VibeNation.
//
// Feedback topology like the hardware: the peak detector listens to the FET
// cell's output, so the ratio buttons set the loop gain (beta = ratio - 1) and
// the knee/overshoot come out of the loop. Fixed threshold; INPUT drives into it.
// Release is program dependent: two RC paths (fast = knob, slow = 5x knob) with
// the slow share growing with the knob, as in the hardware's detector network.
// FET colour: the gain cell's distortion grows with the amount of reduction
// (channel-resistance modulation, 2nd + 3rd), followed by a class-A output stage.
// Runs 2x oversampled (polyphase IIR half-band in the wrapper).
declare name "vn_fet";
declare vn_name "VN FET Compressor";
declare vn_class "CompressorPlugin";
declare vn_comment "1176-style FET compressor: input, output, ratio 4/8/12/20/all, attack 20-800 us, release 50-1100 ms, colour, mix. Outputs gain reduction in dB.";
declare vn_oversample "2";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

indb    = hslider("input[name:Input][unit:dB]", 0, -20, 40, 0.1) : vn.psm;
outdb   = hslider("output[name:Output][unit:dB]", 0, -30, 20, 0.1) : vn.psm;
ratio   = nentry("ratio[name:Ratio][enum:4:1|8:1|12:1|20:1|All]", 0, 0, 4, 1);
atk_us  = hslider("attack[name:Attack][unit:us][log]", 300, 20, 800, 1);
rel_ms  = hslider("release[name:Release][unit:ms][log]", 300, 50, 1100, 1);
colour  = hslider("colour[name:Colour][unit:%]", 50, 0, 100, 1) / 100 : vn.psm;
mixp    = hslider("mix[name:Mix][unit:%]", 100, 0, 100, 1) : vn.psm;

grmeter = hbargraph("gr[name:Gain Reduction][unit:dB]", 0, 40);

allb  = ratio == 4;
// loop gain and threshold per button (higher ratio -> higher threshold, as on the unit)
beta  = ba.selectn(5, ratio, 3, 7, 11, 19, 30);
thr   = ba.selectn(5, ratio, -20, -19, -18.5, -18, -18);
knee  = ba.selectn(5, ratio, 6, 4, 3, 2, 1);
// all-buttons: faster, more aggressive detector, longer recovery and extra grit
atk   = atk_us * 1e-6 * select2(allb, 1, 0.5);
relf  = rel_ms * 1e-3 * select2(allb, 1, 0.8);
w     = 0.2 + 0.25 * (rel_ms - 50) / 1050;      // slow-path share 0.2..0.45

// rectified cell output (one sample behind: transients overshoot)
lvl(y) = vn.lin2db(abs(y));   // full-wave rectifier straight into the timing network

// dual-RC smoothing of the demanded reduction (dB)
rc(d) = (1 - w) * f + w * s
with {
  ka = vn.k1(atk * (1 + beta));   // knob = closed-loop attack time
  f  = vn.follow(ka, vn.k1(relf), d);
  s  = vn.follow(ka, vn.k1(5 * relf), d);
};

// FET gain cell: gain g plus reduction-dependent channel modulation
fetcell(x, g) = x * g / (1 + m * (0.25 * xs + 0.6 * xs * xs * xs))
with {
  work = min(1, 1 - g + 0.04);
  m    = colour * select2(allb, 0.06, 0.12) * work;
  xs   = x / (1 + abs(x));
};

loop(yp, x) = fetcell(x, g)
with {
  over = lvl(yp) - thr;
  gr   = rc(beta * vn.softover(knee, over)) : max(0) : min(40) : grmeter;
  g    = vn.db2lin(0 - gr);
};

// class-A output amp: asymmetric soft saturation (2nd harmonic), DC-blocked
classA(y) = y + colour * 0.12 * (((y : max(-2) : min(2)) <: *) : vn.dcb) * (-0.5) : tanhsafe
with { tanhsafe(v) = v / (1 + 0.02 * colour * v * v); };

fet(x) = x * vn.db2lin(indb) : (loop ~ _) : classA : *(vn.db2lin(outdb));

process = _ <: _, fet : (*(1 - mixp/100), *(mixp/100)) :> _;
