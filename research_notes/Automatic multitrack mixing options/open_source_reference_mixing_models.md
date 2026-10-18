# Open-source / research automatic multitrack mixing systems (reference-based style transfer focus) — status Oct 2026

Checked 18 Oct 2026 against GitHub API (licence, last push, releases, file trees), Hugging Face API and arXiv. "Last push" = GitHub `pushed_at`.

## 1. Which systems exist, what they output, and can they take our 16 stems + a reference song and return per-channel console parameters?

### Takeaway
Only one released system does exactly "raw multitracks + reference song -> per-track gain/pan/EQ/compressor (+ master)": **Diff-MST** — but its **pretrained weights are not public** (open issue asking for them since Sep 2024) and its code is **CC BY-NC-SA 4.0**. The only recent system with **public weights, MIT licence and interpretable FX-chain output** is **StemFX** (ISMIR 2026), but it works on **4 source-separated stems (vocals/bass/drums/other)**, not 16 channels, and its effects are Python-library effects (sox etc.), not console-style per-channel EQ/comp. Everything else either outputs only audio (FxNorm-Automix, Mix-Wave-U-Net, MEGAMI), only gain+pan (DMC), is single-input (DeepAFx-ST, ITO-Master), or needs the target mix of the *same* song (grafx-prune). For our use, the practical route is our own **differentiable-console parameter fit** using Apache-2.0 libraries (dasp-pytorch / GRAFX) against a reference's features, rather than a pretrained model.

### Cited Findings

**Diff-MST (Vanka, Steinmetz, Rolland, Reiss, Fazekas — ISMIR 2024)**
- Repo https://github.com/sai-soum/Diff-MST — 66 stars, last push 2025-07-07, last commit 2024-11-09 (README video link); 3 open issues; no GitHub releases — [GitHub API](https://api.github.com/repos/sai-soum/Diff-MST)
- **No public checkpoints**: issue #27 (opened 2024-09-06, still open) "May I ask if it is convenient to provide checkpoints for academic purposes?"; inference script hard-codes a local path `/Users/svanka/Downloads/.../epoch=191-step=626608.ckpt` — [issues](https://github.com/sai-soum/Diff-MST/issues/27), [eval_all_combo.py](https://github.com/sai-soum/Diff-MST/blob/main/scripts/eval_all_combo.py)
- Licence: README says code is **CC-BY-NC-SA 4.0**; LICENSE file is CC BY-NC-SA 4.0 (non-commercial, share-alike) — [README](https://github.com/sai-soum/Diff-MST), [LICENSE](https://github.com/sai-soum/Diff-MST/blob/main/LICENSE)
- Inputs/outputs: raw tracks + reference song -> transformer controller predicts per-track gain, stereo pan, parametric EQ ("4-band"), dynamic range compressor, plus master-bus stereo EQ + compressor; parameters are static per song (not time-varying) — [arXiv 2407.08889](https://arxiv.org/html/2407.08889v1)
- Code `AdvancedMixConsole` EQ band ranges: band0 80–2000 Hz, band1 2–8 kHz, band2 8–12 kHz, band3 12 kHz–(Nyquist−1 kHz), Q 0.1–5; code also contains an FX-bus `noise_shaped_reverberation` with 12 band gains/decays — [modules.py](https://github.com/sai-soum/Diff-MST/blob/main/mst/modules.py). **Conflict:** the arXiv v1 paper says the console "lacks a crucial reverb module" — [arXiv](https://arxiv.org/html/2407.08889v1). The reverb is in code; whether the trained checkpoint used it is unverified.
- Training data: MedleyDB (196 songs) + Cambridge-MT (535 songs) multitracks; MTG-Jamendo (>55k songs) as unpaired real references; 44.1 kHz; 10 s training segments; trained with up to 8 or 16 tracks (configs `medley+cambridge(+jamendo)-16.yaml` exist); "performance declined beyond the trained track count" — [arXiv](https://arxiv.org/html/2407.08889v1), [repo tree](https://github.com/sai-soum/Diff-MST/tree/main/configs/data)
- Model size ~190M trainable params; training 1.16M steps, batch 2; inference time/hardware **not reported** — [arXiv](https://arxiv.org/html/2407.08889v1)
- Inference code processes 10 s windows (441000 samples) of tracks and reference; TorchScript export added (PR #25) — [eval_all_combo.py](https://github.com/sai-soum/Diff-MST/blob/main/scripts/eval_all_combo.py), [PR #25](https://github.com/sai-soum/Diff-MST/pull/25)
- Quality evidence: **objective only, no listening test** (authors list it as future work). AF loss on 100 examples: Equal-loudness 6.55, prior MST 7.85e-2, Diff-MST AF-16 3.26e-2; FAD 17.6 / 17.9 / 15.1 — [arXiv](https://arxiv.org/html/2407.08889v1)
- Used as stage 2 in an AES 2025 two-stage system (rule-based narrowband-loudness balancing per group, then Diff-MST between groups) that reports MUSHRA tests beating LUFS baselines and mixing 100+ track sessions; references were Cambridge-MT rock; Stage-1 repo has no licence file — [SparrowReivun/AES2025-materials](https://github.com/SparrowReivun/AES2025-materials)

**DeepAFx-ST (Steinmetz, Bryan, Reiss — Adobe Research, 2022)**
- Repo https://github.com/adobe-research/DeepAFx-ST — 413 stars, last push 2023-05-30; weights in release v0.1.0 (2022-07-18), `checkpoints_and_examples.tar.gz` ~1.09 GB — [GitHub API releases](https://api.github.com/repos/adobe-research/DeepAFx-ST/releases)
- Licence: **Adobe Research License — noncommercial research only**; explicitly excludes "development of commercial products" — [LICENSE](https://github.com/adobe-research/DeepAFx-ST/blob/main/LICENSE)
- Single input recording + reference -> predicts control parameters of a 6-band parametric EQ (low shelf, 4 peaking bands, high shelf: gain/freq/Q) and a compressor (threshold, ratio, attack, release [code notes release unused in autodiff version], knee, makeup) — [README](https://github.com/adobe-research/DeepAFx-ST), [peq.py](https://github.com/adobe-research/DeepAFx-ST/blob/main/deepafx_st/processors/autodiff/peq.py), [compressor.py](https://github.com/adobe-research/DeepAFx-ST/blob/main/deepafx_st/processors/autodiff/compressor.py)
- Pretrained speech (LibriTTS) and music (Jamendo) models; `scripts/process.py -i input -r ref -c ckpt`; python 3.8 era — [README](https://github.com/adobe-research/DeepAFx-ST)
- Not a multitrack mixer (no gain/pan/balance across tracks) — [arXiv 2207.08759](https://arxiv.org/abs/2207.08759)

**FxNorm-Automix (Martínez-Ramírez et al., Sony — ISMIR 2022)**
- Repo https://github.com/sony/fxnorm-automix — **MIT** (Copyright 2022 Sony Group Corporation), 149 stars, last push 2024-03-11, 1 open issue; weights committed in repo under `trainings/results/` (ours_S_Lb, ours_S_pretrained, wun_S_Lb, ~10–11 MB each) — [GitHub API](https://api.github.com/repos/sony/fxnorm-automix), [LICENSE.md](https://github.com/sony/fxnorm-automix/blob/main/LICENSE.md)
- Output is **audio only** (end-to-end network mixes stems); trained on wet multitracks after "effect normalization"; average features computed on MUSDB18 (`features_MUSDB18.npy`) — i.e. 4-stem (vocals/bass/drums/other) setup; IRs used for training not released — [README](https://github.com/sony/fxnorm-automix)
- Pinned to `torch==1.9.0`, `setuptools==59.5.0`, soxbindings, aubio from git — hard to install on a 2026 Python — [README](https://github.com/sony/fxnorm-automix)
- Listening test with "highly experienced mixing engineers"; abstract says such systems are "still far from professional human-made mixes" — [arXiv 2208.11428](https://arxiv.org/abs/2208.11428). In the 2025 MEGAMI listening test FxNorm-AutoMix "received low scores on some songs" due to artifacts — [arXiv 2511.08040](https://arxiv.org/html/2511.08040)
- Includes the Wave-U-Net (WUN) baseline trainer/weights (`wun_S_Lb`) — [README](https://github.com/sony/fxnorm-automix)

**automix-toolkit (Steinmetz, Martínez-Ramírez, Bittner et al.; ISMIR 2022 tutorial) — DMC + Mix-Wave-U-Net**
- Repo https://github.com/csteinmetz1/automix-toolkit — **Apache-2.0**, 119 stars, last push 2024-08-28 — [GitHub API](https://api.github.com/repos/csteinmetz1/automix-toolkit)
- Weights on HF https://huggingface.co/csteinmetz1/automix-toolkit (card licence apache-2.0, last modified 2022-12-01): `enst-drums-dmc.ckpt`, `enst-drums-mixwaveunet.ckpt`, `medleydb-16-dmc.ckpt`, `encoder.ckpt` — [HF API](https://huggingface.co/api/models/csteinmetz1/automix-toolkit)
- DMC `Mixer` has `num_params = 2` per track: **gain (−48…+24 dB) and pan only**; no EQ/comp/reverb — [dmc.py](https://github.com/csteinmetz1/automix-toolkit/blob/main/automix/models/dmc.py)
- DMC is not reference-based (predicts a mix from the tracks alone); `inference.py ckpt tracks_dir` -> `mix.wav`; models expecting a fixed order need files named `01_…`, `02_…` — [README](https://github.com/csteinmetz1/automix-toolkit)
- Mix-Wave-U-Net outputs **audio only**; pretrained only on ENST-Drums — [README](https://github.com/csteinmetz1/automix-toolkit)
- Original DMC paper (ICASSP 2021): "human-readable mixing parameters", permutation-invariant, no limit on input sources, perceptual test with audio engineers "outperform baseline approaches" (no human reference given in abstract) — [arXiv 2010.10291](https://arxiv.org/abs/2010.10291)

**MEGAMI (Moliner, Martínez-Ramírez, Koo, Liao, Cheuk, Serrà, Välimäki, Mitsufuji — Sony/Aalto, arXiv Nov 2025, submitted ICASSP 2026)**
- Repo https://github.com/SonyResearch/MEGAMI — 45 stars, last push 2026-01-18; public checkpoints in release v0 (`CLAP_DA_public.pt`, `FxGenerator_public.pt`, `FxProcessor_public.pt`) plus LAION-CLAP and Fx-Encoder++ checkpoints — [README](https://github.com/SonyResearch/MEGAMI)
- Licence **CC BY-NC-SA 4.0** ("For commercial licensing inquiries: marco.martinez@sony.com") — [LICENSE](https://github.com/SonyResearch/MEGAMI/blob/main/LICENSE)
- Not reference-based: conditional diffusion generates per-track effect *embeddings* from dry tracks; a black-box TCN (~9M params) renders **audio only, no interpretable parameters**; up to 14 tracks, permutation-equivariant (unlabelled tracks OK); 11.9 s segments; 44.1 kHz input; no master-bus FX; time-invariant embeddings — [arXiv 2511.08040](https://arxiv.org/html/2511.08040), [README](https://github.com/SonyResearch/MEGAMI)
- Public checkpoints are trained on the "P" set: 248 MoisesDB+MedleyDB multitracks (best paper results use internal ~20k-song set) — [arXiv](https://arxiv.org/html/2511.08040)
- Listening test: 12 listeners (6 with production experience), 7 songs, compared human, equal loudness, E2E-Flow, FxNorm-AutoMix, MEGAMI; MEGAMI "approaches" human, sometimes above (Grunge, BritPop); wide CIs, strongly song-dependent; equal loudness scored well on Disco — [arXiv](https://arxiv.org/html/2511.08040)
- Inference compute not reported; env is conda python 3.13 — [README](https://github.com/SonyResearch/MEGAMI)

**StemFX (Cheng, Wu, Chen, Yeh, Chen, Yang — ISMIR 2026, arXiv Jul 2026)**
- Repo https://github.com/barry-mir/stemfx — **MIT** code; weights https://huggingface.co/barry-mir/stemfx-bsfilm (HF licence **mit**, `best_checkpoint.pt`, updated 2026-05-06); `pip install stemfx`; last push 2026-07-21 — [README](https://github.com/barry-mir/stemfx), [HF API](https://huggingface.co/api/models/barry-mir/stemfx-bsfilm)
- Encoder maps a **4-stem 10 s segment** to a 512-d style embedding; 6-layer transformer decoder emits a per-stem FX chain (`{"vocals":[{"effect":..., "params":{...}}], "bass":..., "drums":..., "other":...}`) in multiafx format; `model.transfer_audio("song_a.wav","song_b.wav")` separates both with bundled SCNet (~214 MB weights) — [README](https://github.com/barry-mir/stemfx)
- Effects come from multiafx (MIT): 85 effects across audiomentations, sox, torchaudio, scipy, librosa, pyloudnorm, numpy (e.g. `sox_highpass`, `sox_compand`, `sox_reverb`, `sox_gain`) — [multiafx](https://github.com/barry-mir/multiafx)
- Trained on pseudo-stems from ~105K FMA songs (source-separated, randomly FX-augmented); reports best spectral fidelity and highest listener preference on paired style transfer, "over 4000 times faster than iterative optimization" (numbers not extracted) — [arXiv 2607.15634](https://arxiv.org/abs/2607.15634)
- Caveat: SCNet separator third-party licence file `stemfx/third_party/LICENSE.msst` exists — not checked — [repo tree](https://github.com/barry-mir/stemfx)

**ITO-Master (Koo, Martínez-Ramírez et al., Sony — ISMIR 2025)** — mastering, not mixing
- https://github.com/SonyResearch/ITO-Master — **CC BY-NC 4.0**, last push 2025-07-03; `pip install ito_master`; single stereo input + reference; "white_box" model + inference-time optimisation (AudioFeatureLoss or CLAP text prompt, e.g. 100 steps); HF Space demo — [README](https://github.com/SonyResearch/ITO-Master), [LICENSE](https://github.com/SonyResearch/ITO-Master/blob/master/LICENSE)

**Fx-Encoder++ (Yeh, Koo, Martínez-Ramírez et al. — ISMIR 2025)** — analysis tool, not a mixer
- https://github.com/SonyResearch/Fx-Encoder_PlusPlus — **CC BY-NC 4.0**; weights https://huggingface.co/yytung/fxencoder-plusplus; extracts an effects embedding of a mix or of one instrument inside a mix (audio or text query, e.g. "the sound of vocals") — usable as a style loss/target — [README](https://github.com/SonyResearch/Fx-Encoder_PlusPlus)

**Differentiable effect libraries (for doing our own parameter fit)**
- dasp-pytorch — **Apache-2.0**, 304 stars, last push 2023-12-04; differentiable parametric EQ, compressor, `noise_shaped_reverberation`, distortion, stereo processing; Diff-MST depends on it — [repo](https://github.com/csteinmetz1/dasp-pytorch), [Diff-MST PR #26](https://github.com/sai-soum/Diff-MST/pull/26)
- GRAFX (Lee et al.) — **Apache-2.0**, 141 stars, **last push 2026-06-29** (most actively maintained in this list); `pip install grafx`; audio processing graphs in PyTorch — [repo](https://github.com/sh-lee97/grafx), [arXiv 2408.03204](https://www.arxiv.org/abs/2408.03204)
- "Searching for Music Mixing Graphs: A Pruning Approach" (DAFx 2024) — code https://github.com/sh-lee97/grafx-prune, **no licence file** (GitHub reports none; all rights reserved by default), last push 2025-02-13; processors: EQ, compressor, noise gate, stereo imager, gain/pan, multitap delay, reverb; **needs the target mix of the same song** (reverse-engineers a mix from dry tracks + its mix), uses MedleyDB and Mixing Secrets data — [demo page](https://sh-lee97.github.io/grafx-prune/), [repo tree](https://github.com/sh-lee97/grafx-prune)

**LLM-based**
- LLM2Fx (Doh et al., KAIST/Sony, WASPAA 2025): LLM predicts EQ and reverb parameters as JSON from a text description, single track, no training — [arXiv 2505.20770](https://arxiv.org/abs/2505.20770)
- MixAssist (Clemens & Marasović, COLM 2025): audio-language dataset of 431 expert/amateur mixing conversation turns; fine-tuned Qwen-Audio gives mixing *advice*, not parameters — [arXiv 2507.06329](https://arxiv.org/abs/2507.06329), [Zenodo](https://zenodo.org/records/15848443)

### Inferences
- For "16 stems + reference -> console parameters" none is ready to download and run: Diff-MST is the right design but lacks weights (we would need to train it ourselves on MedleyDB/Cambridge — non-commercial code licence still applies). StemFX is downloadable and MIT, but would require collapsing our 16 channels into 4 groups and translating sox-style effects into LSP/x42 settings; outputs are per-group, not per-channel.
- A no-pretrained-model route fits our LV2 engine best: build our own console in GRAFX or dasp-pytorch (Apache-2.0) matching our real chain (HPF, 4–6 band PEQ, compressor, gain, pan, reverb send, master), then optimise its parameters on our recorded stems so the mix's features (loudness balance, spectrum, dynamics, stereo width; Fx-Encoder++ embedding only for non-commercial experiments) match the reference. This is the Diff-MST "inference-time optimisation" idea without its weights, and directly yields copyable numbers.
- Diff-MST's EQ ranges start at 80 Hz with bands mostly above 2 kHz — weak for low-mid work (250 Hz mud, kick/bass), so even its output would need our own ranges.

### Gaps
- No Diff-MST checkpoint location found anywhere (not on Zenodo/HF/releases); whether the authors would share on request is unknown.
- StemFX numeric listening-test and retrieval numbers not extracted; the exact list of effects/parameters the decoder can emit not checked.
- grafx-prune "Mixing Secrets" dataset details and optimisation times not found.

## 2. Licences — what is commercial-safe?

### Takeaway
Commercially usable: **automix-toolkit (Apache-2.0, weights Apache-2.0), dasp-pytorch (Apache-2.0), GRAFX (Apache-2.0), FxNorm-Automix (MIT, weights in repo), StemFX (MIT code + MIT weights), multiafx (MIT), pyloudnorm (MIT)**. Non-commercial: **Diff-MST (CC BY-NC-SA 4.0), DeepAFx-ST (Adobe research-only), MEGAMI (CC BY-NC-SA 4.0), ITO-Master (CC BY-NC 4.0), Fx-Encoder++ (CC BY-NC 4.0)**. grafx-prune has **no licence** (not usable without permission).

### Cited Findings
- Diff-MST: CC-BY-NC-SA 4.0 — [README](https://github.com/sai-soum/Diff-MST)
- DeepAFx-ST: "noncommercial research purposes only… do not include… development of commercial products" — [LICENSE](https://github.com/adobe-research/DeepAFx-ST/blob/main/LICENSE)
- FxNorm-Automix: MIT, Sony Group Corporation 2022 — [LICENSE.md](https://github.com/sony/fxnorm-automix/blob/main/LICENSE.md)
- automix-toolkit: Apache-2.0 code; HF weights card apache-2.0 — [repo](https://github.com/csteinmetz1/automix-toolkit), [HF](https://huggingface.co/csteinmetz1/automix-toolkit)
- dasp-pytorch Apache-2.0; GRAFX Apache-2.0 — [dasp](https://github.com/csteinmetz1/dasp-pytorch), [grafx](https://github.com/sh-lee97/grafx)
- MEGAMI CC BY-NC-SA 4.0, commercial licensing via Sony contact — [README](https://github.com/SonyResearch/MEGAMI)
- ITO-Master CC BY-NC 4.0 — [LICENSE](https://github.com/SonyResearch/ITO-Master/blob/master/LICENSE); Fx-Encoder++ CC BY-NC 4.0 — [README](https://github.com/SonyResearch/Fx-Encoder_PlusPlus)
- StemFX code MIT, paper CC BY 4.0, HF weights MIT — [README](https://github.com/barry-mir/stemfx), [HF](https://huggingface.co/barry-mir/stemfx-bsfilm)
- grafx-prune: GitHub reports no licence — [GitHub API](https://api.github.com/repos/sh-lee97/grafx-prune)

### Inferences
- A monetised YouTube/Twitch stream is a commercial use; NC-licensed models (Diff-MST, MEGAMI, DeepAFx-ST, ITO-Master, Fx-Encoder++) should only be used for private experiments, not in the live product.
- Training datasets carry their own terms (MedleyDB, Cambridge-MT, MUSDB18 are research/non-commercial in many cases) — weights trained on them (e.g. automix-toolkit's medleydb-16-dmc) may inherit restrictions even when the weight file says Apache-2.0. Not legally verified.

### Gaps
- Dataset licences behind each weight file not verified individually.
- SCNet (bundled by StemFX) licence not checked.

## 3. Hardware / time for ~16 tracks × 1–5 min

### Takeaway
No paper in this list reports inference time or memory for a full song. All are offline PyTorch models working on ~10–12 s windows at 44.1 kHz; none is designed for real-time. Since parameters are static per song, only a few representative windows need processing, so a one-off run before or between shows (on CPU or the show server's GPU) is plausible; live use would be as periodic parameter suggestions, not in the audio path.

### Cited Findings
- Diff-MST: ~190M params, 10 s windows, inference time not reported — [arXiv](https://arxiv.org/html/2407.08889v1), [eval_all_combo.py](https://github.com/sai-soum/Diff-MST/blob/main/scripts/eval_all_combo.py)
- MEGAMI: ~70M-param diffusion transformer + ~9M TCN, 11.9 s segments, compute not reported — [arXiv](https://arxiv.org/html/2511.08040)
- StemFX: claims >4000× faster than iterative optimisation; 10 s 4-stem segments; examples use `--device cuda:0` — [arXiv](https://arxiv.org/abs/2607.15634), [README](https://github.com/barry-mir/stemfx)
- ITO-Master ITO mode runs e.g. 100 optimisation steps per song — [README](https://github.com/SonyResearch/ITO-Master)
- MR18 USB tap is 48 kHz; all models expect 44.1 kHz (Diff-MST resamples internally) — [eval_all_combo.py](https://github.com/sai-soum/Diff-MST/blob/main/scripts/eval_all_combo.py)

### Inferences
- Rough estimate (unverified): a forward pass of a ~200M-param model on 16 × 10 s is seconds on an RTX 4000 Ada and tens of seconds on a 2-vCPU build server; an own GRAFX/dasp optimisation of a few hundred steps on 16 × 10–30 s would be minutes on GPU, much longer on 2 vCPU. Should be benchmarked before relying on it.

### Gaps
- No measured runtimes or memory numbers exist in the sources for any system.

## 4. Quality evidence vs human mixes (especially live / funk-soul material)

### Takeaway
Evidence is thin. Diff-MST has no listening test. FxNorm-Automix's authors themselves say systems remain "far from" pro mixes. MEGAMI (non-commercial, audio-only) is the only one claiming "approaching human-level" in a 12-listener test with wide, song-dependent results. No system was evaluated on live recordings with bleed or on funk/soul; training is studio multitracks (MedleyDB, Cambridge-MT, MUSDB, FMA, internal Sony).

### Cited Findings
- Diff-MST: objective only (AF loss, FAD); best AF-16 0.168 vs human mixes 0.218 / 0.180 on 3 songs — [arXiv](https://arxiv.org/html/2407.08889v1)
- FxNorm-Automix: listening test with experienced engineers; "still far from professional human-made mixes" — [arXiv 2208.11428](https://arxiv.org/abs/2208.11428)
- MEGAMI: 12 listeners, 7 genres incl. Disco/Grunge/BritPop; near/above human on some songs; equal-loudness surprisingly good on Disco; artifact-prone baselines scored low — [arXiv](https://arxiv.org/html/2511.08040)
- AES 2025 two-stage (rule-based + Diff-MST): MUSHRA vs human expert mixes in-genre, beats LUFS baselines; references were rock — [AES2025-materials](https://github.com/SparrowReivun/AES2025-materials)
- StemFX: "highest listener preference" for paired style transfer (details not extracted) — [arXiv 2607.15634](https://arxiv.org/abs/2607.15634)
- DMC: perceptual evaluation with audio engineers beats baselines — [arXiv 2010.10291](https://arxiv.org/abs/2010.10291)

### Inferences
- Live stage bleed (overheads, vocal mics picking up drums) breaks the "clean dry stem" assumption all these models rely on; parameter predictions for our 16 channels should be treated as a starting suggestion that Claude/the user approves, inside our existing safe bounds — consistent with the approved "Mix F" approach rather than replacing it.

### Gaps
- No study found on live-band or funk/soul/R&B multitracks for any automix model.
- No head-to-head of Diff-MST vs MEGAMI vs StemFX.
