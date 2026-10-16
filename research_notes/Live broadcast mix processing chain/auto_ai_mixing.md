# Automatic / Intelligent / AI Mixing for Live Music, and Safe Agent Control of a Live Mix

Context: 16-ch raw multitrack from a Midas M18-class (MR18 / X-Air family) mixer streamed to a cloud server, mixed in real time for a YouTube live stream of a Neo-Soul/Funk band. A Claude agent adjusts parameters every few seconds and learns across shows.

Research caveats: several primary sources (arxiv.org, roexaudio.com, bcu.ac.uk) were not fetchable from this environment (DNS failures), so some findings rely on search-result abstracts rather than full text. Those are flagged.

## Q1. Intelligent Music Production (IMP) literature: what has been automated and what runs in real time

### Takeaway
Rule-based, cross-adaptive methods from Reiss's group at QMUL/C4DM (Perez-Gonzalez, Hafezi, De Man) already ran in real time for gain/fader, EQ and masking reduction more than 10 years ago. Neural and differentiable approaches (Steinmetz DMC, Diff-MST, LLM2Fx-Tools) are mostly offline, look ahead over long windows, and output interpretable parameters. The first "zero-latency" neural live mixer (AiLive Mixer, arXiv 2026) predicts only per-channel gains. For a live agent, use cheap real-time DSP for the fast loops and keep neural or LLM reasoning in a slow supervisory loop that sets parameters.

### Cited Findings
- **Automatic gain/fader for live mixing (Perez-Gonzalez & Reiss, WASPAA 2009):**
  - It is a cross-adaptive device.
  - It compares each input's loudness with the overall stereo mix loudness, measured in real time with accumulative statistics.
  - It maps those loudness indicators to channel gains.
  - [IEEE Xplore](https://ieeexplore.ieee.org/document/5346498)
- **Automatic EQ of multichannel audio using cross-adaptive methods (Perez-Gonzalez & Reiss, AES 127th Conv., 2009):**
  - It aims for equal average perceptual loudness across frequencies.
  - It targets live mixing and shorter setup time.
  - [AES E-Library](https://aes2.org/publications/elibrary-page/?id=15026)
- **Later fader automation from Reiss's group (DAFx 2012):** it uses EBU R128 loudness, with a cross-adaptive process that brings each track to a time-varying average loudness. [DAFx 2012 paper](https://www.dafx.de/paper-archive/2012/papers/dafx12_submission_6.pdf)
- **Cross-adaptive effects review (Reiss & Brandtsegg, Frontiers in Digital Humanities, 2018):** covers effects with many inputs and outputs, including automatic mixing and live performance. [Frontiers](https://www.frontiersin.org/articles/10.3389/fdigh.2018.00017/pdf)
- **Masking-reduction EQ (Hafezi & Reiss, JAES vol. 63 no. 5, 2015):**
  - The authors built a simplified masking measure and implemented both an offline and a real-time autonomous multitrack EQ.
  - In listening tests, the autonomous systems reduced both perceived and objective masking.
  - The offline semi-autonomous version beat an amateur mix and came close to a professional mix, with only one user parameter adjusted.
  - The authors found that existing objective masking measures correlate poorly with perceived masking in multitrack music.
  - [AES E-Library](https://aes2.org/publications/elibrary-page/?id=17637); [summary](https://labs.sonicfield.org/library/autonomous-multitrack-equalization-based-on-masking-reduction-Hafezi-2015)
- **Hafezi/Reiss EQ mechanism (as described in a 2024 SMC paper):** it modulates a set of 5-band parametric EQs on each track to minimise masking interactions, and needs MIMO routing. [SMC2024](https://smcnetwork.org/smc2024/papers/SMC2024_paper_id126.pdf)
- **Masking minimisation with subgroups (Ronan et al., 2018):** uses a masking metric inspired by the MPEG psychoacoustic model and tests subgrouping. [arXiv 1803.09960](https://arxiv.org/pdf/1803.09960)
- **"Ten Years of Automatic Mixing" (De Man et al., WIMP 2017):** reports a trend toward machine learning and increasingly complex systems. [BCU open access](https://www.open-access.bcu.ac.uk/4968/1/WIMP2017_DeManEtAl.pdf) (full text not fetched)
- **Reference book:** *Intelligent Music Production* (De Man, Stables, Reiss; Routledge/Focal 2019). Chapters cover:
  - understanding audio effects and the mix
  - data collection
  - perceptual evaluation
  - IMP systems, processes and interfaces
  - [Routledge](https://www.routledge.com/Intelligent-Music-Production/Man-Stables-Reiss/p/book/9781138055193)
- **Differentiable Mixing Console (Steinmetz, Pons, Pascual, Serrà; ICASSP 2021):**
  - It learns mixing conventions from real multitrack data at the waveform level, without access to the original mixing parameters.
  - It uses pre-trained sub-networks, weight sharing and a sum/difference stereo loss.
  - It outputs human-readable mixing parameters that users can refine.
  - [arXiv 2010.10291](https://arxiv.org/abs/2010.10291)
- **Diff-MST (Vanka, Steinmetz, Rolland, Reiss, Fazekas; ISMIR 2024):**
  - Architecture: a differentiable mixing console, a transformer controller and an audio production style loss.
  - Given raw tracks and a reference song, it estimates parameters for each channel strip (gain, pan, EQ, compression) plus a master bus.
  - It accepts any number of tracks without source labels.
  - It uses differentiable effects from dasp-pytorch.
  - The authors report that their best configuration beat the baselines on objective metrics.
  - [arXiv 2407.08889](https://arxiv.org/abs/2407.08889); [ISMIR poster](https://ismir2024program.ismir.net/poster_299.html)
- **AiLive Mixer (arXiv 2603.15995, 2026):**
  - Described as the first end-to-end deep learning mixer built for live performance.
  - It starts from the offline DMC model, which has an inherent latency of 975 ms.
  - The authors modify it to handle inter-channel bleed and to run at zero latency.
  - It predicts mono gains per channel only.
  - Source: search abstract only; full text not fetched, and the latency claim is unverified. [arXiv 2603.15995](https://arxiv.org/html/2603.15995)
- **LLM2Fx-Tools (Sony AI / KAIST; arXiv Dec 2025, ICLR 2026):**
  - An LLM uses tool calling, with chain-of-thought planning, to infer an effects chain (effect order and parameters) from pairs of unprocessed and processed audio.
  - It ships with an instruction-following dataset of tool calls.
  - This is the closest published precedent for an LLM driving audio-effect parameters through tools.
  - [Sony AI](https://ai.sony/publications/llm2fx-tools-tool-calling-for-music-post-production); [ICLR 2026](https://iclr.cc/virtual/2026/poster/10009732)
- **Real-time low-latency source separation (HS-TasNet, L-Acoustics, 2024):**
  - Reported latency is about 23 ms.
  - It is aimed at live shows and remixing streams.
  - It is relevant for cleaning bleed from stems before analysis.
  - [arXiv 2402.17701](https://arxiv.org/abs/2402.17701); [L-Acoustics PDF](https://www.l-acoustics.com/wp-content/uploads/2024/04/real_time_demixer_2024_04_19.pdf)
- **Automatic feedback suppression:**
  - van Waterschoot & Moonen (JAES 58(11), 2010) describe notch-filter howling suppression (NHS) as two stages: detect the howl, then design the notch.
  - They compare detection criteria including PHPR, PNPR, IMSD and FEP.
  - They note that the NHS literature is mostly patents.
  - [KU Leuven abstract](https://ftp.esat.kuleuven.be/pub/SISTA/vanwaterschoot/abstracts/09-207.html)
  - Related: segmented notch filtering. [Sensors 2021](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8659983/)
- **Dugan gain-sharing automixer:**
  - It sets a maximum total "room gain" and divides it smoothly among all mics according to their input levels, rather than gating them on and off.
  - Patents include continuous NOM (number of open mics) master-gain adjustment.
  - Each doubling of open mics costs about 3 dB of gain-before-feedback: −3 dB with 2 mics, −6 dB with 4, −9 dB with 8.
  - [Wikipedia: Automixer](https://en.wikipedia.org/wiki/Automixer); [Yamaha/Dugan white paper](https://www.bax-shop.be/downloads/products/9000-0008-3692/yamaha_dugan-my16_automixer_interface_kaart_white_paper.pdf); [Symetrix docs](https://composer-docs.symetrix.co/software/toolkit/design-view/automixers/Automixer_Technology.html); [Q-SYS training](https://training.qsc.com/mod/book/view.php?id=1525)

### Inferences
- **What can be automated reliably in real time today:**
  - loudness-based gain riding and fader normalisation
  - Dugan-style gain sharing for speech or vocal mics (useful for backing-vocal mics that are idle much of the time)
  - feedback-notch detection (this matters only for the venue PA; the cloud broadcast mix has no acoustic loop)
  - slow masking-aware EQ
  - bus compression and limiting to a loudness target
- **Less reliable:** creative decisions such as reverb amount, panning aesthetics, and when to feature a solo. Leave these to presets plus agent judgement.
- **Architecture suggestion:**
  1. Run the fast (audio-rate) loops in deterministic DSP on the server: limiter, compressors, gain-sharing, de-essing.
  2. Have the agent act every 2–10 s, only on setpoints such as target levels, EQ moves and the vocal-to-music ratio (VMR) target.
  3. Run neural models such as Diff-MST offline between songs or shows, to propose starting presets from a reference track.
- **Bleed:** live stems contain bleed, especially drums into vocal mics. AiLive Mixer explicitly addresses bleed, which suggests naive per-stem loudness measurement is biased. Gate or source-separate analysis signals before measuring.

### Gaps
- No full-text verification of AiLive Mixer's architecture, results or limitations (arxiv.org was unreachable).
- No evaluation numbers for the real-time variant of the Hafezi/Reiss EQ.
- I found no published real-time version of Diff-MST or DMC beyond AiLive Mixer.
- Wichern et al. and Martínez-Ramírez (automix / FxNorm / music-mixing style transfer) were not researched in this pass.

## Q2. Commercial landscape (as of 2026)

### Takeaway
Commercial "AI mixing" tools are almost all DAW plugins or offline cloud services: iZotope Neutron Mix Assistant, Sonible smart:EQ, RoEx Automix/Tonn API, and Waves Sync Vx. On live consoles, the shipping automation is mostly Dugan-style gain sharing. Behringer/Midas X-Air-class mixers include a Dugan-inspired automix for up to 16 mics. No major console vendor documents a true AI live-mix assistant.

### Cited Findings
- **iZotope Neutron Mix Assistant:**
  - It listens to the session and suggests gain levels for all tracks based on a chosen "mix focus", grouping tracks into Vocals, Bass, Drums and Musical.
  - Further refinement happens in Visual Mixer, Relay or the DAW faders.
  - Its Target Library contains AI-analysed tonal profiles for instruments, vocals and drums.
  - Tonal Balance Control 2 compares tracks against genre targets built from thousands of masters.
  - [Splice](https://splice.com/blog/how-to-mix-izotope-neutron); [iZotope](https://www.izotope.com/en/learn/best-of-izotope-bundles)
- **Ozone Master Rebalance:** only passing mentions were found. Ozone's Target Library can "dynamically match the tone" to a reference. [Vintage King](https://vintageking.com/software/izotope-mix-master-bundle-advanced-with-ozone-12-electronic-delivery)
- **Sonible smart:EQ 4:**
  - Cross-channel unmasking works across up to 10 tracks in a group.
  - Each instance runs in one of three modes: Track, Group, or Track+Group.
  - Its AI filter balances tone against instrument, vocal and genre profiles, or a custom reference.
  - Reviewers report it can over-boost the frequency extremes and flatten character if trusted blindly.
  - [Sonible](https://www.sonible.com/?p=485991); [review](https://musicproductionwiki.com/articles/sonible-smart-eq-4-review)
- **RoEx:**
  - Its Tonn API mixes 2–32 tracks, balancing levels, EQ, compression and effects according to a chosen style, with per-track presence, pan and reverb preferences.
  - It has a Python SDK (`roex-python`) that works asynchronously through webhooks.
  - Consumer Automix limits tracks to 8 minutes. This is offline file processing, not live.
  - [Tonn portal](https://tonn-portal.roexaudio.com); [PyPI](https://pypi.org/project/roex-python/); [RoEx multitrack](https://www.roexaudio.com/multitrack-mixing)
- **Waves Sync Vx:** a DAW plugin (with ARA) that aligns the time and pitch of vocal doubles to a lead. It is not a live console tool. [MusicTech](https://musictech.com/products/waves-sync-vx-vocal-alignment-plugin)
- **Waves eMotion LV1:** a live mixer with a 32-bit floating-point engine at 44.1–96 kHz. No AI automix was documented in the results. [Waves](https://www.waves.com/mixers-racks/emotion-lv1-16-channels)
- **Behringer X18 / X-Air:** gain-sharing automix "inspired by the Dan Dugan automix system" for up to 16 live mics, without gating artifacts. One spec sheet listed it as "future firmware". [Gear4music](https://www.gear4music.be/en/PA-DJ-and-Lighting/Behringer-X18-X-AIR-Digital-iPad-Tablet-Mixer/XOX)
- **Q-SYS:** its gain-sharing automixer is explicitly based on Dugan's algorithm. It recommends max NOM of 1–3 for conferencing. [Q-SYS](https://training.qsc.com/mod/book/view.php?id=1525)
- **AI on major live consoles:** concrete AI features on Yamaha, DiGiCo and Allen & Heath consoles are poorly documented.
  - Allen & Heath has a university ML research collaboration on automated mixing and feedback. [Royal Commission 1851](https://royalcommission1851.org/smart-mixing-ai-in-live-music-systems)
  - FOH magazine (Feb 2025) was sceptical that AI consoles will arrive soon. [FOH](https://timeless.mydigitalpublication.com/article/FOH-at-Large/4926318/839904/article.html)

### Inferences
- **On-console automix:** the Midas M18 / MR18 is the same platform family as the X18/XR18. It probably has the Dugan-style automix on-board, but this is unverified. Since the band's mix happens in the cloud, implementing gain-sharing server-side is simpler and gives the agent direct control.
- **Vendor tools as references only:** none of the commercial tools exposes a real-time control API suitable for a cloud agent. Their documented behaviours (genre tonal targets, focus-based balance, unmasking groups) are useful design references to replicate in the agent's own DSP.

### Gaps
- Not found or verified:
  - Soundtheory Gullfoss's algorithm
  - Waves Clarity Vx latency or live use
  - Waves F6 automation
  - Mixing Station automation features
  - Masterchannel
  - DiGiCo or Yamaha AI features
- Whether the Midas M18 / MR18 exposes automix over OSC is unverified.

## Q3. Measurable targets

### Takeaway
Usable numeric anchors:
- about −14 LUFS integrated and −1 to −2 dBTP for YouTube (community-derived, not official)
- lead-vocal-to-accompaniment ratio (LAR) of roughly 0–5 dB for band pop, with listener preference higher (about +7.6 dB, and about +10.4 dB for hard-of-hearing listeners)
- genre tonal-balance curves from reference masters

Objective masking metrics are known to correlate poorly with perception, so use them as relative signals, not absolute targets.

### Cited Findings
- **YouTube loudness:**
  - The reference is about −14 LUFS integrated. YouTube turns loud content down but does not turn quiet content up.
  - Recommended true peak is about −1 to −2 dBTP.
  - YouTube does not officially publish the figure.
  - Over-compression raises LUFS, so the platform turns the audio down more.
  - Nothing found confirms normalisation behaviour for live streams specifically.
  - [Wikipedia: Audio normalization](https://en.wikipedia.org/wiki/Audio_normalization); [Youlean](https://youlean.co/?p=30813)
- **LAR study (Gerdes & Siedenburg, JASA-EL 2023):**
  - About 300 Billboard songs from 1946–2020, separated into vocals, bass, drums and other.
  - Mean LAR fell from about 5 dB to about 1 dB until about 1975, then stayed flat.
  - By genre: positive for country, rap and pop; about 0 for rock; negative for metal.
  - Solo artists have higher LAR than bands.
  - [acoustics.org](https://acoustics.org/lead-vocal-tracks-in-popular-music-go-quiet/); [PDF](https://www.geidai.ac.jp/~marui/course_enshu_2024/gerdes_siedenburg_202304.pdf)
- **Preferred LAR (Forum Acusticum 2025):** 7.61 dB for normal-hearing listeners and 10.41 dB for hard-of-hearing listeners. [FA2025](https://dael.euracoustics.org/confs/fa2025/data/articles/000716.pdf)
- **EBU R128 loudness per track:** used as the measure for automatic faders. [DAFx 2012](https://www.dafx.de/paper-archive/2012/papers/dafx12_submission_6.pdf)
- **Masking metrics:**
  - Hafezi & Reiss use a simplified masking measure. Ronan et al. use an MPEG-psychoacoustic-inspired metric.
  - Objective masking measures correlate poorly with perceived masking.
  - [AES 17637](https://aes2.org/publications/elibrary-page/?id=17637); [arXiv 1803.09960](https://arxiv.org/pdf/1803.09960)
- **Genre tonal-balance targets:** iZotope Tonal Balance Control 2 uses curves derived from thousands of masters per genre. [Splice](https://splice.com/blog/how-to-mix-izotope-neutron)

### Inferences
- **Suggested starting targets for Neo-Soul/Funk on YouTube (to tune by ear and from feedback):**
  - Integrated −14 LUFS, ±1 LU, over the song.
  - Short-term loudness band about −16 to −12 LUFS.
  - True peak ≤ −1 dBTP.
  - LAR about +2 to +6 dB. Gerdes found pop is positive and bands lower; listener preference is higher, especially on phone speakers.
  - Bass and kick strong but controlled. Use a funk/R&B tonal curve from 2–3 reference tracks the band likes.
  - Crest factor and PLR (peak-to-loudness ratio) around 8–12 dB to keep groove dynamics. This is a heuristic, not a sourced number.
- **Compute per-stem metrics on gated signals** (only when that source is active) to avoid bleed bias:
  - momentary loudness
  - short-term loudness
  - a spectral centroid / tilt band for each stem

### Gaps
- No sourced genre-specific spectral targets or LAR values for Neo-Soul/Funk.
- No sourced crest-factor norms.
- No official YouTube live-stream loudness documentation.

## Q4. Safe control design for an agent

### Takeaway
Little published literature addresses LLM supervision of a live mix specifically. The design must be assembled from automixer practice and control-engineering principles:
- smooth gain sharing rather than gating
- bounded, slew-limited setpoints applied through DSP smoothing
- hysteresis
- shadow (parallel) mixes for A/B evaluation
- snapshot rollback and human override
- full parameter and metric logging

### Cited Findings
- **Smooth gain distribution beats hard gating:** Dugan-style gain sharing mixes smoothly "without gating artifacts or noise modulation". [Gear4music X18](https://www.gear4music.be/en/PA-DJ-and-Lighting/Behringer-X18-X-AIR-Digital-iPad-Tablet-Mixer/XOX); [Wikipedia](https://en.wikipedia.org/wiki/Automixer)
- **Cap total gain:** use a global NOM/total-gain ceiling as a safety cap against feedback and noise build-up. [Symetrix](https://composer-docs.symetrix.co/software/toolkit/design-view/automixers/Automixer_Technology.html)
- **Interpretable parameters enable oversight:** DMC and Diff-MST deliberately output interpretable console parameters so humans can adjust them afterwards. [arXiv 2010.10291](https://arxiv.org/abs/2010.10291); [arXiv 2407.08889](https://arxiv.org/abs/2407.08889)
- **Automation can flatten character:** auto-EQ suggestions can flatten character and over-boost the extremes if trusted blindly, which argues for bounded EQ ranges. [review](https://musicproductionwiki.com/articles/sonible-smart-eq-4-review)
- **A few dial-like controls go a long way:** Hafezi & Reiss's semi-autonomous EQ needed only one user parameter to approach professional results. [AES 17637](https://aes2.org/publications/elibrary-page/?id=17637)

### Inferences (design recommendations; not directly sourced)
- **Two-layer control:**
  - The agent writes setpoints: target LUFS for each stem, the LAR target, EQ band gains, compressor thresholds, FX send levels.
  - A deterministic server-side controller ramps to those setpoints with per-parameter slew limits. Never write raw fader jumps from the LLM.
- **Suggested bounds per agent action:**
  - Fader: ≤ 1.5 dB per step and ≤ 3 dB per 10 s, ramped over ≥ 300–500 ms.
  - EQ: ≤ 1 dB per step, total ±6 dB from baseline, Q limits fixed.
  - Compressor threshold: ≤ 2 dB per step.
  - Pan: no live pan changes except on preset load.
  - Master limiter: fixed by the agent's controller and never disabled.
  - Hard clamps: on every channel relative to a soundcheck baseline (for example, −12 to +6 dB), plus a global true-peak brickwall.
- **Hysteresis and deadband:**
  - Act only if the metric error exceeds a deadband, such as 1 LU for stem loudness or 1.5 dB for LAR, sustained for at least N seconds.
  - Use different thresholds to enter and exit "solo boost" states.
  - Rate-limit how often the same parameter can be changed (for example, once per 8 s).
- **Shadow mix and A/B:**
  - Render a parallel candidate mix (same stems, proposed settings) on the server.
  - Score it on metrics (LUFS error, LAR error, masking index, spectral distance to the target curve) for about 5–10 s before committing to the live program bus.
  - Commit only if it improves the score and passes the guards.
- **Rollback:**
  - Snapshot every committed state.
  - Auto-revert if program loudness or true peak goes out of bounds, a channel clips, or a metric degrades after commit.
  - Provide a one-click "last-known-good" and a "soundcheck baseline" snapshot.
- **Human override:**
  - Any manual move from a human (for example, through a phone UI) locks that parameter from agent control for X minutes.
  - Log the move as a preference signal.
  - Provide a global "freeze agent" switch.
- **Logging:** for every decision, record time, song section, metrics before and after, parameter deltas, rationale and outcome. Record all 16 raw stems plus the program output for post-show replay.
- **Learning across shows:**
  - Keep presets keyed by song and by member or instrument.
  - Re-mix the recorded multitrack offline after each show: run Diff-MST, RoEx, or the agent's own optimiser to propose improved presets.
  - Treat human corrections as labelled preference data for supervised or bandit updates of setpoint defaults.
  - Use Bayesian optimisation over a small set of interpretable dials (LAR target, tonal tilt, compression amount) with ratings from the band or engineer.
  - This mirrors the low-dimensional control insight from Hafezi & Reiss.

### Gaps
- No peer-reviewed source was found on LLM-in-the-loop live mixing safety.
- No published studies were found with numeric just-noticeable-difference (JND)-based slew limits for live fader automation.
- No published studies were found on RL from engineer corrections for mixing. The recommendations above are engineering judgement.

## Q5. Detecting musical events (solos, who is singing or playing) from stems

### Takeaway
With isolated multitrack stems, envelope-following activity detection gives a strong baseline. This is the same method MedleyDB used to generate its instrument-activation labels. Bleed is the main source of false positives. Solo detection can be layered on top using activity plus relative loudness and spectral novelty. I found no dedicated published "solo detector" method.

### Cited Findings
- **MedleyDB activation labels:**
  - Per-stem confidence values were generated by envelope following: rectification, compression, smoothing and downsampling.
  - MedleyDB is used to evaluate instrument recognition.
  - [arXiv 1511.05520](https://arxiv.org/pdf/1511.05520); [ISMIR 2014 MedleyDB](https://archives.ismir.net/ismir2014/paper/000322.pdf)
- **Bleed corrupts activation labels:** one study kept only 94 bleed-free tracks to avoid erroneous labels, and used 1 s frames. [arXiv 2506.21167](https://arxiv.org/abs/2506.21167v1)
- **Frame-level instrument activity detection:** F1 up to about 0.96 reported on another dataset. [LLark, arXiv 2310.07160](https://arxiv.org/pdf/2310.07160)
- **Bleed removal before analysis:** real-time source separation at about 23 ms latency could clean bleed. [arXiv 2402.17701](https://arxiv.org/abs/2402.17701)

### Inferences
- **Per-stem activity detection:**
  - Run a gated short-term RMS/LUFS envelope (about 400 ms) with hysteresis thresholds calibrated at soundcheck against bleed levels.
  - For vocal mics, add a singing-voice detector or a bleed comparison: vocal-mic energy relative to the coherent drum-overhead energy.
- **Solo heuristic:** an instrument is "featured" when it is active, its short-term loudness rises more than X dB relative to its song-section baseline, and it has high spectral/melodic novelty, sustained over 4 bars or more. The lead vocal is inactive at the same time.
- **Shared event bus:** feed the same events (vocalist active, solo by keys, drum fill) to the camera auto-director and to the mix agent, for example for a modest solo lift of +1 to +2 dB with slew. Debounce with minimum dwell times of several seconds to avoid jittery cuts and level pumping.

### Gaps
- No published method or benchmark was found for live solo detection from multitrack stems.
- No benchmark was found for vocalist-activity detection under stage bleed.
