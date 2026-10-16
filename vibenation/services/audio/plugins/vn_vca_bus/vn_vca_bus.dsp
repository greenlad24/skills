// vn_vca_bus - SSL G-series style stereo bus compressor, VibeNation.
//
// Feed-forward VCA design, linked stereo detector (max of |L|,|R| after the
// sidechain HPF), log-domain gain computer with a small soft knee, attack and
// release smoothing in the dB domain (VCA = exponential gain law).
// AUTO release = the classic dual-RC network: a fast path (0.1 s) plus a slow
// path (1.2 s) that only charges during sustained compression, so transients
// recover fast and dense passages recover slowly (no pumping).
declare name "vn_vca_bus";
declare vn_name "VN VCA Bus Compressor";
declare vn_class "CompressorPlugin";
declare vn_comment "SSL-style stereo bus compressor: threshold, ratio 2/4/10, attack 0.1-30 ms, release 0.1-1.2 s or auto, sidechain HPF, makeup, mix. Outputs gain reduction in dB.";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

thr     = hslider("threshold[name:Threshold][unit:dB]", -12, -40, 0, 0.1) : vn.psm;
ratio   = nentry("ratio[name:Ratio][enum:2:1|4:1|10:1]", 1, 0, 2, 1);
atk_ms  = hslider("attack[name:Attack][unit:ms][log]", 10, 0.1, 30, 0.01);
relsel  = nentry("release[name:Release][enum:0.1 s|0.3 s|0.6 s|1.2 s|Auto]", 4, 0, 4, 1);
schpf   = hslider("sc_hpf[name:Sidechain HPF (0 = off)][unit:Hz]", 0, 0, 300, 1);
makeup  = hslider("makeup[name:Makeup][unit:dB]", 0, 0, 20, 0.1) : vn.psm;
mixp    = hslider("mix[name:Mix][unit:%]", 100, 0, 100, 1) : vn.psm;

grmeter = hbargraph("gr[name:Gain Reduction][unit:dB]", 0, 30);

slope = 1 - 1 / ba.selectn(3, ratio, 2, 4, 10);
knee  = 4;
auto  = relsel == 4;
relt  = ba.selectn(5, relsel, 0.1, 0.3, 0.6, 1.2, 0.1);

// sidechain: 2nd-order HPF (bypassed at 0 Hz), linked peak rectifier, 0.3 ms smoothing
hp(x)  = select2(schpf > 1, x, x : fi.highpass(2, max(schpf, 10)));
det(l, r) = max(abs(hp(l)), abs(hp(r))) : vn.follow(1, vn.k1(0.0003)) : vn.lin2db;

// gain computer (dB of reduction)
gc(lv) = slope * vn.softover(knee, lv - thr);

// attack / release in the dB domain, with the dual-RC auto release
smooth(d) = select2(auto, fixed, max(fastp, slowp))
with {
  ka    = vn.k1(atk_ms * 0.001);
  fixed = vn.follow(ka, vn.k1(relt), d);
  fastp = vn.follow(ka, vn.k1(0.1), d);
  slowp = vn.follow(vn.k1(0.35), vn.k1(1.2), fastp);
};

gr(l, r) = det(l, r) : gc : smooth : max(0) : min(30) : grmeter;

process(l, r) = l * mw + l * g * ww, r * mw + r * g * ww
with {
  g  = vn.db2lin(makeup - gr(l, r));
  ww = mixp / 100;
  mw = 1 - ww;
};
