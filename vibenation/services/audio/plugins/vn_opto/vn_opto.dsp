// vn_opto - LA-2A style optical leveler (T4 cell), VibeNation.
//
// Feedback topology (detector listens to the cell's output, like the real unit),
// so the ratio is soft and program dependent without a ratio law:
//   steady state  out - T = (in - T) / (1 + beta)   beta = 2 (Compress) / 9 (Limit)
// T4 cell: 10 ms attack, two-stage release - half the reduction recovers in
// ~60 ms, the rest over 0.5..5 s depending on how long/hard the cell has been lit
// (a "memory" state that charges in ~2 s and discharges in ~15 s).
// 3-band sidechain emphasis (low shelf 200 Hz, mid bell 1.5 kHz, high shelf 5 kHz).
declare name "vn_opto";
declare vn_name "VN Opto Leveler";
declare vn_class "CompressorPlugin";
declare vn_comment "T4 optical leveler: Peak Reduction, Gain, Mix, 3-band sidechain emphasis. Outputs gain reduction in dB.";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

peak   = hslider("peak_reduction[name:Peak Reduction][unit:%]", 30, 0, 100, 0.1) : vn.psm;
gaindb = hslider("gain[name:Gain][unit:dB]", 0, -20, 30, 0.1) : vn.db2lin : vn.psm;   // linear gain, smoothed (no pow per sample)
mode   = nentry("mode[name:Mode][enum:Compress|Limit]", 0, 0, 1, 1);
sclo   = hslider("sc_low[name:Sidechain Low 200 Hz][unit:dB]", 0, -12, 12, 0.1);
scmid  = hslider("sc_mid[name:Sidechain Mid 1.5 kHz][unit:dB]", 0, -12, 12, 0.1);
schi   = hslider("sc_high[name:Sidechain High 5 kHz][unit:dB]", 0, -12, 12, 0.1);
colour = hslider("colour[name:Tube Colour][unit:%]", 30, 0, 100, 1) / 100 : vn.psm;
mixp   = hslider("mix[name:Mix][unit:%]", 100, 0, 100, 1) : vn.psm;

grmeter = hbargraph("gr[name:Gain Reduction][unit:dB]", 0, 40);

thr  = -6 - 0.45 * peak;                          // dBFS: -6 .. -51
beta = select2(mode, 2.0, 9.0);                   // 3:1-ish / 10:1-ish
knee = select2(mode, 10.0, 6.0);                  // opto knees are wide

// sidechain emphasis EQ (TPT SVF, cramping-free)
sceq = fi.svf.ls(200, 0.6, sclo) : fi.svf.bell(1500, 0.7, scmid) : fi.svf.hs(5000, 0.6, schi);

// level detector: 8 ms RMS blended with a fast peak follower (EL panel response)
det(s) = max(rmsdb, pkdb - 4) with {
  rmsdb = 10 * log10(max(1e-18, s * s : vn.lag(0.008)));
  pkdb  = vn.lin2db(vn.follow(vn.k1(0.0003), vn.k1(0.025), abs(s)));
};

// T4 cell in the dB domain. Input: demanded reduction (dB). Output: actual reduction.
t4(d) = 0.5 * fast + 0.5 * slow
with {
  ka   = vn.k1(0.010);
  memv = vn.follow(vn.k1(2.0), vn.k1(15.0), min(1, d / 12));
  fast = vn.follow(ka, vn.k1(0.060), d);
  slow = vn.follow(vn.k1(0.08), vn.k1(0.5 + 4.5 * memv), fast);
};

// one pass of the loop: x = input, yp = previous output -> new output
cell(x, yp) = x * vn.db2lin(0 - gr)
with {
  over = det(sceq(yp)) - thr;
  gr   = t4(beta * vn.softover(knee, over)) : max(0) : min(40) : grmeter;
};

// output tube/transformer colour: gentle 2nd + 3rd, more with more reduction
tube(y) = y + h * (0.08 * (yc * yc : vn.dcb) - 0.05 * yc * yc * yc)
with {
  yc = max(-1.5, min(1.5, y));
  h  = colour;
};

opto(x) = (cell(x) ~ _) : tube : *(gaindb);

process = _ <: _, opto : (*(1 - mixp/100), *(mixp/100)) :> _;
