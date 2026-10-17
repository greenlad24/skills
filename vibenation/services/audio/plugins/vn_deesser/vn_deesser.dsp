// vn_deesser - split-band de-esser with relative detection, VibeNation.
//
// Detector: band-pass around the chosen frequency (5-9 kHz typical) compared
// with the full-band level, so the de-esser reacts to how *sibilant* a moment is,
// not how loud the singer is - no threshold re-tuning when the vocal level moves
// (important for automatic mixing). An absolute floor ignores hiss/bleed.
// Processing (split mode): a dynamic TPT-SVF bell centred on the detector
// frequency whose cut follows the gain reduction - exactly 0 dB at rest, phase
// coherent with the dry signal (a naive "x - (1-g)*HPF(x)" split does NOT cut
// the band because of the HPF phase shift - we measured that first).
// Wide mode turns down the whole signal instead.
declare name "vn_deesser";
declare vn_name "VN De-esser";
declare vn_class "DynamicsPlugin";
declare vn_comment "Split-band de-esser: frequency, sensitivity, max reduction, split/wide, listen. Outputs gain reduction in dB.";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

freq   = hslider("freq[name:Frequency][unit:Hz][log]", 6500, 3000, 12000, 1) : vn.psm;
sens   = hslider("sensitivity[name:Sensitivity][unit:%]", 50, 0, 100, 1) : vn.psm;
range  = hslider("range[name:Max Reduction][unit:dB]", 8, 0, 24, 0.1) : vn.psm;
wide   = nentry("mode[name:Mode][enum:Split|Wide]", 0, 0, 1, 1);
listen = checkbox("listen[name:Listen (detector band)]");
floor_ = hslider("floor[name:Detector Floor][unit:dB]", -50, -80, -20, 1);
grmeter = hbargraph("gr[name:Gain Reduction][unit:dB]", 0, 24);

thr = -2 - 0.18 * sens;     // band-to-full ratio threshold: -2 dB (0%) .. -20 dB (100%)

band(x) = x : fi.svf.bp(freq, 1.4);
pw(t, s) = s * s : vn.lag(t);

gr(x) = select2(active, 0, d) : vn.follow(vn.k1(0.0005), vn.k1(0.06)) : min(range) : grmeter
with {
  eb  = pw(0.003, band(x));
  ef  = pw(0.010, x : fi.highpass(1, 120));
  rel = 10 * log10(max(1e-14, eb)) - 10 * log10(max(1e-14, ef));
  active = 10 * log10(max(1e-14, eb)) > floor_;
  d   = max(0, 2 * (rel - thr));              // 3:1-ish above the relative threshold
};

process(x) = select2(listen, out, band(x))
with {
  g    = vn.db2lin(0 - gr(x));
  out  = select2(wide, x : fi.svf.bell(freq, 0.9, 0 - gr(x)), x * g);
};
