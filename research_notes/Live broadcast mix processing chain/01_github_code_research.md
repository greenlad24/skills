# GitHub code research: analog emulations, auto-mix, metering, UI (2026-10-16)

Read by a research agent from shallow clones (kept on the build server in /root/vn-tools/research/).

## Analog emulation plugins verified on the build server (LV2, headless, load in mod-host)
CPU = % of one core at 256-frame blocks (lv2bench).

| Plugin (URI prefix `https://hannesbraun.net/ns/lv2/airwindows/` unless noted) | Controls | CPU |
|---|---|---|
| console7channel | fader 0–1 (0.772 = unity) | 1.0% |
| console7buss | master 0–1 | 0.7% |
| totape6 | input ±12 dB, soften, headbump, flutter, output, drywet | 1.9% |
| pressure6 | compres, ratio (0–1) | 0.64% |
| purestdrive | drive 0–1 | 0.5% |
| busscolors4 | color 0–8, in/out trim ±18, dryWet | 0.8% |
| channel9 | consoletype 0–5, drive 0–200, output | 0.8% |
| Calf TapeSimulator / Saturator | mix, lowpass, speed… / drive, blend | 3.1% / 1.5% |
| LSP compressor / limiter / para EQ | — | 0.07–0.3% |

Console7 (not Console8): Console8 BussOut must be the very last stage (clipper + wordlength reduction), which conflicts with the −1 dBTP limiter. ChowTapeModel skipped: hysteresis solver ≈5–10% CPU per instance.

Safety ideas from blablack/nine-strip: crossfade stages when bypassing, keep compressors running while bypassed, reset a stage that outputs NaN.

## Optical (LA-2A style) model
Sources: JClones_CA2A.jsfx (four cascaded asymmetric one-pole stages; its time constants are 95% times = 3τ), InstaShadow OpticalCell.cpp (RC charge → light ∝ V², CdS R = k·L^−0.7, 2 s memory), FilTer87 CL1BCompressor.h.
Our model (gain-reduction domain, r = 1 − g): detector 0.75|x| + 0.25·RMS(12 ms) after optional HF-emphasis shelf, soft knee (3:1 compress / 12:1 limit);
m1 = min(0.30, fol(1 s, 3 s)); m2 = min(0.60, fol(0.15 s, 0.4 s, toward max(r, m1))); rf = fol(10 ms, 60 ms, toward max(r, m2)); gain = 1 − rf.
Release therefore depends on how long the signal was compressed, like the T4 cell.

## Real-time auto-mix algorithms worth implementing
- Loudness faders: per-channel gated short-term K-weighted loudness L_i (update only above −50 LUFS); Δfader = clip(0.3·(L_target + role_offset − L_i), ±0.5 dB/s), 1 LU deadband.
- Dugan gain sharing (vocal mics only): g_i = (e_i + 0.3n)/(Σe + n), n = 10^(−44/20); g_i ← g_i^1.6, renormalise, floor ≈ −15 dB; 12 ms / 250 ms envelopes on 10 ms blocks.
- Masking: 24 Bark bands every 100 ms; when vocal active and competitor E_j(b) − E_vox(b) > −3 dB in 1–4 kHz, cut that band on the competitor (max 3 dB).
- Howl detection (NHS): flag bin if PAPR > ~10 dB, PNPR (vs ±2–3 bins) > ~15 dB, PHPR (vs 2k, 3k) > ~10 dB, level > T, persisting ≥ 5 frames → narrow notch (Q 30, −6 dB) + fader dip.
- Diff-MST loss features (RMS, crest, 24-band Bark log spectrum mid/side, width) as reference targets.
- Kick→bass ducking belongs in a sidechain plugin, not Python.

## Metering
K-weighting at 48 kHz (libebur128): shelf b = [1.53512485958697, −2.69169618940638, 1.19839281085285], a = [1, −1.69065929318241, 0.73248077421585]; high-pass b = [1, −2, 1], a = [1, −1.99004745483398, 0.99007225036621]. 400 ms blocks, 100 ms hop, absolute gate −70 LUFS, relative gate −10 LU; short-term 3 s. True peak: 4× polyphase interpolation; 4× can under-read near Nyquist by ~0.5 dB. pyloudnorm's default filter is an approximation and offline-only.

## UI patterns
- Fader sends ≤ every 50 ms with trailing flush; while a finger is down the local value overrides server echoes.
- X-Air fader law (xair-api util.py): ≥ −10 dB: (dB+30)/40; −30…−10: (dB+50)/80; −60…−30: (dB+70)/160; −90…−60: (dB+90)/480.
- Meter flow control (mod-host output_data_ready) and canvas meters with local ballistics at 60 fps.

## Studio One
Studio One Project Hub (anthogoz) shows that a `.song` is a zip; `Devices/audiomixer.xml` holds AudioTrackChannel elements with gain (linear), pan (0–1, 0.5 = centre), mute/solo, Inserts (plugin classID, presetPath) and Sends (level, prefader). This lets VibeNation import the band's Studio One test-rig mix as a starting balance.
