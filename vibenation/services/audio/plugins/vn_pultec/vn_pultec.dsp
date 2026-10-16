// vn_pultec - Pultec EQP-1A style program equalizer, VibeNation.
//
// Low section: 2nd-order low shelf boost (Q 0.6, midpoint 2x CPS, up to +13.5 dB)
// and 1st-order low shelf atten (midpoint 4x CPS, up to -17.5 dB). The passive
// network's interaction is modelled explicitly: with boost engaged, part of the
// atten is restored below CPS, which gives the famous "boost + atten" curve
// (60 Hz both at 10: about +7 dB at 30 Hz, -5 dB dip near 200 Hz).
// High section: bell boost 3-16 kHz with bandwidth (Q 2.5 sharp .. 0.4 broad,
// up to +16 dB) and 1st-order high shelf atten at 5/10/20 kHz (up to -16 dB).
// Runs 2x oversampled, so the 12/16 kHz bells keep their analog shape (no
// bilinear cramping at 48 kHz) and the tube stage stays alias-free.
declare name "vn_pultec";
declare vn_name "VN Program EQ (EQP-1A style)";
declare vn_class "EQPlugin";
declare vn_comment "Pultec EQP-1A style passive EQ with tube makeup stage. Outputs the net program gain change in dB.";
declare vn_oversample "2";
declare license "MIT";

import("stdfaust.lib");
vn = library("vn.lib");

lfsel  = nentry("low_freq[name:Low Frequency][enum:20 Hz|30 Hz|60 Hz|100 Hz]", 2, 0, 3, 1);
lboost = hslider("low_boost[name:Low Boost][unit:x]", 0, 0, 10, 0.1) : vn.psm;
latten = hslider("low_atten[name:Low Atten][unit:x]", 0, 0, 10, 0.1) : vn.psm;
hfsel  = nentry("high_freq[name:High Boost Frequency][enum:3 kHz|4 kHz|5 kHz|8 kHz|10 kHz|12 kHz|16 kHz]", 3, 0, 6, 1);
hboost = hslider("high_boost[name:High Boost][unit:x]", 0, 0, 10, 0.1) : vn.psm;
hbw    = hslider("high_bw[name:High Bandwidth (sharp-broad)][unit:x]", 5, 0, 10, 0.1) : vn.psm;
hasel  = nentry("atten_freq[name:High Atten Frequency][enum:5 kHz|10 kHz|20 kHz]", 1, 0, 2, 1);
hatten = hslider("high_atten[name:High Atten][unit:x]", 0, 0, 10, 0.1) : vn.psm;
tube   = hslider("tube[name:Tube Drive][unit:%]", 30, 0, 100, 1) / 100 : vn.psm;
outdb  = hslider("output[name:Output][unit:dB]", 0, -12, 12, 0.1) : vn.psm;

gmeter = hbargraph("gain_change[name:Program Gain Change][unit:dB]", -24, 24);

cps  = ba.selectn(4, lfsel, 20, 30, 60, 100);
hf   = ba.selectn(7, hfsel, 3000, 4000, 5000, 8000, 10000, 12000, 16000);
haf  = ba.selectn(3, hasel, 5000, 10000, 20000);

gb   = 1.35 * lboost;                 // dB
ga   = 1.75 * latten;                 // dB
ghb  = 1.6 * hboost;                  // dB
gha  = 1.6 * hatten;                  // dB
qhb  = 2.5 * pow(0.4 / 2.5, hbw / 10);

// 1st-order shelves (TPT one-pole), gain g in dB, f = geometric midpoint
lshelf1(f, g, x) = x + (G - 1) * (x : fi.lowpass(1, f / sqrt(G))) with { G = vn.db2lin(g); };
hshelf1(f, g, x) = x + (G - 1) * (x : fi.highpass(1, min(f * sqrt(G), 40000))) with { G = vn.db2lin(g); };

lowsec  = fi.svf.ls(2 * cps, 0.6, gb) : lshelf1(4 * cps, 0 - ga) : lshelf1(cps, 0.85 * ga * gb / 13.5);
highsec = fi.svf.bell(hf, qhb, ghb) : hshelf1(haf, 0 - gha);

// tube makeup amp (12AX7 + 12AU7): asymmetric, mostly 2nd harmonic, level dependent
tubestage(x) = x + tube * (0.10 * (xc * xc : vn.dcb) - 0.04 * xc * xc * xc)
with { xc = max(-1.5, min(1.5, x)); };

eq = lowsec : highsec : tubestage : *(vn.db2lin(outdb));

// program gain change meter (300 ms RMS out/in)
meter(x, y) = y : attach(_, (10 * log10(max(1e-12, y*y : vn.lag(0.3))) - 10 * log10(max(1e-12, x*x : vn.lag(0.3)))) * (x*x : vn.lag(0.3) > 1e-9) : gmeter);

process = _ <: _, eq : meter;
