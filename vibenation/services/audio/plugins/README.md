# VibeNation LV2 effect suite

Headless, analog-modelled LV2 plugins for the live broadcast mix (Ubuntu 24.04, JACK 48 kHz, mod-host).
DSP is written in Faust (`*/<name>.dsp`), compiled to C++ with `faust -double` and wrapped by our own
thin LV2 wrapper (`common/vn_arch.cpp`) instead of `faust2lv2`, so that:

- port **symbols are clean** (`peak_reduction`, `gr`, …; faust2lv2 appends `_N`), names/units/enumerations come from Faust metadata (`common/gen_ttl.py` writes the TTL from `faust -json`);
- every plugin has **output control ports** (gain reduction / riding gain / level change in dB) and a `latency` port;
- optional **2x oversampling** of the whole Faust program (`declare vn_oversample "2"`) between polyphase IIR half-band filters (`common/vn_os.h`, elliptic 8-coefficient design from `common/halfband_design.py`, ~100 dB image rejection, ~3 samples latency);
- **safety**: FTZ/DAZ set during `run()` (no denormal stalls), NaN control values ignored, and if any output sample is NaN/inf the DSP state is cleared and the block is muted (self-healing instead of a dead channel);
- **click-free**: continuous gains are smoothed (20 ms, linear domain); filter-shape controls change at block rate so coefficients stay out of the sample loop.

URIs: `https://vibenation.app/lv2/<name>`. Build + install all: `./build.sh` (→ `/usr/local/lib/lv2`), one: `./build.sh vn_fet`, no install: `NO_INSTALL=1 ./build.sh`.
Tests: `VN_LV2_DIR=/usr/local/lib/lv2 ../.venv/bin/python tests/test_plugins.py` (ctypes host `tests/vnhost.py`, tones + 10 s stem excerpts normalised to −20 dBFS RMS; 31 checks, all pass).

Reference repos (shallow clones, read-only) are in `/root/vn-tools/research/effects/` and `/root/vn-tools/research/`.

## CPU (measured with `lv2bench -b 1024`, this 2-vCPU AMD droplet)

| plugin | µs / 1024-sample block | % of one core in real time |
|---|---|---|
| vn_opto | 69 | 0.32 |
| vn_fet (2x OS) | 111 | 0.52 |
| vn_vca_bus (stereo) | 29 | 0.14 |
| vn_pultec (2x OS) | 190 | 0.89 |
| vn_tape (2x OS) | 440 | 2.1 |
| vn_tape_stereo (2x OS) | 806 | 3.8 |
| vn_console (stereo) | 69 | 0.32 |
| vn_deesser | 55 | 0.26 |
| vn_rider | 22 | 0.10 |

For comparison on the same box: Calf Deesser 58, Calf Compressor 38, Airwindows ToTape6 396, Console7Channel 217 µs/block.
A full vocal-type strip (rider + opto + de-esser + pultec) is ~340 µs/block ≈ 1.6 % of a core per channel, so 16 channels ≈ 25 % of one core.

---

## vn_opto — LA-2A style optical leveler (mono)

**Models:** T4 electro-optical cell in a feedback leveler. Detector listens to the cell output (like the hardware), so the ratio is soft and program dependent (≈3:1 Compress, ≈10:1 Limit) with no ratio law. Cell: 10 ms attack; two-stage release — about half the reduction recovers in ~60 ms, the rest over 0.5–5 s depending on a "memory" state that charges in ~2 s of compression and discharges in ~15 s. 3-band sidechain emphasis (LALA-style), gentle tube/transformer colour that grows with level.

**Studied:** JClones `CA2A.jsfx` (cascaded GR followers, curve-fitted feed-forward), DiffAPF `LA-2A` (differentiable feed-forward model), hz8107 `opto-beta-compressor`, InstaShadow `OpticalCell`, the team's earlier `faust_test/vnopto.dsp` prototype.

**Better:** real feedback topology instead of feed-forward curve fitting; the slow release stage follows the fast stage (no onset overshoot — the prototype grabbed 18 dB then settled to 12 dB on a step); memory-dependent release is explicit and bounded; detector = 8 ms RMS blended with a peak follower; colour without oversampling cost (2nd/3rd-order polynomial, band-limited).

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `peak_reduction` | Peak Reduction | 0 … 100 (threshold −6 … −51 dBFS) | 30 | % |
| `gain` | Gain (makeup, on the compressed path) | −20 … 30 | 0 | dB |
| `mode` | Mode | 0=Compress / 1=Limit | 0 | |
| `sc_low` / `sc_mid` / `sc_high` | Sidechain emphasis 200 Hz shelf / 1.5 kHz bell / 5 kHz shelf | −12 … 12 | 0 | dB |
| `colour` | Tube Colour | 0 … 100 | 30 | % |
| `mix` | Mix (parallel) | 0 … 100 | 100 | % |
| `gr` | **output**: gain reduction | 0 … 40 | | dB |

Verified: step test 12 dB GR → 6.3 dB after 150 ms → 3.6 dB after 1.5 s (two-stage release); vocal stem at PR 20/50 → 2/10 dB GR.

## vn_fet — 1176 style FET compressor (mono, 2x oversampled)

**Models:** feedback FET limiter. Ratio buttons set loop gain (β = ratio − 1) with ratio-dependent threshold and knee, as on the unit; "All" = faster, harder, gritty. Rectifier feeds the timing network directly (one sample behind → transients overshoot naturally). The attack knob is the *closed-loop* attack (open-loop time = attack·(1+β), which keeps the loop stable at 20:1). Program-dependent release from two RC paths (knob and 5× knob; slow share grows with the knob). FET channel-resistance distortion grows with gain reduction, then a class-A output stage (2nd harmonic).

**Studied:** yonie `WetCompressor` (`compengine.cpp`, `fetcore.h`: feedback loop, dual-RC release, FET channel modulation), JClones `L2`/`Molot`, Airwindows `Pressure4/5/6`, `ButterComp2`, iairu `logic-plugins`, rshloosh/NKBFET 1176 JUCE clones.

**Better:** WetCompressor has only a fixed 4:1, 3 stepped timings and no oversampling; ours has all ratios incl. All-buttons, continuous 20–800 µs / 50–1100 ms, closed-loop attack mapping (no instability at high ratio — a naive dB-domain loop overshot by 15 dB in our tests), 2x OS for the colour stages, mix.

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `input` | Input (drives into the fixed threshold ≈ −20 dBFS) | −20 … 40 | 0 | dB |
| `output` | Output | −30 … 20 | 0 | dB |
| `ratio` | Ratio | 0=4:1 / 1=8:1 / 2=12:1 / 3=20:1 / 4=All | 0 | |
| `attack` | Attack (closed-loop) | 20 … 800 | 300 | µs |
| `release` | Release | 50 … 1100 | 300 | ms |
| `colour` | Colour | 0 … 100 | 50 | % |
| `mix` | Mix | 0 … 100 | 100 | % |
| `gr` | **output**: gain reduction | 0 … 40 | | dB |

Verified: snare +6 dB in → max GR 4:1 23.6 dB, 20:1 27.9 dB, All 28.8 dB; 0 dBFS tone → 4:1 −17.9, 20:1 −20.0 dBFS.

## vn_vca_bus — SSL G-series style bus compressor (stereo)

**Models:** feed-forward VCA (exponential gain law), linked detector (max |L|,|R|) after an optional 2nd-order sidechain HPF, log-domain gain computer with a 4 dB soft knee, attack/release in dB. AUTO release = dual-RC network: fast path 0.1 s plus a slow path (1.2 s) that only charges during sustained compression.

**Studied:** superdandi `gssl-jsfx` (`SSL_G_Bus.jsfx`), Kiriki-liszt `Relief_Compressor`, magnetophon `faustCompressors` / faustlibraries `co.*`, Airwindows `ButterComp2`.

**Better:** gssl's auto release blends coefficients with a "sustain" flag (switches abruptly at the threshold); ours is a true parallel dual-RC (transient: 21 % of GR left after 300 ms, sustained: 84 %); continuous attack, continuous sidechain HPF (2nd order instead of 1-pole), parallel mix; very cheap.

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `threshold` | Threshold | −40 … 0 | −12 | dB |
| `ratio` | Ratio | 0=2:1 / 1=4:1 / 2=10:1 | 1 | |
| `attack` | Attack | 0.1 … 30 | 10 | ms |
| `release` | Release | 0=0.1 s / 1=0.3 s / 2=0.6 s / 3=1.2 s / 4=Auto | 4 | |
| `sc_hpf` | Sidechain HPF (0 = off) | 0 … 300 | 0 | Hz |
| `makeup` | Makeup | 0 … 20 | 0 | dB |
| `mix` | Mix | 0 … 100 | 100 | % |
| `gr` | **output**: gain reduction | 0 … 30 | | dB |

## vn_pultec — Pultec EQP-1A style program EQ (mono, 2x oversampled)

**Models:** low boost = 2nd-order low shelf (Q 0.6, midpoint 2× CPS, up to +13.5 dB); low atten = 1st-order low shelf (midpoint 4× CPS, up to −17.5 dB); the passive network's interaction is modelled (with boost engaged part of the atten is restored below CPS), giving the classic boost+atten curve. High boost = bell 3–16 kHz with bandwidth (Q 2.5 → 0.4, up to +16 dB); high atten = 1st-order high shelf at 5/10/20 kHz (up to −16 dB). Tube makeup stage (mostly 2nd harmonic, level dependent).

**Studied:** consint `Pult-EQ` (`pultec_mono.dsp`: full 6-port WDF of the passive network, GPL — measured, not copied), ABSounds `EQP-WDF-1A` (WDF + `chowdsp_wdf`), Airwindows `Tube2`. We compiled the consint WDF and measured it (`/root/vn-tools/research/effects/pultec_ref/`): its pot laws give almost no action until the top of the knob (half low-atten = −0.8 dB) and max low boost/atten of only +10.8/−9.8 dB.

**Better:** calibrated, linear-in-dB knob laws matching the EQP-1A spec (+13.5/−17.5/+16/−16 dB); the boost+atten trick reproduced (60 Hz both at 10: +7.3 dB at 30 Hz, −5.4 dB at 200 Hz); 2x OS so 12/16 kHz bells keep their analog shape (16 kHz bell measures +14.2 dB at 16 kHz) and the tube stage is alias-free; a few biquads instead of a per-sample 6×6 scattering matrix.

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `low_freq` | Low Frequency | 0=20 / 1=30 / 2=60 / 3=100 Hz | 2 | |
| `low_boost` / `low_atten` | Low Boost / Atten | 0 … 10 | 0 | dial |
| `high_freq` | High Boost Frequency | 0=3k / 1=4k / 2=5k / 3=8k / 4=10k / 5=12k / 6=16k | 3 | |
| `high_boost` | High Boost | 0 … 10 | 0 | dial |
| `high_bw` | High Bandwidth (sharp → broad) | 0 … 10 | 5 | dial |
| `atten_freq` | High Atten Frequency | 0=5k / 1=10k / 2=20k | 1 | |
| `high_atten` | High Atten | 0 … 10 | 0 | dial |
| `tube` | Tube Drive | 0 … 100 | 30 | % |
| `output` | Output | −12 … 12 | 0 | dB |
| `gain_change` | **output**: program gain change (300 ms RMS out/in) | −24 … 24 | | dB |

## vn_tape / vn_tape_stereo — tape machine (2x oversampled)

**Models:** record pre-emphasis → Jiles-Atherton magnetic hysteresis (RK2 solver, α-transform derivative, Langevin anhysteretic) → exact inverse de-emphasis (so highs saturate first, but the low-level response is flat) → head bump (speed dependent 38/62/110 Hz with the dip above) → gap/spacing HF loss (12/17/22 kHz) → optional wow & flutter (modulated fractional delay; the dry path is delayed by the same mean delay so Mix never combs). Off by default.

**Studied:** jatinchowdhury18 `AnalogTapeModel` (`HysteresisProcessing.h`, `HysteresisOps.h`, `HysteresisProcessor.cpp`), Mando-369 `FAUST_FSM_TAPE` (JA in Faust, LUT approach), Airwindows `ToTape6–9`, `IronOxide`, JClones `DuTape`/`TapeHead`.

**Better:** ChowTape's makeup is 1/Ms, so its low-level gain moves ±6 dB with Saturation and −8 dB with Bias; we measured that the loop's small-signal gain ≈ c and normalise with 1/c, so low-level gain stays within ±0.3 dB for all settings and Drive changes *saturation*, not level. Drive maps to the JA anhysteretic slope (as Chow) so huge input levels never push the solver out of range (an input-gain drive blew up by +9 dB in our first test). Pre/de-emphasis pair, speed-dependent bump/loss, NaN-guarded solver. Cheaper than ChowTape's default chain; comparable to Airwindows ToTape6.

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `drive` | Drive (amount of saturation) | −12 … 18 | 0 | dB |
| `saturation` | Saturation (JA Ms) | 0 … 100 | 50 | % |
| `bias` | Bias (loop width) | 0 … 100 | 50 | % |
| `speed` | Tape Speed | 0=7.5 / 1=15 / 2=30 ips | 1 | |
| `bump` | Head Bump | 0 … 100 | 50 | % |
| `wow` / `flutter` | Wow / Flutter | 0 … 100 | 0 | % |
| `mix` | Mix | 0 … 100 | 100 | % |
| `output` | Output | −12 … 12 | 0 | dB |
| `gain_change` | **output**: level change caused by the tape | −24 … 24 | | dB |

Measured (1 kHz): −18 dBFS → H3 −48 dBc, 0 dBFS → H3 −24 dBc; Drive +12 → H3 −15 dBc at 0 dBFS. `vn_tape_stereo` has the same controls, independent L/R hysteresis, shared transport wobble.

## vn_console — console channel / summing colour (stereo)

**Models:** input-transformer flux saturation that acts on the low band only (iron saturates LF first), a cubic op-amp/discrete stage plus a small even-order term — all level dependent (1 kHz: −18 dBFS → H2 −64 / H3 −76 dBc; 0 dBFS → H2 −46 / H3 −39 dBc). Optional capacitive L/R crosstalk rising 6 dB/oct above 1 kHz (up to ≈ −30 dB).

**Studied:** Airwindows `Console7Channel/Buss`, `Console9`, `Channel9` (dielectric level-dependent filtering, sin/asin encode-decode), FilTer87 `VST-AnalogChannel`, JClones `SatChannel`/`SatBuss`, WetCompressor `Transformer`.

**Better:** Airwindows hard-clamps at ±1 with un-band-limited sin() shapers; ours is a pure polynomial below clipping (band-limited to 3×, no oversampling needed), DC-blocked even harmonics, LF-only iron saturation, optional crosstalk, and a level-change meter. Use it on channels *or* buses (one plugin, no encode/decode pairing to get wrong).

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `drive` | Drive | −12 … 18 | 0 | dB |
| `colour` | Colour | 0 … 100 | 50 | % |
| `crosstalk` | Crosstalk | 0 … 100 | 0 | % |
| `output` | Output | −12 … 12 | 0 | dB |
| `gain_change` | **output**: level change (left) | −24 … 24 | | dB |

## vn_deesser — relative-detection de-esser (mono)

**Models:** detector band-pass at `freq` compared with the full-band level (100 Hz HPF), so it reacts to how *sibilant* a moment is, not how loud the singer is — no threshold re-tuning when the vocal level changes (essential for automatic mixing). Absolute floor ignores hiss/bleed. Reduction via a dynamic TPT-SVF bell at `freq` (split mode) or full-band gain (wide).

**Studied:** lsp-plugins `lsp-plugins-deesser` (crossover + compressor with absolute threshold), OlliV `DiaPro`, IgorKhramtsov `DeEsser`, Calf Deesser, Airwindows `DeEss`, Nebula-De-Esser.

**Better:** relative detection; phase-coherent cut. Note: we first built the classic "out = x − (1−g)·HPF(x)" split and measured that it only removed ~1 dB of 6–8 kHz at 10 dB GR (HPF phase shift) — the dynamic bell removes 5.7 dB on sibilant frames, 0.4 dB on others, 0.00 dB change in 100 Hz–3 kHz.

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `freq` | Frequency | 3000 … 12000 | 6500 | Hz |
| `sensitivity` | Sensitivity (relative threshold −2 … −20 dB) | 0 … 100 | 50 | % |
| `range` | Max Reduction | 0 … 24 | 8 | dB |
| `mode` | Mode | 0=Split / 1=Wide | 0 | |
| `listen` | Listen (detector band) | 0/1 | 0 | |
| `floor` | Detector Floor | −80 … −20 | −50 | dBFS |
| `gr` | **output**: gain reduction | 0 … 24 | | dB |

## vn_rider — vocal rider (mono)

**Models:** an automatic fader. Voice-weighted level (150 Hz HPF + 5 kHz LPF, 200 ms RMS) is ridden toward `target` within ±`range` with time constant `speed`. Gate: the fast (20 ms) level must be above `gate` AND within 15 dB of the recent singing level (peak memory falling 3 dB/s); otherwise the rider holds its gain, so pauses, breaths and drum/bass bleed never pump the vocal up.

**Studied:** FlorisLeirs `Fader_Rider` (block-RMS, block-size dependent, noise gate on the audio itself), SickNixon `DeathRider` (template only), csteinmetz1 `automix-toolkit`, Waves Vocal Rider behaviour.

**Better:** sample-accurate, block-size independent; voice-weighted detector; two-part gate with a fast close (our first version with only the slow level lifted phrase tails by +5 dB — fixed and covered by a test); outputs the riding gain.

| symbol | name | range | default | unit |
|---|---|---|---|---|
| `target` | Target Level (voice-weighted RMS) | −40 … 0 | −20 | dBFS |
| `range` | Range (±) | 0 … 12 | 6 | dB |
| `speed` | Speed | 50 … 3000 | 400 | ms |
| `gate` | Gate Floor | −80 … −20 | −50 | dBFS |
| `output` | Output | −12 … 12 | 0 | dB |
| `gain` | **output**: current riding gain | −12 … 12 | | dB |

Verified: vocal +8 dB → rider −6.9 dB; vocal −8 dB → +7.7 dB; singing then 5 s of −69 dBFS kick bleed → gain moves only −0.1 → −0.7 dB.

---

## Verification summary

- `lv2info` loads all 9 URIs with no errors/warnings.
- mod-host (private instance on port 5700, not the production one): `add`, `param_set`, `param_get`, audio connect and `remove` succeed for every plugin (ids 950–958).
- `tests/test_plugins.py`: 31/31 checks pass (no NaN/inf, sane levels, behaviour checks above).
