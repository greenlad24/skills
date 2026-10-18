# Tooling for automatic mixing on Linux and getting the results into the LIVE engine (JACK + mod-host LV2)

Context: JACK + mod-host LV2 engine (LSP, x42, Dragonfly reverb, Calf delay, custom Faust), 48 kHz, 16 ch MR18; offline multitracks; a Scary Pockets reference. Researched 18 Oct 2026. Where something comes from prior knowledge and was not re-verified in this session, it is marked **[unverified]**.

## Q1. Can DawDreamer or Pedalboard load our LV2 plugins headless on Linux, so an optimiser renders through the exact live chain?

### Takeaway
No, neither hosts LV2. Both host **VST3** on Linux, and DawDreamer also compiles **Faust** natively. So the "exact live chain" can be rendered offline in Python like this: **LSP (VST3 builds exist) + Dragonfly (DPF, multi-format) + our Faust code** run in DawDreamer or Pedalboard. **x42 and Calf (LV2-only)** need a real LV2 host instead: lilv/`lv2apply`, Carla, or our own mod-host running on JACK's dummy backend in freewheel mode. The most faithful option is to render offline through mod-host itself, since it is the same binary, the same plugin builds and the same parameter mapping.

### Cited Findings
- **DawDreamer**: GPLv3. Linux x86_64/aarch64, Python 3.11–3.14. Hosts VST instruments and effects (repo topics: vst, vst3, vst-host, vst3-host). Supports Faust effects and polyphonic instruments plus the Faust Box/Signal APIs, and can transpile Faust to JAX/Flax. Has audio-rate and PPQN parameter automation and offline `render()`/`get_audio()`. The README does not mention LV2. Caveat: DawDreamer must be imported before JAX/Numba/TorchScript (other LLVM users) or the process can segfault. No GitHub releases are listed on the repo page. — [DawDreamer GitHub](https://github.com/DBraun/DawDreamer)
- A DawDreamer issue shows a Linux `.so` plugin (libTAL-NoiseMaker) being loaded through RenderEngine. No DawDreamer LV2 issue or support was found. — [DawDreamer issue #122](https://github.com/DBraun/DawDreamer/issues/122)
- **Pedalboard (Spotify)**: GPL-3.0 (bundles JUCE GPLv3, Rubber Band GPLv2+, LAME, libgsm). Loads **VST3 on Linux/macOS/Windows**; AU is macOS-only; LV2 is not mentioned. Plugin parameters are exposed as a dict and as attributes (e.g. `plugin.ratio = ...`). It releases the GIL for multicore use without multiprocessing. Linux wheels need AVX, and "most Linux VSTs need glibc > 2.27". Built-ins: Compressor, Gain, Limiter, HPF/LPF/Ladder, Convolution, Delay, Reverb, Chorus, Phaser, Distortion, PitchShift, MP3/GSM, Resample, Bitcrush. It has a live `AudioStream`. — [Pedalboard GitHub](https://github.com/spotify/pedalboard)
- ST-ITO (ISMIR 2024) used Pedalboard to load **63 open-source VST3 plugins compiled for Linux** and ran a CMA-ES optimiser through a ZamEQ2/ZamCompX2/ZamDelay/TAL-Reverb-4 chain. This is a working precedent for "optimise real plugins headless on Linux". — [ST-ITO paper (arXiv 2410.21233)](https://arxiv.org/html/2410.21233v1)
- **LSP plugins** ship CLAP, JACK standalone, LADSPA (partial), **LV2, VST2/LinuxVST and VST3**, all listed as full support. Debian packages these (e.g. `lsp-plugins-vst3`); 1.2.33/1.2.35 are packaged. — [LSP GitHub](https://github.com/lsp-plugins/lsp-plugins); [Debian lsp-plugins-vst3](https://packages.debian.org/ja/sid/lsp-plugins-vst3); [Debian codegraph 1.2.35](https://codegraph.jelmer.uk/lsp-plugins/1.2.35-1/)
- **Dragonfly Reverb**: GPL-3.0. Latest release 3.2.10 ("denormal protection"). 3.2.8 updated DPF, which "fixes CLAP on Linux". 3.2.6 added ARM Linux builds. Repo tags list lv2 and vst. — [Dragonfly GitHub](https://github.com/michaelwillis/dragonfly-reverb); [releases](https://github.com/michaelwillis/dragonfly-reverb/releases). That the release assets include **VST3** is **[unverified]**: DPF-based projects normally build LV2/VST2/VST3/CLAP/JACK, but I did not open the asset list.
- **lv2apply** (lilv-utils, in Ubuntu noble 0.24.22) runs an LV2 plugin over an audio file and writes the output: `-i in -o out`, `-c SYMBOL VALUE` for control ports, plugins found through `LV2_PATH`. Option syntax differs between versions. — [lv2apply man page (Ubuntu noble)](https://manpages.ubuntu.com/manpages/noble/man1/lv2apply.1.html); [Arch man](https://man.archlinux.org/man/lv2apply.1.en)
- **Carla** lists LV2 among its hosted formats, with rack/patchbay modes. Headless use is documented only as a workaround: pycarla says set `ProcessMode=3` in `~/.config/falkTX/Carla2.conf`. No documented offline/freewheel render API in `carla_backend.py` was found. — [pycarla examples](https://pycarla.readthedocs.io/en/latest/Examples.html); [Carla (fork README)](https://github.com/jpcima/Carla)

### Inferences
- **Recommended "exact chain" offline renderer:** run the production mod-host graph against JACK started with the dummy driver, put JACK in freewheel mode, and feed the multitrack WAVs in and record out with a JACK file player/recorder. This needs no new host, no plugin-format drift and gives identical parameter symbols, so an optimiser's best values can be sent to the live mod-host verbatim (`param_set`). Freewheel runs faster than real time, bounded by CPU. **[unverified: not benchmarked; JACK freewheel and the dummy backend are standard JACK features, but mod-host's behaviour under freewheel was not tested here]**
- **Faster inner loop:** per-channel single-plugin renders with `lv2apply`, or lilv's Python bindings (**[unverified]** that our lilv build ships them), parallelised across 16 cores on the show server or a cheap CPU droplet. Each CMA-ES candidate renders only the channels whose parameters changed. Cache per-channel outputs and sum in numpy, because gain/pan/send are linear and need no plugin render.
- Using the LSP VST3 builds in Pedalboard is viable, but VST3 and LV2 builds of the same plugin may differ subtly (parameter ranges, defaults). Do a null test (render the same settings in both, compare) before trusting a VST3-optimised preset on the LV2 engine.
- x42 (e.g. x42-eq/fil4, x42-dpl) and Calf delay are, as far as I know, **LV2-only on Linux [unverified]**. They are reachable only through an LV2 host path (lv2apply/lilv/Carla/mod-host).
- Faust plugins: compile the same `.dsp` with DawDreamer's FaustProcessor for offline work and `faust2lv2` for live, so DSP is bit-identical. DawDreamer's Faust→JAX path even gives a **differentiable** version of our own custom plugins.
- **Licensing:** DawDreamer, Pedalboard, Dragonfly, LSP and Matchering are all GPL-3.0. Fine for internal server-side use; GPL obligations apply only if we distribute binaries/software to others. Running them as a SaaS backend is not distribution under GPLv3 (it is not AGPL). **[legal inference, not legal advice]**

### Gaps
- No primary source confirms DawDreamer or Pedalboard LV2 support (it appears absent). I did not check whether either has an open LV2 feature request.
- Whether the Dragonfly release assets include VST3 was not verified.
- No benchmark of offline render speed of a 16-channel LV2 chain under JACK freewheel was found.

## Q2. Which optimisation approaches are documented for matching a target mix (per-track contributions) or a reference's spectrum/loudness/dynamics, with code?

### Takeaway
There are two documented families, both with open code. (1) **Gradient-based** fitting with differentiable proxies of the console: dasp-pytorch (Apache-2.0), GRAFX (Apache-2.0), Diff-MST (non-commercial licence), automix-toolkit DMC (Apache-2.0). (2) **Gradient-free** fitting through the real plugins: ST-ITO, which uses CMA-ES with pop 64 and ≤25 steps, about 1 min per example, over real VST3s via Pedalboard. For our "fit teacher mix onto live chain" job, the practical recipe is a hybrid. First do a closed-form or least-squares fit of the linear parts (per-channel gain, pan, send levels), then fit the nonlinear parts (EQ bands, comp) with dasp-style proxies or CMA-ES through the real LV2s.

### Cited Findings
- **dasp-pytorch**: Apache-2.0. Differentiable `gain`, `distortion`, `parametric_eq`, `compressor`, `expander`, `noise_shaped_reverberation`, `stereo_widener`, `stereo_panner`, `stereo_bus`. Its quickstart fits a parameter with Adam (lr 0.01, 2,500 iterations, MSE). The examples include automatic EQ and production style transfer. 304 stars and no tagged releases, so it is a small research library. — [dasp-pytorch GitHub](https://github.com/csteinmetz1/dasp-pytorch)
- **GRAFX**: Apache-2.0 (`pip install grafx`). PyTorch audio processing graphs of differentiable processors with batched parallel GPU computation. Its showcase optimises every processor's parameters in a large music-mixing graph by gradient descent. DAFx 2024 demo track (Lee, Martínez-Ramírez, Liao, Uhlich, Fabbro, K. Lee, Mitsufuji, Sony). — [GRAFX GitHub](https://github.com/sh-lee97/grafx); [arXiv 2408.03204](https://arxiv.org/abs/2408.03204)
- **ST-ITO** (Steinmetz et al., ISMIR 2024): inference-time optimisation of arbitrary, including non-differentiable, effect chains to match a reference. Uses **CMA-ES** (≈100-dim spaces; population 64; max 25 steps; sigma 0.3; parameters normalised to [0,1] and initialised at 0.5; early stop after 10 steps with <0.1 improvement). The objective is cosine similarity of **AFx-Rep** embeddings (PANNs encoder, self-supervised, mid and side embeddings concatenated). About 1 min per example, against about 1 s for direct parameter-prediction networks. In a 23-listener study it scored at least on par with DeepAFx-ST+. Limitations: series chains only, assumes minimal prior processing, poor on hard tasks like guitar tone matching. Code: github.com/csteinmetz1/st-ito. — [ST-ITO arXiv](https://arxiv.org/html/2410.21233v1); [ISMIR 2024 poster](https://ismir2024program.ismir.net/poster_249.html)
- **Diff-MST** (Vanka, Steinmetz, Rolland, Reiss, Fazekas, ISMIR 2024): multitrack mixing style transfer from a **reference song** using a differentiable mixing console. Includes a compressor that can be switched off; effects are configurable. Licence **CC-BY-NC-SA 4.0 (non-commercial)**. No public weights link on the README. GPU-oriented training. — [Diff-MST GitHub](https://github.com/sai-soum/Diff-MST)
- **automix-toolkit**: Apache-2.0. Pretrained **DMC** (Differentiable Mixing Console) and Mix-Wave-U-Net checkpoints (ENST-Drums only, on Hugging Face). `scripts/inference.py` turns stems into `mix.wav`. Recipes for ENST-Drums, DSD100 and MedleyDB. — [automix-toolkit GitHub](https://github.com/csteinmetz1/automix-toolkit)
- **pyloudnorm**: MIT. ITU-R BS.1770-4 integrated loudness, loudness/peak normalisation, and an "attempt" at EBU 3342 LRA. **No true-peak** is mentioned. Non-differentiable; the README points to Descript `audiotools` (PyTorch) and `jaxloudnorm` (JAX) for differentiable loudness. — [pyloudnorm GitHub](https://github.com/csteinmetz1/pyloudnorm)
- **torchaudio**: entered maintenance mode in 2.9 and removed the APIs deprecated in 2.8; I/O moved to TorchCodec. In 2.10, after feedback, `lfilter`, `overdrive`, RNNTLoss, CUCT and forced_align were **kept**. Do not build new mixing code on torchaudio's effects; `lfilter` remains usable as a differentiable biquad. — [torchaudio 2.9 docs](https://docs.pytorch.org/audio/2.9.0/torchaudio.html); [pytorch/audio issue #3902](https://github.com/pytorch/audio/issues/3902)

### Inferences
- **Fitting a teacher mix to our live chain, step by step:**
  1. **Per-channel gain/pan/send**: if teacher stems are available (e.g. the teacher model outputs per-track processed stems), gain and pan are a linear least-squares problem per stem (`argmin_g ||g·x_proc − y_stem||`), solved in closed form in milliseconds.
  2. **EQ bands**: fit the magnitude response ratio (teacher stem spectrum ÷ our pre-EQ channel spectrum, smoothed) onto the LSP/x42 band parameters with dasp `parametric_eq` as a proxy (gradient), then verify by a real LV2 render. Or run CMA-ES directly over the band frequency/gain/Q through `lv2apply`.
  3. **Compressor**: dasp `compressor` as a proxy is an approximation (different detector and knee than LSP). Use CMA-ES through the real LSP compressor with a loss on short-term-loudness envelope and crest factor.
  4. **Reverb sends**: optimise send level only, keeping the Dragonfly preset fixed. A loss on early/late energy ratio or the AFx-Rep embedding fits the budget.
- **Budget**: ST-ITO's 64 × 25 = 1,600 renders per fit is affordable per channel on 16 cores if each render is a 10–20 s excerpt. This is an offline post-show job, never a live one.
- For the **Scary Pockets reference**, the documented open path is ST-ITO-style: AFx-Rep embedding plus spectral, loudness and LRA terms as the objective, CMA-ES over master-bus and group parameters. Diff-MST would fit per-track console parameters to a reference song, but its NC licence and missing public weights make it research-only for us.
- Spectral and loudness loss terms can be computed with pyloudnorm (LUFS, LRA) plus numpy (1/3-octave or ERB spectra). Add true-peak separately via 4× oversampling, since pyloudnorm lacks it.

### Gaps
- I did not verify whether the st-ito repo's licence permits commercial use.
- No published work fits parameters specifically onto **LV2** plugins (all found used VST3/Pedalboard or differentiable proxies).
- No source quantified the proxy-vs-real mismatch for dasp compressor against the LSP compressor.

## Q3. Matchering: what it does, license, suitability for our master chain

### Takeaway
Matchering 2.0 is **GPL-3.0, offline, file-based** reference mastering. It matches RMS, frequency response, peak amplitude and stereo width of a target to a reference, then applies its own "Hyrax" brickwall limiter. It works internally at 44.1 kHz with a 4096-point FFT and ≤15 min tracks. It is unsuitable as a live processor, but useful offline: derive a static "match EQ" curve and level and width targets from the Scary Pockets reference, then bake them into our live master EQ (LSP) and a static gain. Our existing LUFS/true-peak limiter keeps the −16 LUFS / −1 dBTP targets.

### Cited Findings
- Matchering 2.0 masters a TARGET to match a REFERENCE's "RMS, frequency response, peak amplitude, and stereo width". It includes the open-source **Hyrax** brickwall limiter (a JSFX clone by Tokyo Dawn Labs is linked). Licence **GPL-3.0**. Python ≥3.8, ≥4 GB RAM, libsndfile (FFmpeg optional for MP3). Outputs pcm16/pcm24 WAV. Also ships as a Docker web app. 2.7k stars, 33 open issues. Hosted versions: Songmastr, MVSEP, Moises. — [Matchering GitHub](https://github.com/sergree/matchering)
- Defaults: `internal_sample_rate = 44100`, `max_length = 15*60` s, `max_piece_size = 15` s, `fft_size = 4096`, `lin_log_oversampling = 4`, `rms_correction_steps = 4`, `threshold = (2**15−61)/2**15` (≈ −0.016 dBFS sample peak), LOWESS smoothing `frac 0.0375`. Limiter: attack 1 ms, hold 1 ms, release 3000 ms. — [matchering/defaults.py](https://raw.githubusercontent.com/sergree/matchering/master/matchering/defaults.py)

### Inferences
- The internal 44.1 kHz rate means our 48 kHz show audio is resampled. The final output peak threshold is near 0 dBFS **sample** peak, not −1 dBTP, and the output is not loudness-targeted to −16 LUFS (it matches the reference RMS). Matchering's output therefore must not feed the stream directly. Use it as an **analysis tool**: run it (or just its spectrum-ratio + LOWESS step) on a show recording against the reference, export the smoothed correction curve, fit it to 6–8 LSP parametric bands (least squares), and apply those as the static master "tone match". Re-check that the live limiter holds −1 dBTP.
- Matching the reference's RMS would push a live funk mix much louder than −16 LUFS (commercial masters are typically far hotter). Match **spectral balance and width**, not level. **[inference]**

### Gaps
- Did not read the Habr article describing the exact Matchering algorithm steps (the README only names the matched properties).
- Matchering's release and version dates are not shown on the repo page.

## Q4. Real-time adaptive/automixing on Linux: open-source automixers (gain-sharing, feedback-safe), cross-adaptive processing, neural mixing latency

### Takeaway
I found **no open-source Dugan-style gain-sharing automixer in LV2 (or Faust/Python/C++)**. The commercial ones (Waves Dugan, Yamaha DEK-DUGAN, Q-SYS) are not Linux/LV2. The algorithm is simple and documented (each input's gain = its RMS ÷ the sum of all inputs' RMS), so the realistic path is a **custom Faust LV2** for the vocal/talk mics. Rane/InMusic patent US8542849 should be checked before shipping. Neural mixing (DMC, Mix-Wave-U-Net, Diff-MST) is documented as offline. No source gives live-latency figures, so real-time neural mixing should stay out of the audio path. Keep the agreed design: a deterministic controller does fast moves, and AI updates parameters every 1–3 min.

### Cited Findings
- Search found only commercial gain-sharing automixers: Waves Dugan Automixer/Speech (Mac/Windows; Waves hosts) and Yamaha DEK-DUGAN (console-bound). — [Waves Dugan Automixer manual](https://www.dandugan.com/Assets/manuals/Waves-Dugan-Automixer-Manual.pdf); [Yamaha DEK-DUGAN](https://www.fullcompass.com/prod/660063-yamaha-dek-dugan-dm5-series-dugan-automix-software-package)
- Q-SYS documents gain sharing as: each input's gain is computed as its RMS level divided by the combined RMS of all inputs, with optional sidechain frequency filtering. This is a usable spec. — [Q-SYS Gain-Sharing Automatic Mic Mixer](https://help.qsys.com/Content/Schematic_Library/auto_mixer.htm)
- Patent US8542849 (connectable gain-sharing automixers, Rane/InMusic) is listed as active. — [Google Patents US8542849](https://patents.google.com/patent/US8542849)
- ST-ITO needs about 1 min per optimisation against about 1 s for direct parameter-estimation networks. Inference-time optimisation is far from audio-rate, so it can only drive slow parameter updates. — [ST-ITO arXiv](https://arxiv.org/html/2410.21233v1)
- Pedalboard has a live `AudioStream` and releases the GIL, but it is not a JACK/LV2 host. — [Pedalboard GitHub](https://github.com/spotify/pedalboard)

### Inferences
- **Live automix design for our rig**: write a Faust `automix.dsp`. Per-channel RMS detectors (≈20–50 ms) feed gain-share weights `g_i = rms_i / Σ rms_j` (optionally raised to a power and floored at, say, −15 dB so band mics never fully gate), smoothed with 5–50 ms attack and 200–500 ms release. A "last mic hold" and a global ceiling keep total gain constant. This makes it inherently feedback-safer than independent gates, because the summed open-mic gain stays near one mic's worth. Compile with `faust2lv2` and load it in mod-host. Apply it **only to speech/backing vocal mics and the MC mic**, not to instruments; music mixing wants Claude's balance, not level-proportional gain. **[design inference; patent check required]**
- Cross-adaptive moves (e.g. ducking guitar 2–3 dB at 2–4 kHz while lead vocal is active, or sidechained kick→bass) are achievable live with LSP's sidechain-capable dynamics/EQ plugins. The repo already ducks reverb under the vocal (commit 860eee0). Extend this pattern rather than adding neural inference. **[inference; LSP sidechain variants exist per LSP's plugin list, not re-verified here]**
- Feedback safety: keep the existing deterministic feedback detector + notch path. No open-source LV2 "feedback-safe automixer" was found.

### Gaps
- No open-source LV2 automixer or feedback-suppressor was found. The search was limited to two queries; a scan of the LV2 plugin lists (lv2plug.in, MOD plugin store) and the Faust libraries was not done.
- No published real-time latency numbers were found for DMC, Mix-Wave-U-Net or Diff-MST.
- The claims and expiry of patent US8542849 were not analysed.
