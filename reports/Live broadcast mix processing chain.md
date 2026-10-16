# Building Sunrise Jam's Cloud-Mixed Broadcast Chain

**Bottom line:** Sunrise Jam's broadcast mix should start from the band's own test-rig balance: vocals at about −2 dB, sax at −2.1, kick, harmonica, piano and synth bass near −10, snare at −14.9 and overheads at −23.4. That balance runs through a server-side chain with four stages. Each channel gets gate/expander → EQ → compressor (with automatic make-up gain) → sends. Channels then feed eight subgroup buses, four shared effects returns and a mid/side-aware mix bus. The master is gentle (glue at 2:1, light multiband, a true-peak limiter at −1.5 dBTP) and aims for about **−14 LUFS integrated**. The FOH app had to cut and could not add gain because of feedback. The broadcast mix is fed from the raw USB multitrack and has no acoustic loop, so it can boost presence, add make-up gain, use parallel compression and add saturation for phone speakers. Even so, the user's rules still apply: no low cut on kick or bass, piano grouped and never quiet, vocals on top, harmonica softened. The 16 MR18 channels (plus the two line inputs) should go from the venue laptop to a DigitalOcean CPU-Optimized server as uncompressed 24-bit PCM over SRT. That is about 18.4 Mbps raw, or 22–30 Mbps with overhead. On the server, the stream is clock-slaved or adaptively resampled into JACK. Carla hosts LSP and x42 plugins there and exposes every parameter over OSC. The audio is delay-matched to the video by cross-correlation. Claude never moves a fader directly. It writes bounded setpoints every 2–10 seconds. A deterministic controller slews to those setpoints, guarded by a shadow mix, snapshots, human override and full logging. Every show's raw stems are replayed offline so the next show starts from better presets. Most per-channel numbers below are informed synthesis rather than published recipes, because no genre-specific live-broadcast settings were found. Each value is therefore tagged by origin.

**Source legend used throughout.** **[U]** comes from the user's rig file (channel list, rules and test-rig balance from the prior session), which is ground truth. **[S]** comes from a published source and is cited inline. **[I]** is inferred engineering judgement that synthesizes [U] and [S] and should be validated by ear at the first soundcheck.

## Five user rules override the textbook

Several user rules contradict generic advice, and the user wins each time. The first is **"don't high/low-cut kick or bass lows"** [U]. Mixing guides routinely high-pass a kick at 30–40 Hz and a bass DI at 30–45 Hz ([musicguymixing](https://www.musicguymixing.com/live-kick-drum-eq/); [LSI April 2025](https://customdigital.livesoundint.com/april-2025/page-17)). Sunrise Jam's channels 1, 12 and 14 instead get no HPF at all. The kick–bass overlap is handled by kick-keyed ducking of about 2 dB in the 60–120 Hz region, which sources describe as the more surgical tool ([Mastrng](https://mastrng.substack.com/p/mixing-kick-and-bass); [musicguymixing sidechaining](https://www.musicguymixing.com/sidechaining/)). The only low-frequency filter anywhere in those paths is a 20 Hz subsonic guard on the master [I], and it can be disabled.

The second rule is that **piano 6+7 is grouped, "never low, soft at all times," rich and sitting in the low-mids behind the singer** [U]. The keys therefore keep their 150–400 Hz body. The guitars give way in that region instead, which inverts the usual "cut the Rhodes at 250–400 Hz" advice. The agent also gets a hard floor on the piano group fader.

The third rule is **vocals on top, and channels 9 and 10 are always vocals** [U]. The lead-to-accompaniment ratio (LAR) target therefore sits at the upper end of published norms (see the balance section).

The fourth rule is that **harmonica can be very sharp and must be softened** [U]. Channel 16 gets a dynamic cut in the upper mids rather than a static one.

The fifth is **"never touch preamp gain"** [U]. The cloud agent gets no write access to the MR18 at all. All gain staging happens as server-side digital trim and faders.

Two of the user's figures conflict with each other. The test-rig balance puts overheads at −23.4 dB and harmonica at −10 dB. The channel notes say overheads go "~−35 dB because loud in room" and harmonica sits "~−30 dB relative." The low figures describe the FOH problem: in the room the acoustic drums and harp are already loud. The broadcast mix starts from the raw USB feed, so this report uses the **test-rig numbers** as the starting broadcast balance. It also gives harmonica heavier tonal softening to honour the intent. One assumption must be checked at the first show. The test-rig faders were presumably built on the same raw USB multitrack in Studio One. If they were, they apply with zero server trim. If they were not, the agent should run a one-time soundcheck calibration that sets per-channel trim so each source's gated short-term loudness matches what the test-rig balance implies [I].

The FOH app's chains used cuts only and no make-up gain because of feedback rings at 129, 160, 196, 226 and 3377 Hz [U]. That is why its vocal had a −2 dB cut at 3 kHz and its bass had −2.5 dB cuts at 350 Hz and 3 kHz. Those notches were feedback management, not tone. The broadcast chain keeps the tonal cuts (mud at 300–350 Hz) and replaces the feedback cuts with presence boosts where the source calls for them. Every compressor uses **auto make-up gain matched to bypass loudness** [I], so the test-rig fader values keep their meaning after compression.

To keep FOH changes from leaking into the stream, the MR18's USB sends should be tapped **before any channel processing** (raw input) [I; verify the MR18 USB-routing options]. The MR18 provides 16 mic preamps plus 2 line inputs over 18×18 USB ([Long & McQuade](https://www.long-mcquade.com/GearHunter/1080537/Midas-MR18.htm)). The two spare line channels 17/18 are the obvious place for a stereo audience/ambience feed, which the current channel list lacks [I].

## Sixteen channel strips start from the band's own balance

The tables below give the complete starting preset per channel. Run order in each strip is HPF → gate/expander → EQ → compressor (+ de-esser) → fader/pan → sends. Fader values are server fader dB. Where the user gave no test-rig value, the value is [I] and follows the rule "piano & guitar at medium; bass moves only if clearly over/under" [U].

### Levels, panning and filters

Panning uses audience perspective, which suits mixes that accompany video ([Sound On Sound](https://www.soundonsound.com/node/4920130); [iZotope](https://www.izotope.com/community/blog/drum-panning)). The pan positions below are placeholders and should be mirrored to the actual stage as seen by the main camera [I].

| Ch | Source | Start fader | Pan | HPF | LPF | Origin |
|---|---|---|---|---|---|---|
| 1 | Kick | **−10.0** | C | **none** | none | fader/HPF [U]; pan [S] convention |
| 2 | Snare | **−14.9** | C | 80 Hz, 12 dB/oct | none | fader [U]; HPF [I] (sources say up to 200 Hz, but funk body at 150–200 Hz must survive) |
| 3 | Overheads (mono, often off) | **−23.4** (auto-mute if no signal) | C | 180 Hz, 24 dB/oct | none | fader [U]; HPF [I] from the 200–400 Hz range ([ProSoundWeb](https://www.prosoundweb.com/tightening-it-up-zen-and-the-art-of-frequency-bracketing-for-drum-kits/2/)) |
| 4 | DI 1 acoustic gtr (mostly unused) | −14 (muted until active) | L20 | 90 Hz | 14 kHz | [I] |
| 5 | Guitar AMP (solo/rhythm) | −12 | L30 | 100 Hz | 12 kHz | HPF [U prior] / [S] ([musicguymixing funk](https://www.musicguymixing.com/funk-guitar-eq/)); rest [I] |
| 6+7 | Piano stereo (grouped) | **−10.0**, floor clamp −13 | L60 / R60 | 35 Hz, 12 dB/oct (subsonic only) | none | fader/group [U]; width/HPF [I] |
| 8 | Guitar DI / GT board | −13 | R30 | 120 Hz (150 Hz for chicken-scratch) | 10 kHz | HPF [U prior]+[S]; LPF [S] ([Violet Recording](https://violetrecording.com/how-to-mix-electric-guitar/)) |
| 9 | Vocal Centre (lead) | **−2.0** | C | 100 Hz male / 120 Hz female | none | fader [U]; HPF [U prior]+[S] ([LSI](https://digital.livesoundint.com/may-2013/page-25)) |
| 10 | Vocal Piano (2nd singer) | **−2.3** | L15 (toward piano) | 120 Hz | none | fader/HPF [U]; pan [I] |
| 11 | Congas 1 / 3rd vocal / guest soloist | role preset (below) | R35 | role preset | role preset | see role table |
| 12 | Bass DI | −10.0 | C | **none** | 6 kHz | HPF rule [U]; fader [I] (matched to kick and DI2); LPF [S] 5–8 kHz range |
| 13 | Congas 2 | −16 | R50 | 80 Hz | 14 kHz | HPF [U prior]; rest [I] |
| 14 | DI 2 synth bass (sub + bass) | **−9.8** | C (mono-summed) | **none** | none | [U] |
| 15 | Sax / flute (wireless lav) | **−2.1** | L25 | role preset | role preset | fader [U]; see role table |
| 16 | Harmonica / BV | **−10.0** | R25 | role preset | role preset | fader [U]; see role table |

### EQ (4-band parametric per channel; broadcast boosts allowed)

| Ch | Band 1 | Band 2 | Band 3 | Band 4 | Origin |
|---|---|---|---|---|---|
| 1 Kick | +3 dB @ 60 Hz, Q1.0 | −4 dB @ 350 Hz, Q2.0 | +3 dB @ 3.5 kHz, Q1.5 | — | [S] ranges ([musicguymixing](https://www.musicguymixing.com/live-kick-drum-eq/); [Produce Like A Pro](https://producelikeapro.com/blog/drum-eq-basics/)); exact values [I] |
| 2 Snare | +2 dB @ 180 Hz, Q1.0 | −3 dB @ 420 Hz, Q2.5 | +2.5 dB @ 5 kHz, Q1.0 | dyn −3 dB @ 4 kHz on buzzy hits | [S] ([eMastered](https://emastered.com/blog/snare-eq)); values [I] |
| 3 OH | −2 dB @ 350 Hz, Q1.0 | −1.5 dB @ 2.5 kHz, Q1.5 | +1.5 dB shelf @ 10 kHz | — | [I] |
| 4 Acoustic DI | −3 dB @ 220 Hz, Q1.2 | −2 dB @ 1 kHz, Q2 (piezo quack) | +2 dB shelf @ 10 kHz | — | [I] |
| 5 Gtr amp | −2.5 dB @ 350 Hz, Q1.0 | dyn −2 dB @ 3 kHz, Q1, keyed by ch 9 | +1.5 dB shelf @ 4.5 kHz | — | [S] ([Nail The Mix](https://www.nailthemix.com/guitar-mixing-faqs)); keying [I] |
| 6+7 Piano | +1 dB @ 200 Hz, Q0.8 ("rich") | +1 dB @ 1.5 kHz, Q1.5 (Rhodes bark; off for acoustic piano) | −2 dB @ 3 kHz, Q1.1 | −1.5 dB @ 4.5 kHz, Q0.8 | 3k/4.5k [U prior]; 200 Hz lift [I] honouring "low-mids" [U] |
| 8 Gtr DI | −2.5 dB @ 350 Hz, Q1.0 | −1.5 dB @ 3 kHz, Q1.0 | +1.5 dB shelf @ 4 kHz | — | [S] ([musicguymixing funk](https://www.musicguymixing.com/funk-guitar-eq/)) |
| 9 Lead vocal | −3 dB @ 300 Hz, Q1.5 | −2 dB @ 650 Hz, Q2 (only if boxy) | **+2 dB @ 4 kHz, Q1.0** (male 3.5 kHz / female 5 kHz) | **+2 dB shelf @ 11 kHz** | 300 Hz [U prior]; presence/air [S] ranges ([ProSoundWeb](https://www.prosoundweb.com/vocal-mixing-for-live-events/2/)); replaces the FOH 3 kHz feedback cut |
| 10 Vocal piano | −3 dB @ 300 Hz, Q1.5 | +1.5 dB @ 4 kHz, Q1.0 | +1 dB shelf @ 11 kHz | — | [I] (BV sits behind lead) |
| 12 Bass DI | −2.5 dB @ 350 Hz, Q1.1 | **+2 dB @ 800 Hz, Q1.0** (phone translation) | +1.5 dB @ 2 kHz, Q1.2 (finger definition) | — | 350 Hz [U prior]; 800 Hz [S] anecdotal ([R/E/P](https://repforums.prosoundweb.com/index.php/topic,25609.0.html)) and [SOS](https://www.soundonsound.com/node/4929135); values [I] |
| 13 Congas 2 | +1.5 dB @ 200 Hz, Q1.0 | −3 dB @ 450 Hz, Q1.5 | +2 dB @ 5 kHz, Q1.0 | — | [I] |
| 14 Synth bass | −2 dB @ 300 Hz, Q1.2 | +1.5 dB @ 900 Hz, Q1.0 | — | — | [I] |

Channels 11, 15 and 16 take their EQ from the role presets below.

### Dynamics and sends

| Ch | Gate / expander | Compressor (auto make-up) | Extra | Sends (dB below unity) | Origin |
|---|---|---|---|---|---|
| 1 Kick | Gate: threshold so only kick opens it, range 25 dB, attack 0.5 ms, hold 30 ms, release 150 ms | 4:1 hard knee, attack 10 ms, release 100 ms, 3–5 dB GR on hits | Key output feeds bass ducking | Room −22 ("a little reverb" [U]) | [S] ranges ([Computer Music](https://www.pressreader.com/australia/computer-music/20200715/282089164061105); [musicguymixing](https://www.musicguymixing.com/kick-compression/)); short release for funk [I] |
| 2 Snare | Expander, range 8 dB (keeps ghost notes), attack 0.5 ms, hold 40 ms, release 150 ms | 4:1, attack 15 ms, release 120 ms, 3–5 dB GR | — | Room −15 | comp [S] ([Nail The Mix](https://www.nailthemix.com/how-to-use-compression-on-a-snare-drum)); expander [I] |
| 3 OH | none | 2:1, attack 20 ms, release 150 ms, 1–2 dB GR | Delay kick/snare 2–3 ms only if OH is up [I] | — | [I]; alignment rule ~1 ms/ft [S] ([SOS](https://www.soundonsound.com/node/4921497)) |
| 4 Acoustic DI | none | 3:1, attack 15 ms, release 150 ms, ~3 dB GR | — | Inst plate −18 | [I] |
| 5 Gtr amp | none | 3:1, attack 15 ms, release 120 ms, 2–4 dB GR | Solo state +2 dB | Inst plate −16, delay −20 on solos | [S] (funk transient survival) / [I] |
| 6+7 Piano | none | 2:1, threshold −22, attack 25 ms, release 200 ms, 2–3 dB GR | Vocal-keyed dyn EQ −2 dB at 2–4 kHz | Inst plate −14 | comp [U prior]; keying [I] |
| 8 Gtr DI | none (use modeler gate) | 3:1, attack 15 ms, release 100 ms, 2–4 dB GR | — | Room −20 | [S] ([musicguymixing funk](https://www.musicguymixing.com/funk-guitar-eq/)) |
| 9 Lead vocal | Expander, range 8 dB, attack 1.5 ms, hold 100 ms, release 300 ms | 3:1 soft knee, attack 5 ms, release 120 ms, 3–5 dB GR | De-esser split-band, narrow, 6 kHz (male) / 7.5 kHz (female), 3–5 dB max | **Vocal plate −8** ("good amount" [U]), delay −18 (throws) | comp [S] ([musicguymixing](https://www.musicguymixing.com/vocal-compression-settings-live/)); expander values [I] (no source gave numbers) |
| 10 Vocal piano | Expander as ch 9 | 4:1, attack 5 ms, release 120 ms, 4–6 dB GR | De-esser as ch 9 | Vocal plate −6 (more than lead) | [I] from BV practice |
| 12 Bass DI | none | Stage 1 peak: 8:1, attack 2 ms, release 80 ms, 2–4 dB GR. Stage 2 level: 3:1, threshold −18, attack 30 ms, release 150 ms, 3–6 dB GR | Kick-keyed dyn EQ −2 dB @ 80 Hz (60–120 Hz), attack 5 ms, release 80 ms; parallel saturation send | none | stage 2 [U prior]; ducking [S]; two-stage [I] |
| 13 Congas 2 | none | 3:1, attack 10 ms, release 100 ms, 2–3 dB GR | — | Room −18 | [I] |
| 14 Synth bass | none | 3:1, attack 20 ms, release 150 ms, 2–3 dB GR | Kick-keyed duck 2 dB @ 60–120 Hz; mono below 120 Hz | none | [S] ducking; rest [I] |

The bass saturation send needs explaining. Phone speakers cannot reproduce a 40–80 Hz fundamental. Distortion generates harmonics that the ear reads as the missing fundamental. A low-passed send into distortion is "a more flexible solution" than distorting the dry track ([Computer Music](https://www.pressreader.com/australia/computer-music/20171004/282243780786770)). Sources warn it can thin the lows on full-range systems ([UPC thesis](https://upcommons.upc.edu/entities/publication/53beaf2b-6dbb-4628-b2f4-e8549f05184f/full)). Channels 12 and 14 should therefore feed a send that low-passes at 400 Hz, saturates, high-passes at 150 Hz, and returns 15 dB below the dry bass [I]. This adds audible "bass" on phones without changing the dry low end the user wants untouched.

### Role-switching presets for channels 11, 15 and 16

Each multi-role channel stores one complete preset per role. The agent proposes a switch using a classifier: singing-voice detector, harmonicity, spectral centroid and median f0. A switch requires **at least 8 seconds of consistent classification**. The new preset then crossfades over 2 seconds, and an operator "confirm/lock role" button overrides the classifier [I]. Sources found no published live role or solo detector. The closest validated method is MedleyDB-style envelope-following activity detection ([arXiv 1511.05520](https://arxiv.org/pdf/1511.05520)). The thresholds are therefore all [I].

| Ch / role | Fader | Pan | HPF / LPF | EQ | Comp | Sends |
|---|---|---|---|---|---|---|
| **11 Congas 1** (default) | −16 | R35 | 80 Hz / 14 kHz | +1.5 @ 200 Hz; −3 @ 450 Hz Q1.5; +2 @ 5 kHz | 3:1, 10/100 ms, 2–3 dB | Room −18 |
| **11 Third vocal** | −4 | R20 | 120 Hz / — | −3 @ 300 Hz Q1.5; +1.5 @ 4 kHz; +1 shelf 11 kHz | 4:1, 5/120 ms, 4–6 dB + de-esser | Vocal plate −6; joins VOCAL bus |
| **11 Guest soloist (e.g., trombone)** | −6 (featured +2 while soloing) | R20 | 70 Hz / 12 kHz | −2 @ 300 Hz; +1.5 @ 1.2 kHz; dyn −2 @ 3 kHz | 3:1, 20/150 ms, 2–4 dB | Inst plate −12, delay −20; joins SOLO bus |
| **15 Sax** (default) | −2.1 | L25 | 100 Hz / 14 kHz | −2 @ 250 Hz (lav boom); dyn −2 @ 2.8 kHz (honk/bite); +1.5 shelf 8 kHz | 3:1, threshold −18, 20/150 ms | Inst plate −10, delay −20 |
| **15 Flute** | −4 | L25 | 250 Hz / — | +1.5 @ 5 kHz; dyn −3 @ 7 kHz (breath/chiff) | 2.5:1, 15/150 ms | Inst plate −8 |
| **16 Harmonica** (default) | −10 | R25 | 120 Hz / **9 kHz** | +1 @ 250 Hz (warmth); −2 @ 1.2 kHz Q1.5; **dyn −3 to −5 dB @ 3 kHz, Q1.5, only above threshold** | 3:1, threshold −18, 20/150 ms | **Room −12** (short room [U]) |
| **16 Backing vocal** | −5 | R25 | 120 Hz / — | as 11 third vocal | 4:1, 5/120 ms + de-esser | Vocal plate −6; joins VOCAL bus |

Origins: the HPF 120 Hz, the 3:1 at −18 dB and the 20/150 ms timings on 15 and 16 come from the prior FOH app [U]. The harmonica's dynamic cut and LPF implement the user's "soften" rule [I]. The vocal-role compression follows the BV practice above [I]. The flute HPF, chiff band and trombone values are [I].

## Eight buses and four returns glue the band without flattening the groove

Reference sessions in this genre sound "captured": KEXP works from an SM57/58 template and aims to capture what the band delivers ([Mix](https://www.mixonline.com/recording/live-on-kexp-podcast-blurs-the-lines-between-live-and-studio-recording)). Vulfpeck's Fearless Flyers used "a nice, dead room…great D.I.s…good drum mics" ([Live for Live Music](https://liveforlivemusic.com/news/the-fearless-flyers-blue-note-residency-record-new-studio-album-videos/)). Russell Elevado most often mixes with *no* mix-bus chain ([RBMA](https://daily.redbullmusicacademy.com/2018/06/russell-elevado-interview)). The bus layer here should therefore add glue and control, not obvious squash. The published numbers cover the mix-bus SSL-style compressor and NY parallel drums. Every other bus setting is practitioner convention [I].

| Bus | Members | Processing (start) | Origin |
|---|---|---|---|
| DRUMS | 1, 2, 3 | VCA comp 4:1, attack 20 ms, auto release, sidechain HPF 80 Hz, 2–3 dB GR | [I] |
| DRUM SMASH (parallel) | 1, 2 (pre-fader send) | 10:1, attack 1 ms, release 100 ms, 10–15 dB GR, blended ~−12 dB (≈25% wet), level-matched | [S] ([musicguymixing](https://www.musicguymixing.com/parallel-compression-on-drums/); [MusicRadar](https://www.musicradar.com/tuition/tech/how-to-use-new-york-compression-on-drums-605461)) |
| PERC | 13 (+11 in conga role) | 2:1, 15/150 ms, 1–2 dB GR | [I] |
| BASS | 12, 14, saturation return | 3:1, attack 30 ms, auto release, 1–2 dB GR; mono below 120 Hz; shared loudness target | [I] |
| KEYS (user group) | 6+7 | 1.5:1, 1–2 dB GR; vocal-keyed dyn EQ −2 dB 2–4 kHz; **group floor −13 dB** | group/floor [U]; ducking [I] |
| GUITARS | 4, 5, 8 | 2:1, 1–2 dB GR; vocal-keyed dyn EQ −1.5 dB 2.5–3.5 kHz | [I]; [S] for the competing-band concern ([musicguymixing funk](https://www.musicguymixing.com/funk-guitar-eq/)) |
| SOLO | 15, 16 (instrument roles), 11 (soloist role) | 2:1, 1–2 dB GR; vocal-priority duck −3 dB when ch 9 is active and no solo is detected | [I] implementing "vocals on top" [U] |
| VOCALS | 9, 10 (+11/16 in vocal roles) | 2:1, attack 10 ms, release 150 ms, 1–3 dB GR (second leveling stage); fast peak limiter catching 1–2 dB | two-stage concept [S] ([McDSP](https://mcdsp.com/2021/12/08/009-multi-stage-vocal-compression/)); values [I] |

Time-based effects run on four 100%-wet aux returns, with EQ after each reverb, so the agent can ride "wet" per song ([Violet Recording](https://violetrecording.com/how-to-add-reverb-to-vocals/)). The **vocal plate** uses 30 ms pre-delay and **1.4 s decay** for up-tempo funk. Ballads go to 2.0–2.5 s. The return is high-passed at 250 Hz and low-passed at 10 kHz. These numbers fall inside the sourced 20–40 ms pre-delay, 0.8–1.8 s decay and 200–400 Hz / 8–12 kHz filter ranges ([Rysup Audio](https://rysupaudio.com/blogs/news/reverb-settings-for-vocals)). The **short room** serves snare, kick, congas, guitar and the user-requested harmonica room: 0.6 s decay, 5 ms pre-delay, HPF 200 Hz, LPF 8 kHz [I]. The **tempo delay** is set at 60000/BPM ms per quarter note. It uses a dotted-eighth or quarter, 15% feedback, HPF 300 Hz and LPF 6 kHz, with a 90 ms single-repeat slapback as an alternate preset [I]. The **instrument plate** serves keys, sax, flute, soloists and the acoustic DI: 1.8 s decay, 20 ms pre-delay, HPF 300 Hz, LPF 9 kHz [I]. The agent should judge reverb level in mono too, because decorrelated tails partially cancel when summed ([SOS](https://www.soundonsound.com/sound-advice/q-can-haas-delays-be-mono-compatible)).

## A mono-safe image keeps the vocal 3–7 dB on top

A YouTube stream is heard largely on phones. Haas-style widening (one side delayed 5–35 ms) comb-filters and can vanish in mono ([iZotope](https://www.izotope.com/en/learn/what-is-the-haas-effect); [SOS](https://www.soundonsound.com/sound-advice/q-can-haas-delays-be-mono-compatible)). The imaging rules are therefore conservative. **Kick, snare, both basses and the lead vocal stay dead centre**, and synth bass is mono-summed. Width comes only from real stereo sources, panning and reverb returns: piano 6+7 narrowed to ±60%, guitar amp and guitar DI on opposite sides at ~30%, congas, sax and harmonica placed to the stage. If an audience pair is added on inputs 17/18, it goes hard L/R. No stereo enhancer goes on the master. A mid/side EQ high-passes the side channel at about 120 Hz so the low end is mono, and the correlation meter should average above roughly +0.3 [I].

For overall balance, the band's test rig already encodes "vocals on top": both singers sit 7–8 dB above the piano, kick and synth bass. The measurable target is the lead-to-accompaniment ratio. Across ~300 Billboard songs, mean LAR settled near **+1 dB** after 1975. It is positive for pop and around 0 for rock, and bands run lower than solo artists ([Gerdes & Siedenburg via acoustics.org](https://acoustics.org/lead-vocal-tracks-in-popular-music-go-quiet/)). Listeners, though, prefer about **+7.6 dB**, and hard-of-hearing listeners about +10.4 dB ([Forum Acusticum 2025](https://dael.euracoustics.org/confs/fa2025/data/articles/000716.pdf)). Given the user's explicit rule and phone playback, the agent should hold **LAR at +3 to +7 dB**, measured on the gated vocal bus against the music bus, starting at +5 dB [I]. Kick and both basses hold their test-rig relationship (kick −10, DI2 −9.8, bass DI −10). The bass bus moves only on clearly sustained error. Piano and guitars are "medium" and never fall below their floors.

A **TALK** state applies between songs. The lead vocal's HPF rises by 20–30 Hz, reverb and delay sends are muted, and the vocal is lifted 3–6 dB. Its compression tightens to about 6 dB GR, and the band beds drop 10–20 dB [I]. The duck on the band is a vocal-keyed sidechain at about −20 dBFS threshold, 4:1–8:1, 10–30 ms attack and 200–500 ms release ([zZounds](https://blog.zzounds.com/2022/06/21/ducking-vocals-with-sidechain-compression-during-live-broadcasts/); [Voxbooster](https://voxbooster.com/blog/mix-voice-with-background-music)). Song/talk detection uses band-bus RMS plus vocal features, with a few seconds of hysteresis. An Allen & Heath user found a ducker working on the main mix but not on the stream aux ([A&H community](https://community.allen-heath.com/?p=105396)), so verify the duck on the exact path that feeds the encoder.

## The broadcast master targets −14 LUFS and −1.5 dBTP

YouTube's live encoder spec is AAC or MP3 at **128 kbps stereo, 44.1 kHz** ([YouTube Help](https://support.google.com/youtube/answer/2853702?hl=en)). For uploads, YouTube turns content louder than about −14 LUFS down and never turns quiet content up. That figure comes from third-party guides, and nothing confirms the behaviour for live streams ([Youlean](https://youlean.co/?p=30813)). Streaming platforms use a −1 dBTP ceiling ([FabFilter](https://www.fabfilter.com/help/pro-l/using/outputoptions)), and AES TD1008 recommends −16 LUFS for music ([Production Advice](https://productionadvice.co.uk/td1008/)). A 128 kbps AAC encode leaves less codec headroom than higher bitrates, so the master runs eight stages:

| # | Stage | Setting | Origin |
|---|---|---|---|
| 1 | Subsonic guard | 20 Hz, 12 dB/oct (below kick/bass musical content; disable if the user objects) | [I] (master HPF convention is 25–30 Hz; lowered for the user rule) |
| 2 | Tonal EQ | ±1 dB max broad moves toward a neo-soul curve (warm lows, relaxed 2–5 kHz, smooth top) | [I] |
| 3 | M/S EQ | Side HPF 120 Hz; optional side +1 dB shelf above 10 kHz | [I] |
| 4 | Glue compressor | SSL-style 2:1, attack 30 ms, auto release, 1–2 dB GR | [S] ([Waves](https://www.waves.com/how-to-use-ssl-bus-compressor-classic-mix-glue); [Violet Recording](https://violetrecording.com/best-bus-compressor-plugins/)) |
| 5 | Multiband | 4 bands, crossovers 120 Hz / 800 Hz / 5 kHz; 1.5:1–2:1; 1–3 dB GR per band; attacks ~30 ms low, ~10 ms high | [S] ranges ([Violet Recording](https://violetrecording.com/how-to-use-multiband-compression-in-mastering/); [musicguymixing](https://www.musicguymixing.com/multiband-compression-mastering/)) |
| 6 | Slow leveler (AGC) | ±3 dB range, multi-second time constants, catches song↔talk jumps | [I] broadcast convention |
| 7 | True-peak limiter | x42-dpl in true-peak mode, **ceiling −1.5 dBTP**, ≤3 dB GR on peaks | ceiling [S]/[I]; plugin [S] ([x42 dpl](https://rg42.org/oss/lv2/dpl)) |
| 8 | Metering | BS.1770 momentary/short-term/integrated, LRA, true peak, correlation | [S] ([EBU Tech 3342](https://tech.ebu.ch/publications/tech3342)) |

The targets are **−14 LUFS integrated ±1 LU** per song, with −15 to −16 an acceptable conservative alternative. Song sections should hold short-term loudness between −16 and −12 LUFS, and talk between −16 and −18. True peak stays at or below −1.5 dBTP. The peak-to-loudness ratio stays around 8–12 dB to keep groove dynamics; this is a heuristic, not a sourced norm. If a band compresses 6 dB continuously, that signals an EQ problem upstream, not a need for more limiting ([Violet Recording](https://violetrecording.com/how-to-use-multiband-compression-in-mastering/)). Loudness should come from balance and buses, not from the limiter. Run the internal mix at 48 kHz. Resample to 44.1 kHz only at the AAC encoder, as the YouTube spec lists, and test that hand-off on an unlisted stream first.

## SRT carries 18.4 Mbps of raw PCM to a Carla-hosted server

**Venue side.** The laptop only captures and transmits; it does no processing. One Windows user found that 18-channel X-Air capture worked only with all 18 channels selected and the Behringer driver also set as the output device ([Audacity forum](https://forum.audacityteam.org/t/multitrack-recording-behringer-x18/45653)). Use wired Ethernet, not Wi-Fi, because Wi-Fi adds jitter ([sonobus.net](https://sonobus.net/)). Use the High Performance power plan and disable USB selective suspend. Keep the Studio One local multitrack recording running as the backup [I]. Sixteen channels × 48 kHz × 24 bit is **18.43 Mbps** raw, so plan for 22–30 Mbps of uplink with SRT overhead and retransmission headroom [I, arithmetic].

**Transport.** The first choice is **SRT in caller mode** with a 500 ms latency window (range 300–1000 ms) for ARQ recovery. The payload is one sample-locked stream: either 16–18 channels of `pcm_s24le` in Matroska/NUT, or two 8-channel SMPTE 302M streams in MPEG-TS. FFmpeg's s302m encoder supports only 2, 4, 6 or 8 channels ([FFmpeg source](https://ffmpeg.org/doxygen/4.0/s302menc_8c_source.html)), and it has a reported demux-recognition issue ([trac #8660](https://ffmpeg.org/pipermail/ffmpeg-trac/2020-May/054245.html)). The Matroska/NUT route is untested and must be verified. The fallback is **JackTrip** with `-n 16` and a larger receive queue such as `-q8`; JackTrip requires matching sample rate and buffer on both ends and has no retransmission ([jacktrip man page](https://man.archlinux.org/man/extra/jacktrip/jacktrip.1.en); [CCRMA notes](https://ccrma.stanford.edu/~cc/deck.js/153bSpring2020/index.html)). SonoBus, also uncompressed PCM, is another option ([SonoBus GitHub](https://github.com/essej/sonobus)). The mixer's clock and the server clock will drift. At 50 ppm that accumulates to about **0.54 s over a 3-hour show** [I, arithmetic]. The receiver must either make the incoming stream the JACK master clock or resample adaptively. The zita-ajbridge approach is a slowly varying ratio driven by a control loop ([zita-ajbridge](https://kokkinizita.linuxaudio.org/linuxaudio/zita-ajbridge-doc/quickguide.html)); FFmpeg's `aresample=async` is the other route.

**Server DSP stack.** Use a **DigitalOcean CPU-Optimized (dedicated-vCPU) droplet**. Those plans get "guaranteed access to the full hyper-thread," whereas shared vCPUs suffer noisy neighbours ([DigitalOcean](https://docs.digitalocean.com/products/droplets/concepts/choosing-a-plan/)). PREEMPT_RT is in mainline since Linux 6.12 ([Phoronix](https://www.phoronix.com/news/Linux-6.12-Does-Real-Time)), but stock Ubuntu does not enable it ([OneUptime](https://oneuptime.com/blog/post/2026-03-02-how-to-install-real-time-kernel-preempt-rt-on-ubuntu/markdown)). No musician monitors this mix, so an RT kernel is optional. Run JACK or PipeWire on a dummy driver at 48 kHz with **256–512 frames × 3 periods**, and pin the audio thread with SCHED_FIFO on an isolated vCPU [I].

Host the chain in **Carla**, which offers "full OSC control" of every plugin parameter ([Carla README](https://git.kx.studio/falkTX/Carla/src/commit/240132bd9acce75b427afa73ea6febfa882c8aa9)). The chain uses:

- **LSP Plugins** (LGPLv3; LV2/CLAP) for gate, parametric EQ, compressor, dynamic processor and multiband ([LSP GitHub](https://github.com/lsp-plugins/lsp-plugins))
- **x42-dpl** as the true-peak limiter (1.2 ms latency) ([x42](https://rg42.org/oss/lv2/dpl))
- Dragonfly or LSP reverbs and LSP delays
- FAUST, optionally, for custom dynamic-EQ ducking

The CPU estimate is about 1–3 cores for audio [I, unbenchmarked]. Double that if the shadow mix runs in parallel. GPL/LGPL obligations are generally not triggered by a hosted service, but legal review is needed [I].

**Video and sync.** The research assumes phone cameras ingested over WebRTC. The pipeline is a LiveKit, mediasoup or Janus SFU feeding a GStreamer compositor or LiveKit Egress, then H.264 1080p60 CBR with a **2 s keyframe interval (120 frames)** over RTMPS ([LiveKit Egress](https://docs.livekit.io/server/egress); [streamer.guide](https://streamer.guide/guides/bitrate-encoder-settings-cheat-sheet)). Secondary sources conflict on bitrate (6 to 17 Mbps), so check YouTube's official page. x264 at 1080p60 plus compositing needs its own large droplet, or a GPU droplet if NVENC turns out to be exposed (unverified) [I]. For A/V sync, cross-correlate each phone's own audio against the board mix with **GCC-PHAT**, which is cheap and robust to noise ([USPTO 9877066](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9877066); [MathWorks](https://www.mathworks.com/help/phased/ref/gccphat.html)). Resample both signals to 8–16 kHz mono. Every 5–10 s, run a ±2 s search window and accept an offset only above a peak-to-sidelobe threshold. Median-filter the accepted offsets and slew each video pad's offset. Hold the board audio at a fixed delay equal to the slowest video path [I]. A soundcheck clap provides the initial offsets.

## Claude writes bounded setpoints, never raw faders

Reiss's group showed that cross-adaptive loudness-based fader and EQ automation runs in real time ([Perez-Gonzalez & Reiss](https://ieeexplore.ieee.org/document/5346498); [DAFx 2012](https://www.dafx.de/paper-archive/2012/papers/dafx12_submission_6.pdf)). Masking-reduction EQ approached a professional mix with a single user parameter ([Hafezi & Reiss](https://aes2.org/publications/elibrary-page/?id=17637)). Neural systems such as Diff-MST output interpretable console parameters but run offline ([arXiv 2407.08889](https://arxiv.org/abs/2407.08889)). The closest LLM precedent, LLM2Fx-Tools, infers effect chains through tool calls ([Sony AI](https://ai.sony/publications/llm2fx-tools-tool-calling-for-music-post-production)). No peer-reviewed work covers an LLM supervising a live mix, so everything in this section is engineering design [I] built on those precedents.

The architecture has two layers. A **fast deterministic layer** on the server runs at audio rate: compressors, limiter, de-essers, kick-keyed ducking, vocal-keyed spectral ducking, the TALK duck and gated per-stem loudness metering. A **slow supervisory layer**, Claude, acts every 2–10 s. It writes only setpoints: per-stem loudness targets, the LAR target, EQ band gains, compressor thresholds, send levels and role/state changes. The controller then ramps toward them. Gate analysis signals before measuring, because stage bleed biases per-stem loudness; one study had to discard bleed-affected stems to get valid activity labels ([arXiv 2506.21167](https://arxiv.org/abs/2506.21167v1)).

The safety envelope is fixed in code, not in the prompt.

| Control | Max per action | Rate / ramp | Hard clamp | User-rule overlay |
|---|---|---|---|---|
| Fader | 1.5 dB | ≤3 dB per 10 s; ramp ≥300–500 ms; same parameter ≤ once per 8 s | −12/+6 dB from soundcheck baseline | Kick, snare, OH, vocals **locked** after balance (±1 dB trim, 2 LU deadband); bass deadband 2.5 LU ("clearly over/under"); piano floor −13 dB |
| EQ band | 1 dB | ramp ≥200 ms | ±6 dB from preset; Q fixed | No HPF may be added on 1, 12, 14 |
| Comp threshold | 2 dB | ramp ≥200 ms | ±6 dB from preset | — |
| FX sends | 2 dB | per song section | −40 dB to preset +4 dB | Vocal plate never below −14 on ch 9 in SONG state |
| Pan | none live | preset load only | — | — |
| Master limiter | none | — | always on, ceiling ≤ −1.5 dBTP | — |
| MR18 preamp / any MR18 parameter | **no write access** | — | — | "Never touch preamp gain" [U] |

Every action also passes four checks. **Hysteresis** acts only when error exceeds the deadband (1 LU stem loudness, 1.5 dB LAR) for N seconds, with separate enter and exit thresholds for solo-lift states. Solo lift is +1 to +2 dB with slew and several seconds of minimum dwell. A **shadow mix** renders the candidate settings in parallel for 5–10 s and scores them on LUFS error, LAR error, true peak, a masking index and spectral distance to the genre curve. Masking metrics correlate poorly with perception, so they serve only as relative signals ([Hafezi & Reiss](https://aes2.org/publications/elibrary-page/?id=17637)). **Snapshot rollback** stores every committed state. The system auto-reverts if program loudness or true peak goes out of bounds, a channel clips, or the score degrades after a commit. It always offers "last-known-good" and "soundcheck baseline". **Human override** works through a phone UI: any manual move locks that parameter from agent control for several minutes and is logged as a preference label, and a global **freeze-agent** switch drops to the static presets above.

Learning across shows follows from the logging. Record all 18 raw stems and the program output. For every decision, log the timestamp, song section, metrics before and after, parameter deltas, rationale and outcome. After each show, replay the multitrack offline through the same server chain. Let the agent, or Diff-MST/RoEx-style optimizers, propose preset deltas. Promote a delta into the next show's presets only if it improves the scores on that replay *and* on the previous shows' stems, which prevents overfitting to one night. Key presets by song and by performer, because rotating musicians and guest soloists mean channel 11 or 15 can be a different player each week. Learn ch 9's male/female setting per singer. Restrict online learning to a handful of interpretable dials (LAR target, tonal tilt, compression amount, reverb wetness), tuned by Bayesian optimization from band or engineer ratings. This mirrors the finding that a few dials suffice ([Hafezi & Reiss](https://aes2.org/publications/elibrary-page/?id=17637)).

## Conclusion

Most of the "TV-show quality" here comes from architecture, not from exotic processing. Tapping the USB feed raw, outside the feedback loop, converts the FOH app's defensive cut-only presets into a broadcast chain that can add presence, make-up gain, parallel punch and phone-friendly bass harmonics. Separating a fast deterministic DSP layer from a slow, clamped supervisory agent makes an LLM safe in a live signal path. The user's own rules and test-rig balance are the strongest data available. Published sources supplied ranges but almost no genre-specific live numbers, so the inferred values above are best treated as hypotheses that the first soundcheck and the first offline replay will confirm or correct.

Several things remain open and should be checked early on a private stream:

- whether the MR18 USB sends can be tapped pre-processing
- whether the Mac test-rig faders were built on the same raw gain structure
- whether 16-channel PCM over SRT in Matroska/NUT is stable
- whether YouTube normalizes live streams
- what the official 1080p60 bitrate is

The biggest musical risk is the role-switching channels. A misclassified channel 11 or 16 would put conga processing on a trombone, or harmonica softening on a backing singer. The 8-second confirmation rule, the crossfade and an operator role-lock button are the right price for avoiding that error on air.
