# GitHub mixing plugins research

Date: 16 October 2026. Scope: the open-source "mixing plugins" landscape on GitHub, read for code and algorithms that VibeNation can learn from and improve on. Analog-emulation plugins (Airwindows, ChowDSP, Calf), automix-toolkit and metering libraries are covered in a separate report and are only mentioned here where they matter.

## Bottom line

- **There is no open-source "AI mix engineer" plugin to copy.** The GitHub search for "mixing plugins" is mostly noise (Laravel Mix, Neovim, Elixir, crack/"download" repos). The real value sits in about a dozen small, well-written DSP projects, and in a few clear algorithms inside them.
- **The best ideas are control algorithms, not plugins.** The four that matter most for us are: (1) the master_me "leveler with brake" (ride towards a loudness target, freeze during quiet parts); (2) LSP Auto-Gain's two-speed gain rider with "surge" protection; (3) ZL Equalizer's dynamic EQ that slides between two EQ curves, with a "learn threshold" that uses a running histogram; (4) Dugan-style gain sharing for the vocal mics (gain = sqrt(own power / total power)).
- **LSP already ships most of the building blocks we need, and they are cheap.** Our LSP 1.2.14 install already has `autogain`, `sc_autogain` (sidechain riding/ducking), `beat_breather`, `gott_compressor`, sidechain multiband compressors and dynamics processors. Each stereo instance costs about 1% of one JACK cycle on this server.
- **master_me builds and runs headless as LV2, but it is too heavy to run as-is.** It adds about 20 to 30% JACK DSP load on this 2 vCPU server (bypassing its sections does not help, because Faust bypasses compute both paths). We should copy its leveler logic, not run the plugin.
- **Faust is the right tool for our own DSP.** `faust2lv2` is installed and works here: Bart Brouns' `autoComp` (auto-release compressor) built in about 11 s of CPU and costs about 1 to 3% load. Two VibeNation Faust plugins (`vngain`, `vnopto`) already exist in `/usr/local/lib/lv2`. New VibeNation DSP should be written in Faust, compiled with `faust2lv2`, and hosted in mod-host like the rest.
- **Neural and generative mixers are offline research, not live tools.** Sony FxNorm-automix (MIT) and MEGAMI (non-commercial licence, diffusion models) need a GPU and whole-song context. What we can borrow is their "effect normalisation" idea: per-instrument target spectra and dynamics, learned after the show.

## How the search was done

GitHub search API, sorted by stars, 15 to 40 results each, for: "mixing plugins", "mixing plugin", "audio mixing", "auto mixing", "automatic mixing", "channel strip plugin", "mastering plugin", "bus compressor", "lv2 plugins", "juce mixing", "faust audio effects", "intelligent mixing", "automixer", "neural audio effects", plus follow-ups for "dynamic eq plugin", "resonance suppressor", "lookahead limiter", "auto gain plugin", "spectral unmasking", "dugan automix" and "faust compressor". About 600 unique repositories came back. Most were not audio at all. Seventeen were shallow-cloned into `/root/vn-tools/research/deep/` and their DSP source was read.

## Landscape

"Headless Linux" means the code can run as an LV2 (or JACK) process on our server with no screen: **y** = yes today, **build** = yes after a source build, **n** = no (VST3/AU-only, Windows-only, offline Python, or no code).

| Repo | Stars | Licence | Category | Headless Linux |
|---|---|---|---|---|
| lsp-plugins/lsp-plugins | 897 | LGPL-3.0 | Full suite: EQ, dynamics, autogain, mixers, limiter | y (installed) |
| lsp-plugins/lsp-plugins-autogain | 1 | LGPL-3.0 | Auto-gain (loudness rider), part of LSP | y (installed) |
| zamaudio/zam-plugins | 323 | GPL-2.0 | Dynamics, dynamic EQ, maximiser, saturation | y (installed) |
| x42/dpl.lv2 | 28 | GPL-3.0 | Look-ahead peak limiter | y (installed) |
| x42/fil4.lv2 | 95 | GPL-2.0 | Parametric EQ | y (installed) |
| michaelwillis/dragonfly-reverb | 1158 | GPL-3.0 | Reverb | y (installed) |
| trummerschlunk/master_me | 754 | GPL-3.0 | Automatic mastering for live streaming | build (done, see below) |
| ZL-Audio/ZLEqualizer | 1030 | AGPL-3.0 | Dynamic EQ, EQ match | build (JUCE, LV2 target exists; not tried) |
| ZL-Audio/ZLCompressor | 223 | AGPL-3.0 | Compressor with styles, look-ahead, oversampling | build (JUCE; not tried) |
| ZL-Audio/ZLSpectrumEqualizer | 76 | AGPL-3.0 | Dynamic spectrum EQ | build (JUCE) |
| ZL-Audio/ZLSplitter | 168 | AGPL-3.0 | L/R, M/S, transient/steady splitter | build (JUCE) |
| magnetophon/lamb-rs | 134 | AGPL-3.0 | Look-ahead compressor/limiter (Rust, nih-plug) | n (CLAP/VST3 only) |
| magnetophon/lamb | 16 | AGPL-3.0 | Same DSP in Faust | build (faust2lv2; heavy CPU) |
| magnetophon/faustCompressors | 33 | GPL-3.0 | Compressor library, auto-release compressor | build (done, see below) |
| magnetophon/CompBus | 5 | GPL-3.0 | Compressors sidechained from the bus they feed | build (Faust) |
| grame-cncm/faust | 3188 | GPL/LGPL | DSP language, compiles to LV2/JACK | y (installed) |
| DISTRHO/DPF | 876 | ISC | Plugin framework (LV2/CLAP/VST) | y |
| robbert-vdh/nih-plug | 2996 | ISC | Rust plugin framework | n (no LV2) |
| okarlsen/sgtm-automix | 0 | AGPL-3.0 | Dugan gain-sharing automixer (JUCE) | build |
| g0ku321/podcast-automix | 8 | MIT | Offline Dugan automixer for 2 mics (Python) | n (offline) |
| stoatworks-labs/mixerreturn | 3 | MIT | Dugan automixer summing-bus plumbing | n |
| CristianMoresi/M32LiveConsoleTool | 1 | MIT | Auto-level faders, anti-clip, tempo delays over OSC (C#) | n (but the logic is portable) |
| brahimaann/smart-eq | 0 | none | Adaptive vocal EQ + cross-track spectral unmasking | n (no licence, VST3) |
| Thiagohgl/DyERS-dynamic-resonance-suppressor | 18 | AGPL-3.0 | Soothe-style resonance suppressor (STFT) | build (old Projucer project) |
| pndias/hott-master-vst | 4 | GPL-3.0 | Mastering with resonance suppression | n (VST3) |
| Kiriki-liszt/Relief_Compressor | 52 | GPL-3.0 | Clean compressor, Hilbert detector, FIR look-ahead | n (VST3/AU) |
| Wamphyre/oXygen | 49 | BSD-3 | Mastering chain (JUCE) | build (covered elsewhere) |
| blablack/nine-strip | 44 | AGPL-3.0 | Channel strip using Airwindows DSP | build (covered elsewhere) |
| FilTer87/VST-AnalogChannel | 43 | GPL-3.0 | Channel strip | n (VST3) |
| fsecada01/bus_channel_strip | 11 | BSD-3 | Bus strip (Rust) | n (VST3/CLAP) |
| GareBear99/FreeEQ8 | 49 | GPL-3.0 | 8-band EQ | n (macOS/VST3 focus) |
| ZhiyuAlexZhang/Grisey | 65 | GPL-3.0 | LUFS / true-peak metering | covered elsewhere |
| x42/meters.lv2 | 226 | GPL-2.0 | Meters | y (installed; covered elsewhere) |
| sony/FxNorm-automix | 149 | MIT | Deep-learning automix + effect normalisation | n (offline, GPU) |
| SonyResearch/MEGAMI | 45 | CC BY-NC-SA | Generative (diffusion) automix | n (non-commercial, offline) |
| csteinmetz1/AutomaticMixingPapers | 109 | MIT | Reading list | n/a |
| csteinmetz1/dasp-pytorch | 304 | Apache-2.0 | Differentiable EQ/comp/reverb in PyTorch | n (offline training) |
| csteinmetz1/steerable-nafx | 212 | Apache-2.0 | Neural effects research | n |
| adobe-research/DeepAFx | 216 | Adobe research | Plugins as differentiable layers | n |
| DBraun/DawDreamer | 1328 | GPL-3.0 | Python DAW: runs Faust + VST, offline render | y (offline twin) |
| spotify/pedalboard | 6356 | GPL-3.0 | Python effects + VST3 host | y (offline) |
| mikeoliphant/neural-amp-modeler-lv2 | 544 | GPL-3.0 | Neural amp models for DI guitar/bass | build |
| lucianodato/noise-repellent | 564 | LGPL-3.0 | Spectral noise reduction | build |
| lucianodato/speech-denoiser | 293 | LGPL-3.0 | RNNoise LV2 (speech only) | build |
| vvvar/PeakEater | 464 | GPL-3.0 | Wave-shaper/clipper | build |
| mixxxdj/mixxx | 7271 | GPL-2.0 | DJ software (not a mix chain) | n/a |
| bbc/brave | 692 | Apache-2.0 | Live AV mixer (GStreamer) | archived |
| software-mansion/smelter | 736 | custom | Real-time video/audio compositing | not audio DSP |
| twinysam/FreeAudioPluginList | 143 | none | List only | n/a |

## What was measured on this server

JACK runs here with the dummy driver at 48 kHz and 1024-frame periods. With the current VibeNation chain loaded, JACK DSP load already reads about 32 to 46% (it moves around). A second, temporary mod-host on ports 5598/5599 loaded each test plugin on the dummy capture ports and was removed afterwards.

| Plugin (stereo) | Extra JACK DSP load |
|---|---|
| master_me (all sections) | +20 to +30% |
| master_me with multiband, knee comp and limiter "bypassed" | about the same (Faust crossfade bypass still computes everything) |
| LSP `mb_compressor_stereo` | about +1% or less |
| LSP `autogain_stereo` | about +1.2% each (4 instances = +5%) |
| Faust `autoComp` (built here) | about +1 to +3% (within noise) |

Takeaway: LSP and small Faust programs are cheap; double-precision Faust with long sliding windows (master_me, lamb) is not.

## Deep dives

### 1. master_me (trummerschlunk/master_me): automatic mastering for live streams
- **Files read:** `master_me.dsp`, `lib/ebur128.dsp`, `expanders.lib`, `plugin/MasterMePlugin.cpp`, `Makefile`, `plugin/Makefile`.
- **What it does:** one stereo plugin that takes an unmastered stream to a loudness target. Chain: input gain → DC blocker → mono/phase/correlation fix → gate → EQ (high-pass, tilt, side EQ) → **leveler** → "kneecomp" (M/S RMS compressor) → 8-band M/S multiband compressor → RMS limiter → zero-latency brickwall. Presets include "YouTube −14 LUFS" and "Music general −16 LUFS".
- **Leveler (the gem):** it measures short-term LUFS (400 ms K-weighted sliding mean square) **at the output of the chain** (the whole chain sits inside a feedback loop). Each sample: `gain_dB = clamp((target − LUFS_s) + previous_gain, −maxcut, +maxboost)`, then a one-pole low-pass whose cutoff is `speed × brake`. The **brake** is a peak expander on the input: when the input falls below the brake threshold (default −14 dB relative), brake goes to 0 and the leveler freezes. Quiet passages, song endings and talk between songs do not get pumped up.
- **Compressor design tricks:** "strength" instead of ratio (`GR = −strength × overshoot`, strength 1 means ∞:1); thresholds are written **relative to the loudness target**, so one target change moves the whole chain; quadratic soft knee; FF/FB blend; partial stereo link via linear interpolation between per-channel GR and the linked minimum; multiband gains applied with cascaded 3-stage shelving filters (no phase-splitting crossover on the audio path).
- **Build result:** built headless for LV2 with `make -C plugin lv2_dsp HAVE_OPENGL=false` (uses pregenerated C++, so no faustpp needed) and the TTL files written by DPF's `lv2_ttl_generator`. Installed to `/usr/local/lib/lv2/master_me.lv2`. URI `https://github.com/trummerschlunk/master_me`; `lv2info` lists 97 ports and the five loudness presets. It needs the LV2 worker and options features, which mod-host provides. It ran in mod-host, but at +20 to 30% load (see above).
- **Borrow:** the leveler-with-brake logic and "thresholds relative to target", in our Python loudness controller (or a small Faust plugin). **Improve:** compute the brake from the **music bus** level (not the master), so a crowd or MC talk does not unfreeze it; use LUFS-S for riding and LUFS-I for reporting; limit the ride speed in dB/s, not with a one-pole.

### 2. LSP Auto-Gain (lsp-plugins-autogain + lsp-dsp-units)
- **Files read:** `lsp-dsp-units/src/main/dynamics/AutoGain.cpp`, `include/.../AutoGain.h`, `lsp-plugins-autogain/src/main/meta/autogain.cpp`, `include/private/meta/autogain.h`.
- **Algorithm:** two loudness measurements (long, default 400 ms, and short, default 20 ms) with selectable weighting (K, A, B, C, D or none). Gain moves at **fixed dB-per-second rates**: per sample `gain *= exp(±rate·ln10/20/fs)`. Rules, in order: (1) silence (short level below "silence") → hold the gain; (2) **surge up**: if the short level after gain is above `target × deviation`, fall at the fast short-fall rate until it is back inside; (3) optional quick amp: if far below target, grow fast; (4) otherwise move slowly by the long rates towards the target. (5) A final soft-knee cubic curve on the short level clips gain on sudden pops. (6) Optional maximum boost.
- **Sidechain modes** (`sc_autogain`): Internal; **Control** (the sidechain level drives the gain, which is automatic ducking/riding); **Match** (makes this signal as loud as the sidechain signal, which is automatic gain matching).
- **Headless:** already installed (`http://lsp-plug.in/plugins/lv2/autogain_mono`, `..._stereo`, `sc_autogain_*`). About 1% load per stereo instance.
- **Borrow:** use `autogain_mono` per vocal and horn/sax/harmonica channel as the fast "fader rider" inside bounds Claude sets (target, max boost, deviation). Use `sc_autogain` in Match mode for automatic make-up after each channel's compressor, so Claude's compressor moves never change channel loudness. **Improve:** set the target per song section from the director, not as a fixed number.

### 3. ZL Equalizer (ZL-Audio/ZLEqualizer): dynamic EQ, learn threshold, EQ match
- **Files read:** `source/dsp/filter/dynamic_filter/dynamic_base.hpp`, `dynamic_side_handler.hpp`, `source/dsp/compressor/follower/ps_follower.hpp`, `source/zlp/controller.cpp` (lines 815 to 880), `source/zlp/filter_dynamic_attach.cpp`, `source/chore/eq_match/eq_match_optimizer.hpp`.
- **Dynamic EQ model:** each band has a **base gain** and a **target gain**. The sidechain (band-filtered) level in dB is mapped to an amount `a = clamp((L − (T − K)) / (2K), 0, 1)²` (quadratic onset), smoothed by the "PS follower", and the band gain is `base + a × (target − base)`, applied per sample to the IIR coefficients. This is easier for an AI to reason about than ratio and threshold: "when the 3 kHz area of the vocal gets loud, slide from 0 dB to −4 dB".
- **PS follower (punch/smooth):** a decoupled peak detector `state = max(x, rel·(state − x) + x)` followed by an attack smoother, blended with a plain branching attack/release follower by a "smooth" amount. Coefficients `exp(−2π·1000/(fs·t_ms))`.
- **Learn threshold (auto-threshold):** per block it measures band loudness **minus** full-signal loudness, and pushes that into two exponentially decaying histograms (decay 0.9 per second and 0.99 per second). Threshold = 50th percentile; knee = max(½ × (P90 − P10), 2 to 5 dB). "Relative" mode adds the current total loudness back, so the threshold follows the performer's overall level.
- **EQ match:** greedy fitting. For up to N bands: try peak, low shelf and high shelf at orders 2, 4 and 6; optimise (log f, gain, log Q) with NLopt (global CRS2, then local SLSQP) to minimise the dB error; subtract that band's response; stop when the error stops improving.
- **Headless:** JUCE, with an LV2 target in CMake for Linux; not built (heavy JUCE build and AGPL).
- **Borrow:** (a) the base-to-target dynamic band model for our vocal de-harsh and kick/bass-unmask bands; (b) the histogram learn-threshold, run in Python on analyzer data to set LSP dynamic band thresholds every few seconds; (c) greedy EQ-match in scipy to turn a "target tone curve" from Claude into at most 8 LSP `para_equalizer` bands.

### 4. ZL Compressor (ZL-Audio/ZLCompressor): compressor styles
- **Files read:** `source/dsp/compressor/styles/{clean,classic,optical,vocal}.hpp`, `computer/compression_computer.hpp`, `follower/ps_follower.hpp`.
- **Styles are just topology:** Clean = feed-forward. Classic = feedback (the detector reads the previous output sample), smoothing in dB. Optical = smoothing the **linear** level **before** the dB conversion, which gives natural program-dependent release. Vocal = feedback, smoothing the **linear gain**. The gain computer is a smooth piecewise quadratic with an adjustable "curve" (−1 to +1) that bends the knee.
- **Borrow:** when we write our own compressor in Faust, offer these four detector topologies as one "style" control instead of many knobs. Claude picks Optical for vocals and bass, Clean for drums and the bus.

### 5. lamb (magnetophon/lamb, lamb-rs): look-ahead compressor/limiter
- **Files read:** `lamb.dsp` (lines 334 to 600 and 1040 to 1090), `lamb-rs/README.md`.
- **Algorithm:** gain computer in dB → **release hold** (`max(min(prev, GR delayed by hold), slidingMin(GR, hold))`, so gain does not rise if it must fall again soon) → **look-ahead sliding minimum** over the attack window → the "SIN" smoother, which moves the gain along a warped sine curve, so the gain's slope never jumps (no clicks, less distortion at fast times) → optional **adaptive release**: a slow reference GR is tracked, and release slows towards infinity once the fast GR is more than a few dB away from it (no pumping after a big hit).
- **Cost:** the author warns it is CPU-heavy; fixed latency is 100 ms. Rust version is CLAP/VST3 only.
- **Borrow:** release hold + adaptive release, which are cheap ideas, for our master bus glue and for the bass channel. Not the full SIN smoother.

### 6. faustCompressors / autoComp (magnetophon/faustCompressors)
- **Files read:** `autoComp.dsp`, `compressors.lib`.
- **Auto-release:** `release = rel + (slowGR − fastGR) × amount`. When gain reduction is sustained (slow GR is large), release lengthens; on short transients it stays fast. Also shows FF/FB blend, RMS detector with sliding sums, partial link, and a multi-channel ducker (`duckGainReduction`) where each channel ducks the others.
- **Build result:** compiled here with `faust2lv2 autoComp.dsp` (about 11 s of CPU; it took 8 min of wall time only because it ran at low priority), installed to `/usr/local/lib/lv2/autoComp.lv2`, URI `https://faustlv2.bitbucket.io/autoComp`, verified with `lv2info` and run in a temporary mod-host at about 1 to 3% load. Ports `in0/in1/out0/out1`.
- **Borrow:** this is proof that our own Faust plugins are a practical route. Most of this library has since moved into the standard Faust `co.*` compressors.

### 7. Dugan gain-sharing automixers (sgtm-automix, podcast-automix)
- **Files read:** `okarlsen_sgtm-automix/plugin/Source/AutomixEngine.h`, `g0ku321_podcast-automix/podcast_automix/automix.py`, `stoatworks-labs_mixerreturn/Source/DSP/SummingBus.cpp`.
- **Core formula:** for channel i, `g_i = min(1, sqrt(P_i / ΣP))`, where P is a smoothed power (attack 15 ms, release 200 ms, smoothed in the log domain, 16-sample hops). The detector is band-limited to 150 Hz to 5 kHz (voice band). Per-channel **weight** (dB) biases priority. **Presence gate** with hysteresis (on −75 dB, off −81 dB, 1 s hold), so a silent mic does not take part. Bypass and presence fades avoid clicks. The total gain of all open mics stays constant (a "number of open mics" (NOM) of 1), so bleed and comb filtering drop.
- **Podcast version adds:** an **attenuation floor** (−20 / −26 dB) and a gain curve exponent of 1.6, so the non-speaking mic is turned down, not off.
- **Borrow for music:** run gain sharing only across the **two vocal mics** (and optionally the sax and harmonica mics), with a floor of about −8 to −10 dB, not −20 dB. When both people sing, both stay open. This is a cheap control-rate job (per 16 to 64 samples), easy to write in Faust or to drive with LSP gains.

### 8. smart-eq (brahimaann/smart-eq): spectral unmasking formula
- **Files read:** `src/dsp/Stages.h` (SpectralDucker), `src/dsp/STFTEngine.cpp`, `README.md`. No licence file, so treat as reading only (formula, not code).
- **Formula:** per FFT bin, `D = 2|X||S| / (|X|² + |S|²)`, which peaks at 1 when the instrument bus X and the vocal S have equal energy in that bin. `gain = 1 − depth × D × φ(S)`, with `φ(S) = S² / (S² + knee²)`. Per-bin smoothing: attack 5 ms, release 120 ms. STFT 2048, hop 512, so 2048 samples (43 ms) of latency.
- **Borrow:** the idea, not the STFT. On our system, 43 ms latency on the band bus is acceptable only if the vocal path is delayed to match. A cheaper version is to use LSP `sc_mb_dyna_processor` on the band bus keyed by the vocal bus (3 to 4 IIR bands at 200 to 500 Hz, 1 to 3 kHz and 3 to 6 kHz, 1 to 3 dB maximum dip), with Claude setting depth.

### 9. DyERS resonance suppressor (Thiagohgl)
- **File read:** `Source/DynamicEqualizer.cpp`.
- **Algorithm:** STFT; find peaks where the bin power is `Prominence` times its ±2-bin neighbours; skip peaks more than 20 dB below the biggest; for each peak multiply the transfer function by a Gaussian dip in **log-frequency** (`1 − depth·exp(−Δlogf²/w²)`); smooth the transfer function over time; optional wet/dry and "delta" listen.
- **Borrow:** the peak-pick + log-Gaussian dip is a neat way to build a **feedback and ringing detector** for our vocal and acoustic channels. Run it in the Python analyzer (not in the audio path), and when a narrow peak persists for more than 0.5 to 1 s, set a narrow LSP notch. This is exactly the "Claude may step in for feedback" emergency rule.

### 10. Relief Compressor (Kiriki-liszt)
- **Files read:** `source/RLFCMP_processor.cpp` (detector notes and coefficients), `source/RLFCMP_shared.h` (envelope follower, Kaiser window class).
- **Tricks:** a **Hilbert-pair detector** (two allpass chains 90° apart; `sqrt(a² + b²)` gives a ripple-free envelope even on low bass); detector time constants are subtracted from the user attack/release so the stated times are accurate; **0.5 ms look-ahead smoothed with a 24-tap Kaiser FIR** instead of a hard hold; double precision.
- **Borrow:** the Hilbert detector for the bass DI and synth bass compressors (a plain peak detector ripples at 40 to 80 Hz and causes distortion).

### 11. M32 Live Console Tool (CristianMoresi): live auto-leveling rules
- **File read:** `Modules/AutoLeveler.cs` (correction loop and manual-move handling), `README.md`.
- **Rules worth copying:** separate up/down slew in dB/s; silence gate; **ignore large drops** (an intentional cut is not drift); **stand down the moment a human moves the fader**; after the human move, wait 4 s for it to settle and then **re-capture the target** from the new level; anti-clip only ever reduces, with a per-resource limit.
- **Borrow:** this matches our "human holds the control" rule. Add the "learn the human's level as the new target" step to the post-show learning, so next show starts closer to what the band wanted.

### 12. Sony FxNorm-automix (MIT): effect normalisation
- **Files read:** `automix/utils_data_normalization.py` (`get_eq_matching`, `get_mean_peak`, `get_comp_matching`, panning matching).
- **Idea:** before training, every stem is pushed to the **average** spectrum, dynamics, stereo width and reverb of its instrument class. EQ matching = long-term average spectrum (64k FFT) vs reference, `sqrt` of the ratio, 101-tap FIR. Dynamics matching = the mean of onset peaks above the 75th percentile (after peak normalisation), then a threshold/ratio search until it falls inside the reference ±1 standard deviation.
- **Borrow:** after each show, compute per-channel "average spectrum" and "onset-peak crest" from the recorded multitrack, compare with VibeNation's target per instrument role, and store the corrections in the versioned playbook. Do not run the neural network live.

### 13. zam-plugins (installed): what is inside
- **Files read:** `plugins/ZaMaximX2/ZaMaximX2Plugin.cpp`, `plugins/ZamAutoSat/ZamAutoSatPlugin.cpp`, `plugins/ZamDynamicEQ/ZamDynamicEQPlugin.cpp`.
- ZaMaximX2 is a look-ahead maximiser with a moving-average "envelope fill" and sample peaks only. ZamAutoSat is just `2x(1 − |x|/2)` (no oversampling). ZamDynamicEQ is one band driven by a basic compressor. All work, but LSP and x42 do these jobs better for us. Keep x42 dpl as the final true-peak stage.

## What VibeNation should build

Ordered by value for effort. CPU figures are for this 2 vCPU build server at 1024-frame periods. The show server has a faster CPU, so these figures are on the safe side.

1. **Master loudness leveler with brake** (Python controller now, Faust later)
   - Where: master, before the glue compressor and the x42 limiter (it drives the existing `master_gain`).
   - How: ride LUFS-S towards −16 LUFS using master_me's loop, but with a dB/s slew limit (for example +1 dB/s up, −3 dB/s down, max ±6 dB) and a **brake** that freezes riding when the band bus is more than 14 dB below its running median (song ends, talk, breaks). Glue compressor and limiter thresholds are set relative to the target.
   - CPU: about 0 (control rate in the existing analyzer).
2. **Per-channel fast rider: LSP `autogain_mono` on vocals, sax, harmonica, guest horn**
   - Where: after the channel compressor, before the fader.
   - How: target set by Claude per song; deviation 3 dB; long grow/fall 1 to 3 dB/s; surge protection on; silence at −60 LUFS (holds gain when the player stops); max boost 6 dB. Treat it as Claude's "deterministic controller" for fast moves.
   - CPU: about 1% per instance → about 5% for 5 channels.
3. **Auto make-up after compression: LSP `sc_autogain` in Match mode**
   - Where: on each channel where Claude changes compression, fed with the pre-compressor signal as sidechain.
   - Why: Claude can change threshold/ratio without changing the balance, which removes a whole class of AI mistakes.
   - CPU: about 1% per instance; use only on the 4 to 6 channels that are compressed hardest.
4. **Learn-threshold service** (Python, from ZL Equalizer)
   - Where: in the analyzer. For each dynamic band (vocal 2 to 5 kHz, kick/bass 60 to 120 Hz, guitar/piano 250 to 500 Hz), keep a decaying histogram of `band level − channel level`; set threshold = P50 + offset and knee = ½(P90 − P10). Update every 2 to 5 s with a small slew.
   - CPU: negligible (numpy on existing band data).
5. **Dynamic EQ as "base curve → target curve"**
   - Where: channel EQ stage for vocals (de-harsh 2.5 to 5 kHz, de-ess 6 to 9 kHz), bass/kick (low-mid mud), acoustic DI (body resonance).
   - How: LSP `para_equalizer` cannot do dynamic bands; use LSP `mb_dyna_processor`/`sc_mb_dyna_processor` now. Later, write a small Faust "vndyneq" (2 to 4 bands; amount curve and PS follower from ZL; band gain interpolated between base and target).
   - CPU: about 1 to 2% per instance (LSP); Faust version should be under 1%.
6. **Vocal-keyed unmasking on the band bus**
   - Where: band (non-vocal) bus, keyed by the vocal bus.
   - How: LSP `sc_mb_dyna_processor` with 3 bands, maximum 1 to 3 dB of dip, attack 5 ms, release 120 ms; depth set by Claude per song. Only the bands where the D score from smart-eq's formula (computed in the analyzer) shows real collision are enabled.
   - CPU: about 2%.
7. **Two-vocal Dugan gain sharing** (Faust)
   - Where: after the vocal compressors, before the vocal bus.
   - How: `g_i = max(floor, sqrt(P_i/ΣP))`, voice-band detector 150 Hz to 5 kHz, attack 15 ms, release 200 ms, floor −8 dB, presence gate with 1 s hold, per-mic weight. When both sing (power ratio within 6 dB), both stay at 0 dB.
   - CPU: under 1%.
8. **Feedback and ringing watchdog** (Python, from DyERS)
   - Where: analyzer on vocal, acoustic DI and sax mics.
   - How: FFT 4096; peaks above neighbours by more than 12 dB, persisting for more than 0.7 s and rising → place an LSP notch (Q 8 to 15, −6 dB), then relax over 30 s. This is an emergency move, so it is allowed even on human-held controls.
   - CPU: about 1 to 2% of one core in numpy.
9. **Own compressor in Faust with "style" + auto-release + release hold**
   - Where: replace `compressor_mono` on bass, synth bass and vocals once the above is stable.
   - How: one DSP, four styles (Clean FF, Classic FB, Optical linear-domain, Vocal), autoComp's auto-release, lamb's release hold, a Hilbert detector option for the bass. Thresholds expressed relative to the channel's learned median level.
   - CPU: about 1% per channel if kept in single precision without long sliding windows.
10. **Post-show "effect normalisation" learning** (offline, Python)
   - From FxNorm: per channel, compare average spectrum and onset-peak crest with VibeNation's per-role targets; fit corrective EQ with the greedy EQ-match method (scipy, at most 4 bands); store in the versioned playbook. Also record every human fader hold as a new target (M32 tool idea).
   - Tools: DawDreamer (runs Faust in Python) to replay recorded multitracks through the same DSP offline.

Guard-rails for all of the above: nothing touches preamp gain; every automatic move has a hard range (Claude sets the range, the controller moves inside it); any control a human touches is frozen for the rest of the stream, except the feedback, clipping and dead-signal emergencies.

## Not worth it

- **master_me as a live plugin:** works, but costs +20 to 30% DSP load here; copy the algorithm instead.
- **lamb / lamb-rs:** beautiful limiter, but heavy CPU, 100 ms latency, and the Rust build has no LV2.
- **MEGAMI:** non-commercial licence and offline diffusion models.
- **FxNorm-automix neural model, Wave-U-Net mixers, DeepAFx, steerable-nafx, signaltrain:** offline research needing a GPU and full songs; keep only the normalisation ideas.
- **ZLEqualizer / ZLCompressor binaries:** strong DSP, but AGPL and heavy JUCE builds; re-implement the small algorithms instead.
- **Relief Compressor, VST-AnalogChannel, bus_channel_strip, FreeEQ8, hott-master-vst, Apotheosis:** VST3/AU/CLAP only; no LV2.
- **ondinha-unmask:** README only, no code.
- **smart-eq:** no licence; formula only.
- **stoatworks mixerreturn:** plumbing for a shared summing bus, no new DSP.
- **podcast-automix:** offline Python for speech; we only need its floor idea.
- **ZamAutoSat:** a one-line waveshaper with no oversampling.
- **Laravel/Neovim/Elixir "mix" repos, "LANDR/FL Studio/Soothe2 … full/cracked" repos:** not audio, or lure/piracy repos. Avoid.
- **noise-repellent, speech-denoiser:** made for noise and speech; they harm music.
- **mixxx, Godot Mixing Desk, Mix.js, waveform-playlist:** DJ, game or web playback mixers, not mix-processing chains.

## Files and installs

- Clones: `/root/vn-tools/research/deep/` (17 repos plus `magnetophon_lamb` and `brahimaann_smart-eq`).
- Installed and verified with `lv2info`:
  - `https://github.com/trummerschlunk/master_me` in `/usr/local/lib/lv2/master_me.lv2` (DSP only, no GUI; runs in mod-host; heavy).
  - `https://faustlv2.bitbucket.io/autoComp` in `/usr/local/lib/lv2/autoComp.lv2` (Faust auto-release compressor; light).
- Neither plugin is used by the VibeNation graph yet.
