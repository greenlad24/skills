# LLM-driven, agentic, reference-conditioned and rule-based automatic mixing (as of Oct 2026)

Scope: options that could drive a live mixing engine's per-channel gain, pan, EQ, compression and reverb sends, plus how to judge mixes without an unreliable audio-LLM. Every claim has a source. Anything unverified is flagged.

## Q1. Which approaches exist, how do they decide settings, and what is released? (profiles)

### Takeaway
Most LLM-for-mixing work in 2025–2026 is about **single-source effect parameters** (EQ/reverb/Fx-chains), not full multitrack balance, and the strongest systems (LLM2Fx-Tools, MEGAMI, StemFX, sequential stem blending) have **no confirmed code or weights release**. What is actually usable today: Diff-MST code (non-commercial license), automix-toolkit checkpoints (Hugging Face), RIME/POEMS agent code, and the LLM2Fx *recipe* (prompting a general LLM with DSP code + features + few-shot examples), which needs no model release because it runs on any LLM, including Claude.

### Cited Findings

**LLM2Fx: "Can Large Language Models Predict Audio Effects Parameters from Natural Language?" (Doh et al., KAIST + Sony, WASPAA 2025, arXiv 2505.20770)**
- What: zero-shot text-to-parameters; the LLM outputs JSON for a 6-band parametric EQ (18 params) and a noise-shaped reverb (25 params) from the dasp-pytorch library, applied to dry guitar/drum/piano clips — [arXiv HTML v2](https://arxiv.org/html/2505.20770v2)
- LLMs tested: GPT-4o, Mistral-7B-Instruct-v0.3, Llama 3.2 1B/3B, Llama 3.1 8B, Llama 3.3 70B — [arXiv](https://arxiv.org/html/2505.20770v2)
- How it decides: in-context information — five few-shot examples per Fx type, the DSP Python code, and audio features (RMS, spectral centroid, RT60) — [arXiv](https://arxiv.org/html/2505.20770v2)
- Evaluation: MMD on FXenc embeddings vs. SocialFX-Eval targets (7 EQ words, 19 reverb words), lower is better. Avg MMD: random 0.53 (EQ) / 0.75 (reverb); Text2FX-style CLAP optimisation (Chu et al.) 0.55 / 0.45; GPT-4o zero-shot 0.22 / 0.70; Mistral-7B with all context 0.22 / 0.27; ground-truth floor 0.09 / 0.05. DSP code alone hurt reverb (0.77) — [arXiv](https://arxiv.org/html/2505.20770v2)
- No listening test, no latency reported; demo at https://seungheondoh.github.io/llm2fx-demo/ ; **no LLM2Fx code repository found** (relies on public https://github.com/csteinmetz1/dasp-pytorch) — [arXiv](https://arxiv.org/html/2505.20770v2); [Sony AI page](https://ai.sony/publications/can-large-language-models-predict-audio-effects-parameters-from-natural-language)

**LLM2Fx-Tools: Tool Calling for Music Post-Production (Doh et al., KAIST + Sony AI, ICLR 2026, arXiv 2512.01559)**
- What: an audio-LLM that picks effect types, their order and parameters (an "Fx-chain") via chain-of-thought + tool calls; also does reference style transfer — [ICLR poster](https://iclr.cc/virtual/2026/poster/10009732); [Sony AI](https://www.ai.sony/publications/LLM2Fx-Tools-Tool-Calling-For-Music-Post-Production/)
- Model: Qwen3-4B with LoRA (r=128), Fx-Encoder++ audio encoder, 32-query transformer adapter — [arXiv v2](https://arxiv.org/html/2512.01559v2)
- Tools: 9 modules / 26 params — Pedalboard compressor, distortion, reverb, delay, limiter, gain; custom 3-band EQ, stereo widener, panner — [arXiv v2](https://arxiv.org/html/2512.01559v2)
- Inputs: text instruction + reference audio + pseudo-dry audio; outputs CoT, tool calls, NL reply. Dataset LP-Fx (99,900 train / 900 test dialogues from MedleyDB, generated with Gemini 2.5 Flash/Flash-lite, filtered by Gemini 2.5 Pro) — [arXiv v2](https://arxiv.org/html/2512.01559v2)
- Quality evidence: MUSHRA (16 listeners): hidden ref 81.5, **LLM2Fx-Tools 62.8**, Gemini 2.5 Flash 56.5, DeepAFx-ST 54.8, no Fx 39.1, MultiTask 34.9, Regression 16.2. Reverse-engineering accuracy 80% vs Gemini 2.5 Flash 78% — [arXiv v2](https://arxiv.org/html/2512.01559v2)
- Limits: single-instrument sources only, untested on unseen effect modules; latency not reported; **code/weights/dataset release not stated**; paper is CC BY-NC-SA 4.0; demo https://seungheondoh.github.io/llm2fx-tools-demo/ — [arXiv v2](https://arxiv.org/html/2512.01559v2)
- Follow-up InstructFX2FX (DAFx26 demo): notes LLM2Fx systems are single-shot and proposes LLM picks effects + initial params, then CLAP-guided optimisation on rendered audio refines them — [DAFx26 demo 74](https://www.dafx.de/paper-archive/2026/papers/DAFx26_demo_74.pdf) (details not read in full)

**Text2FX (Chu, O'Reilly, Barnett, Pardo, Northwestern, ICASSP 2025, arXiv 2409.18847)**
- What: per-clip optimisation of differentiable EQ/reverb params so the CLAP embedding of the output matches a text prompt; no training; includes a listener study — [arXiv](https://arxiv.org/html/2409.18847v2)
- Code/demos: project page anniejchu.github.io/text2fx (no GitHub repo confirmed) — [arXiv](https://arxiv.org/html/2409.18847v2)
- In LLM2Fx's benchmark this CLAP-optimisation approach scored no better than random on EQ (0.55 vs 0.53 MMD) — [LLM2Fx](https://arxiv.org/html/2505.20770v2)

**MixAssist (Clemens & Marasović, Univ. of Utah, COLM 2025, arXiv 2507.06329)**
- What: audio-grounded dataset of expert/amateur mixing conversations: 431 turns, 7 sessions, 12 producers; audio-LLMs (Qwen-Audio family) fine-tuned to give mixing *advice* (text), not parameters — [arXiv](https://arxiv.org/abs/2507.06329)
- Results: Qwen significantly better than other tested models (LLM-as-judge + human expert comparisons); users flagged weak audio understanding and wanted explainable, controllable tools — [arXiv](https://arxiv.org/pdf/2507.06329)
- Release: http://mclemcrew.github.io/mixassist-website ; audio on [Zenodo 15848443](https://zenodo.org/records/15848443); paper CC BY 4.0, dataset licence not stated — [arXiv](https://arxiv.org/abs/2507.06329)
- A third-party Carla MCP server repo (agrathwohl/carla-mcp-server) ships a MixAssist setup guide but describes the dataset differently (640 conversations, different title) — trust the paper — [glama listing](https://glama.ai/mcp/servers/@agrathwohl/carla-mcp-server/blob/8be3a8a52c0edf77aba47a61620885ab4a3599a2/MIXASSIST_SETUP.md). Note: this is an MCP server for the **Carla** plugin host (our show-server host); not evaluated here.

**RIME / POEMS (Schaffer & Singh, Dartmouth, arXiv 2607.19605, 2026)**
- What: tool-calling audio agents doing music post-production; POEMS exposes 20+ operators: gain dB, normalisation, fades, constant-power pan, HPF/LPF/shelves/peaking EQ, compressor, limiter, gate, de-esser, reverb, delay, chorus, phaser, distortion, pitch tools, Demucs 6-stem separation — [arXiv](https://arxiv.org/html/2607.19605)
- How it decides: agent listens, plans tool use, re-checks audio each step, max 20 steps. Zero-shot agents GPT-Audio-Mini, Gemini 3 Flash, Gemma 3n; Gemma 3n LoRA SFT on 3,000 triplets — [arXiv](https://arxiv.org/html/2607.19605)
- Results: GPT-Audio-Mini best on FAD/KAD and edit similarity (0.637); Gemini 3 Flash trailed (Graph F1 0.634, edit sim 0.528); 95.9% of zero-shot failures hit the step limit; parameter recovery collapses as instructions get vaguer; SFT raised exact-param accuracy 51.4% to 69.0% — [arXiv](https://arxiv.org/html/2607.19605)
- Code: github.com/sahaslab/RIME, demo sahaslab.com/rime; code licence not stated — [arXiv](https://arxiv.org/html/2607.19605)

**Diff-MST: Differentiable Mixing Style Transfer (Vanka et al., QMUL + Steinberg, ISMIR 2024, arXiv 2407.08889)**
- What: transformer controller predicts parameters of a differentiable mixing console (per-track gain/EQ/compression/pan etc. plus master) from raw stems + a **reference song**; outputs readable parameters — [arXiv](https://arxiv.org/pdf/2407.08889); [ISMIR](https://ismir2024program.ismir.net/poster_299.html)
- Evidence: objective metrics only, no listening test; best variant beats baselines — [arXiv](https://arxiv.org/html/2407.08889v1)
- Code: https://github.com/sai-soum/Diff-MST — **CC-BY-NC-SA 4.0 (no commercial use)**; weights not clearly provided (you supply `ckpt_path`); single NVIDIA GPU for training; 226 commits, 66 stars — [GitHub](https://github.com/sai-soum/Diff-MST)

**Differentiable Mixing Console (DMC) + automix-toolkit (Steinmetz et al., ICASSP 2021; toolkit by csteinmetz1)**
- DMC: permutation-invariant, any number of inputs, outputs human-readable mixing parameters — [arXiv 2010.10291](https://arxiv.org/pdf/2010.10291)
- automix-toolkit: code + pretrained checkpoints on Hugging Face (csteinmetz1/automix-toolkit, e.g. enst-drums-dmc.ckpt, enst-drums-mixwaveunet.ckpt — drums only); inference on a folder of stems; ~98 stars — [ecosyste.ms](https://science.ecosyste.ms/projects/198271). Licence not verified.
- FxNorm-automix (Martínez-Ramírez et al., Sony, ISMIR 2022): trains on wet multitracks via effect normalisation; code at https://marco-martinez-sony.github.io/FxNorm-automix/ — [ISMIR 2022](https://ismir2022program.ismir.net/poster_11.html). Licence not verified.

**MEGAMI (Moliner, Martínez-Ramírez, Koo, ... Mitsufuji; Sony + Aalto; ICASSP 2026, arXiv 2511.08040)**
- Generative model of per-track effect embeddings conditioned on dry tracks; permutation-equivariant; listening tests "approaching human-level quality across diverse genres" — [arXiv](https://arxiv.org/abs/2511.08040)
- No code/weights found; whether it outputs parameters or audio not stated on abstract page — [arXiv](https://arxiv.org/abs/2511.08040)

**Other 2026 work (no code confirmed)**
- StemFX (Yang lab, ISMIR 2026, 2607.15634): autoregressive per-stem FX-chain prediction; MultiAFx toolkit unifies 85 effects from 7 Python libs; >4000x faster than iterative optimisation — [arXiv](https://arxiv.org/abs/2607.15634)
- Sequential Stem Blending (Yeh, Chan, Hung, Yang, 2608.05506): latent flow matching, blends one stem at a time into a growing submix; demo sequential-mixing-demo.vercel.app — [arXiv](https://arxiv.org/abs/2608.05506)
- Two-stage mixing analysis (Shi ... Reiss, ISMIR 2026, 2609.02835): two-stage (group then inter-group) significantly beats single-stage in listening tests; **bad grouping hurts most**, loudness errors weaker — code/audio https://sparrowreivun.github.io/TwoStageMixingAnalysis/ — [arXiv](https://arxiv.org/abs/2609.02835)
- TimberAgent (2603.09332): retrieval-guided executable effect control — only reference list seen, **unverified** — [arXiv](https://arxiv.org/pdf/2603.09332)

**Classic knowledge/rule-based intelligent mixing**
- De Man & Reiss "Knowledge-Engineered Autonomous Mixing System" (AES 135, 2013): rules from mixing textbooks + instrument tags + low-level features; compared in listening test with feature-only automixers and human engineers — [AES](https://aes2.org/publications/elibrary-page/?id=17011); [academia.edu](https://www.academia.edu/31481042/A_Knowledge_Engineered_Autonomous_Mixing_System)
- Review of a decade of automatic mixing (De Man, Reiss, Stables, WIMP 2017) — [BCU open access](https://www.open-access.bcu.ac.uk/4968/1/WIMP2017_DeManEtAl.pdf)
- Mix Evaluation Dataset (DAFx 2017): engineer mixes + ratings, no reference given to listeners; 6 of 10 songs' raw tracks CC BY 4.0 — [DAFx17](https://www.dafx17.eca.ed.ac.uk/papers/DAFx17_paper_49.pdf)
- Dugan automixing: only commercial (Waves Dugan Automixer, ~$500 native / $750 SoundGrid); no open-source implementation found — [Dugan brochure](https://dandugan.com/Assets/brochures%20&%20price%20list/Waves-Dugan-Automixer-Brochure.pdf)

### Inferences
- The LLM2Fx finding transfers directly to us: a general LLM (Claude) given the plugin's actual parameter code, measured features and a few examples beats a random/CLAP baseline at EQ. Our approach (Claude as mixer within bounds) matches the published recipe; no model to download.
- Nobody has published an open, commercially licensed model that outputs full multitrack console settings for a live band. Diff-MST is the nearest but is non-commercial and studio/offline oriented.
- RIME's results (agents running out of steps, poor parameter recovery for vague instructions) argue for giving Claude concrete numeric targets, not vague goals.

### Gaps
- Licences for automix-toolkit, FxNorm-automix, RIME code and MixAssist data were not confirmed.
- SAFE plugins (semantic audio feature extraction) and open cross-adaptive gain/pan implementations: no source found in this pass.
- No published latency figures for LLM2Fx-Tools, MEGAMI or StemFX inference.

## Q2. Which can run live on CPU (seconds to minutes), which are offline? Which beat baselines in listening tests?

### Takeaway
Live-capable on CPU: rule/knowledge-based mixing and text-only LLM prompting (LLM2Fx-style, just an API call). Probably fast enough: single forward-pass parameter estimators (DMC, Diff-MST, StemFX), but GPU-trained and not benchmarked on CPU. Offline: Text2FX (per-clip optimisation), generative MEGAMI and flow-matching stem blending, multi-step audio agents (RIME). Listening-test winners over baselines: LLM2Fx-Tools (MUSHRA 62.8 vs 54.8 DeepAFx-ST, 39.1 no-Fx), MEGAMI ("approaching human"), two-stage mixing, KEAMS. Diff-MST and LLM2Fx have **no** listening test.

### Cited Findings
- LLM2Fx-Tools MUSHRA: 62.8 vs Gemini 2.5 Flash 56.5, DeepAFx-ST 54.8, no-Fx 39.1 — [arXiv](https://arxiv.org/html/2512.01559v2)
- MEGAMI listening tests approach human-level — [arXiv](https://arxiv.org/abs/2511.08040)
- Two-stage systems significantly beat single-stage in 3 listening experiments — [arXiv](https://arxiv.org/abs/2609.02835)
- Diff-MST: objective evaluation only — [arXiv](https://arxiv.org/html/2407.08889v1)
- LLM2Fx: MMD only, no listening test — [arXiv](https://arxiv.org/html/2505.20770v2)
- StemFX >4000x faster than iterative optimisation — [arXiv](https://arxiv.org/abs/2607.15634)
- Text2FX is single-instance optimisation (iterative per clip) — [arXiv](https://arxiv.org/html/2409.18847v2)
- RIME agents take up to 20 tool steps with audio re-checks — [arXiv](https://arxiv.org/html/2607.19605)
- Diff-MST training uses one NVIDIA GPU — [GitHub](https://github.com/sai-soum/Diff-MST)

### Inferences
- For our show server (GPU droplet) a forward-pass model would run in well under a second per window, but only if weights exist and licensing allows commercial streams; today that is not the case for the best ones.
- A practical design: rules + deterministic controller for fast moves, Claude for slower decisions using LLM2Fx-style context (plugin code, features, few-shot examples of approved settings, e.g. the user's "Mix F"). This is inferred, not tested in any paper on live sound.
- None of the listed papers addresses live sound (bleed, feedback, changing line-ups); all are studio stems.

### Gaps
- No paper found evaluating any of these systems on live multitrack recordings with heavy bleed.
- No CPU inference timing for DMC/Diff-MST.

## Q3. How reliable are LLM/audio-LLM judges, and what objective metrics can replace them for A/B?

### Takeaway
Audio-LLM judges have documented, systematic **position bias**, worst when the two clips are hard to tell apart — exactly our "Gemini always picks Y on identical clips" result. Mitigate by judging both orders and counting only order-consistent verdicts, or replace the judge with objective distances to a reference mix (multi-resolution STFT, audio-feature distance, FxEnc/AFx-Rep embedding similarity, FAD/KAD) plus a reference-free learned score (Audiobox-Aesthetics Production Quality).

### Cited Findings
- AudioJudge (2507.12705): GPT-4o-Audio and Gemini-2.5-Flash favoured the first position on some tasks; position bias grows as the quality gap between clips narrows; method is to run both orders — [arXiv](https://arxiv.org/pdf/2507.12705); summary that judges pick the first clip when choice is hard and a jury of judges reached up to 91% agreement with humans — [SCBX](https://www.scbx.com/en/?p=36635) (secondary)
- ParaPairAudioBench (2606.24648): every model showed systematic position bias; SpeechJudge ~29-point gap favouring B, Qwen2.5-Omni favoured A; Gemini 2.5 Flash best overall — [arXiv](https://arxiv.org/pdf/2606.24648)
- CMI-RewardBench (music reward models): swapping order shifted win rates noticeably; they kept only order-consistent labels — [arXiv](https://arxiv.org/pdf/2603.00610)
- Speech-quality reward benchmark randomly swaps order to reduce bias — [arXiv](https://arxiv.org/pdf/2510.00743)
- Music QA benchmarks often test reasoning more than perception, so models may score well without really hearing — [Are you really listening?](https://arxiv.org/pdf/2504.00369)
- MixAssist authors: LLM-as-judge may not capture nuanced human preference; they added human studies — [arXiv](https://arxiv.org/pdf/2507.06329)
- No dedicated audio-LLM mix-quality benchmark found; SongBench includes "mixing" as one of seven song-quality components — [Qwen-Audio-3.0-Gen report](https://arxiv.org/pdf/2607.27011)
- Objective metrics used in literature: multi-resolution STFT on L/R and M/S, audio-feature (AF) distance, AFx-Rep and FxEnc embedding similarity (LLM2Fx-Tools) — [arXiv](https://arxiv.org/html/2512.01559v2); MRSTFT and AudioFeatureLoss (Diff-MST) — [GitHub](https://github.com/sai-soum/Diff-MST); MMD on FXenc embeddings (LLM2Fx) — [arXiv](https://arxiv.org/html/2505.20770v2); FAD/KAD (RIME) — [arXiv](https://arxiv.org/html/2607.19605); "distributional metrics" (MEGAMI) — [arXiv](https://arxiv.org/abs/2511.08040)
- Reference-free learned score: Meta Audiobox-Aesthetics predicts Production Quality, Production Complexity, Content Enjoyment, Content Usefulness (~1–10); `pip install audiobox_aesthetics`; mostly CC-BY 4.0 (some MIT code); checkpoint licence not separately stated — [GitHub](https://github.com/facebookresearch/audiobox-aesthetics)

### Inferences
- For A/B: (1) sanity check — if A and B are identical, the decision must be "tie" (a deterministic metric gives that for free; an LLM did not); (2) score each candidate by distance to an approved reference (the user's approved mix) on loudness-matched audio using MRSTFT + AF distance + embedding similarity; (3) add Audiobox PQ as a reference-free tiebreaker; (4) if an audio-LLM is used at all, ask in both orders and accept only consistent answers.
- Loudness-match before any comparison; louder usually wins with humans and models (general practice, not sourced here).

### Gaps
- No study validating Audiobox-Aesthetics PQ against mix-engineer preferences on live band mixes.
- No public pairwise mix-preference dataset found for training a mix-specific judge.
