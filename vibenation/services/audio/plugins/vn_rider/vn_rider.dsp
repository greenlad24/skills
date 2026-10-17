// vn_rider - vocal rider (automatic fader), VibeNation.
//
// Measures a voice-weighted short-term level (HPF 150 Hz + LPF 5 kHz, 200 ms RMS),
// and rides a gain within +-range toward the target level with a smooth time
// constant. A two-part gate decides when to ride: the level must be above an
// absolute floor AND within 15 dB of the recent singing level (a slowly decaying
// peak memory), so pauses, breaths and drum/bass bleed in the vocal mic never
// pump the gain up - the rider simply holds its last value until the singer is back.
// The current gain is output (dB) so the host/Claude can display it.
declare name "vn_rider";
declare vn_name "VN Vocal Rider";
declare vn_class "DynamicsPlugin";
declare vn_comment "Vocal rider: target, range, speed, gate. Outputs the current riding gain in dB.";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

target = hslider("target[name:Target Level][unit:dB]", -20, -40, 0, 0.1);
range  = hslider("range[name:Range (+-)][unit:dB]", 6, 0, 12, 0.1);
speed  = hslider("speed[name:Speed][unit:ms][log]", 400, 50, 3000, 1);
gate   = hslider("gate[name:Gate Floor][unit:dB]", -50, -80, -20, 0.5);
outdb  = hslider("output[name:Output][unit:dB]", 0, -12, 12, 0.1) : vn.db2lin : vn.psm;   // linear gain, smoothed (no pow per sample)
gmeter = hbargraph("gain[name:Riding Gain][unit:dB]", -12, 12);

// voice-weighted level, dBFS RMS
lvlt(t, x) = 10 * log10(max(1e-14, x : fi.highpass(2, 150) : fi.lowpass(2, 5000) <: * : vn.lag(t))) + 3;
lvl = lvlt(0.2);

// recent singing level: instant attack, falls 3 dB/s
peakmem(l) = loop ~ _ with { loop(s) = max(l, s - 3 / ma.SR); };

ride(x) = (step ~ _) : max(0 - range) : min(range) : gmeter
with {
  l    = lvl(x);
  lf   = lvlt(0.02, x);                        // fast level: closes the gate the moment the phrase ends
  open = (lf > gate) & (lf > peakmem(l) - 15) & (l > gate);
  want = max(0 - range, min(range, target - l));
  k    = vn.k1(speed * 0.001) * open;          // hold the gain while the gate is closed
  step(s) = s + (want - s) * k;
};

process(x) = x * vn.db2lin(ride(x) : vn.lag(0.01)) * outdb;
