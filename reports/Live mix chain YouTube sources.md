# YouTube-Verified Presets Rebuild Sunrise Jam's Cloud Mix

The full chain is now settled, and **about two thirds of the per-channel numbers are backed by high-view or multi-channel YouTube engineers**. The rest are clearly marked fallbacks. At the venue, set the MR18's USB Sends to the **"Analog" tap** in X-Air Edit. That sends 16 raw preamp channels, untouched by the FOH gate, EQ, compressor or fader, from the laptop to the cloud server over SRT. On the server, each channel runs filter → (gate only on kick) → EQ → compressor → sends. The channels feed seven subgroup buses, four effects returns and an audience bus, then a light stream master: glue at 2:1 that "barely moves", gentle equal-loudness EQ, and a true-peak limiter at **−1 dBTP with no more than 3–4 dB of gain reduction**. The loudness target is **−16 LUFS integrated**, not the −14 LUFS of the earlier report. Two stream engineers target −16, and two channels confirm that YouTube never turns quiet audio up. The YouTube evidence changes several earlier inferred values:

- the snare loses its expander
- the kick compressor's attack slows from 10 ms to 25–30 ms
- the lead vocal no longer gets a 4 kHz boost, because 4 kHz is the "harshness" band in a 1.01M-view tutorial
- keys dip at 1–2 kHz to sit behind the singer
- the bass compressor becomes a single 4:1 stage with 6–9 dB of gain reduction
- the vocal effects are ducked by the vocal itself

The user's rules still win where they conflict with YouTube practice: there is no high-pass on kick or bass even though four channels high-pass bass at 40 Hz, the piano is never low, vocals sit on top, and preamp gain is never touched. Claude cannot be a "set and forget" automixer here. The earlier StageMix app failed because it **could not recognise what it was hearing or judge whether the result sounded good**. The new design gives Claude ears in three layers: on-server classifiers, objective metrics, and a hosted audio-language "listener". Claude stays a bounded director that verifies every change by listening again.

## How to read the verification tags

Every preset value carries one of five tags. **[V: …]** means the value meets the user's rule: either one video has at least 100k views, or two or more independent channels agree. Several videos from one channel count as one channel. The tag lists channel count and views. **[V: official]** means official Behringer/Midas or YouTube material. **[U]** is the band's own ground truth from the prior StageMix session (channel list, rules, test-rig faders). It cannot be YouTube-verified but overrides everything else. **[CONFLICT]** marks verified sources that disagree with each other or with a user rule. **[UNVERIFIED/inferred]** is a single low-view source or engineering judgement, and the user should treat it as a fallback for the first soundcheck. View counts were captured on 2026-10-16. No YouTube source with numeric settings was specific to neo-soul or funk. The numbers come from live-sound educators (mostly X32/XR18 owners) and studio mixers, so they describe good live and broadcast practice in general, not the genre.

The preset tables use short source keys. The full key, with links and views, is:

| Key | Video (channel) | Views |
|---|---|---|
| A | [Drum Gates](https://www.youtube.com/watch?v=H9NbaELL6nE) (Academy AV) | 227k |
| B | [Drum Compression](https://www.youtube.com/watch?v=WxOnpsuAsqw) (Academy AV) | 215k |
| C | [Live Drum Compression](https://www.youtube.com/watch?v=CshdvNnDKr4) (Attaway Audio) | 145k |
| D | [EQ drums on X32/M32](https://www.youtube.com/watch?v=SY-BnLQNwOc) (Andrew Lepard) | 222k |
| E | [Drum Mixing, Ross Stratton](https://www.youtube.com/watch?v=FIlwKWlfXc0) (Mike Lee Music) | 91k |
| F | [4 Magic Frequencies for Snares](https://www.youtube.com/watch?v=yCC3MYf0-yQ) (Hardcore Music Studio) | 387k |
| G | [Mixing Bass Guitar Live](https://www.youtube.com/watch?v=ctBDFPnhrOs) (Attaway Audio) | 198k |
| H | [Mixing Live Bass Guitar](https://www.youtube.com/watch?v=FNa7avcUUSM) (Alan Hamilton Audio) | 160k |
| I | [How I Mix Bass Guitar](https://www.youtube.com/watch?v=DDhDnuJXHHc) (Collaborate Worship) | 113k |
| J | [Andy Wallace Bass EQ Trick](https://www.youtube.com/watch?v=zrWA9rglG24) (Green Light Sound) | 415k |
| K | [Scheps: Kick and Bass](https://www.youtube.com/watch?v=BMW4K7FzQp8) (Waves) | 219k |
| L | [Science of Kick and Bass](https://www.youtube.com/watch?v=27ewHn5SAiI) (Sage Audio) | 243k |
| M | [Maserati: Bass & Synth Bass](https://www.youtube.com/watch?v=x8uzol0NixE) (Waves) | 144k |
| N | [Ducker on Bass, X32](https://www.youtube.com/watch?v=Csmtq0WGPcI) (Drew Brashler) | 74k |
| O | [Parallel Drum Groups, X32](https://www.youtube.com/watch?v=C3K60IS8Pj4) (Drew Brashler) | 52k |
| P | [CLA Parallel Drum Compression](https://www.youtube.com/watch?v=Z0eqw_3cY2A) (Puremix) | 153k |
| Q | [Mixing for Smartphones with Saturation](https://www.youtube.com/watch?v=7q1PeGsmhn8) (Audio University) | 41k |
| R | [Mixing Latin Percussion, JC Losada](https://www.youtube.com/watch?v=oLDVLFYGjQ8) (Waves) | 44k |
| S | [EQ the Congas](https://www.youtube.com/watch?v=ASFeqBOGk2Q) (Marco Galvan) | 16k |
| AHV | [5 Tips Live Vocals X32/XR18](https://www.youtube.com/watch?v=oP4sdpkkNhY) (Alan Hamilton Audio) | 403k |
| CWV | [Vocal EQ & Compression](https://www.youtube.com/watch?v=nF0uezOA4UA) (Collaborate Worship) | 809k |
| ATC / ATE | [Vocal Compression](https://www.youtube.com/watch?v=vcdwTwAXjmg) / [Vocal EQ](https://www.youtube.com/watch?v=ey715RqVozk) (Attaway Audio) | 258k / 444k |
| ATR / ATD | [Vocal Reverb](https://www.youtube.com/watch?v=Ms0qDW0GSDc) / [Live Vocal Delay](https://www.youtube.com/watch?v=2t_hVmyXZ-4) (Attaway Audio) | 267k / 107k |
| COLT | [Vocal EQ Secrets](https://www.youtube.com/watch?v=Wq1di2luMcs) (Colt Capperrune) | 1.01M |
| WSG | [EQ Female Vocals](https://www.youtube.com/watch?v=NeqfK1Z9JKI) (Worship Sound Guy) | 58k |
| ALM | [Smooth R&B Vocals](https://www.youtube.com/watch?v=MTmteq-jCyw) (Adam Lewis Mixing) | 125k |
| STK | [Vocal Trick They All Use](https://www.youtube.com/watch?v=CUyMUHStPxs) (Streaky) | 1.25M |
| TMBV | [Background Vocals, Maserati](https://www.youtube.com/watch?v=a6agrpAFmGw) (Mix with the Masters) | 646k |
| CWK / HMSP / ATK / PEN | [Keys EQ](https://www.youtube.com/watch?v=XJaEkLbxoEk) (Collaborate Worship) / [Piano Frequencies](https://www.youtube.com/watch?v=fM9OwnQ_uRI) (Hardcore Music Studio) / [Keys & Pads](https://www.youtube.com/watch?v=UXF70zgc-Q4) (Attaway) / [Rhodes](https://www.youtube.com/watch?v=FmdQsxbR5Oc) (Pensado's Place) | 93k / 64k / 83k / 99.5k |
| HMSG / CWONG | [Electric Guitar Frequencies](https://www.youtube.com/watch?v=xYK-GM3MPD8) (Hardcore Music Studio) / [Cory Wong Clean Tones](https://www.youtube.com/watch?v=Z3fStcglxoQ) (Universal Audio) | 178k / 526k |
| ATA / OTM | [Acoustic Guitars](https://www.youtube.com/watch?v=H6_L4X_ftNM) (Attaway) / [EQ Acoustic Guitars](https://www.youtube.com/watch?v=enc6oUhyT3c) (OwnTheMix) | 106k / 106k |
| RCS / FM / HRN / SB / ALI | [Sax](https://www.youtube.com/watch?v=jPe8O7LWitg) (Recording Crave) / [Huge Sax](https://www.youtube.com/watch?v=33aHekBUbHc) (Fabio Marziali) / [Sax EQ](https://www.youtube.com/watch?v=6jhM8zHVRAI) & [Flute](https://www.youtube.com/watch?v=iB1pzQlxqJs) (Home Recording Network) / [Trombone](https://www.youtube.com/watch?v=zpBd3MBeIFM) (Shawn Bell) / [Brass, MixedByAli](https://www.youtube.com/watch?v=3OOwjTQABVc) (UA) | 38k / 22k / 23k & 16k / 4k / 59k |
| DBL / CWL / WV | [Louder Stream Audio LUFS](https://www.youtube.com/watch?v=2jhggSKR2AI) (Drew Brashler) / [Live Stream Not Loud Enough](https://www.youtube.com/watch?v=5jA7-GLzt0M) (Collaborate Worship) / [Broadcast Mixes without Overcompressing](https://www.youtube.com/watch?v=LCgUWA8D2Zs) (Waves) | 109k / 99.5k / 100k |
| VULF / NPR / SNL | [He mixes Vulfpeck live](https://www.youtube.com/watch?v=g-HC64mO9-Q) / [Tiny Desk audio](https://www.youtube.com/watch?v=e07bI5rz6FY) / [Mixing SNL](https://www.youtube.com/watch?v=tlmK-QCLthI) | 305k / 796k / 112k |
| FF | [Stereo without Sucking in Mono](https://www.youtube.com/watch?v=spaqBr-cCFw) (FabFilter) | 322k |

## The MR18 must send raw "Analog" taps, and the stream lands at −16 LUFS

**USB routing is now verified.** In X-Air Edit, open In/Out → USB Sends and set the tap to **"Analog"**. The "Default signal tap" dropdown applies it to all channels at once. Drew Brashler's reason: "I don't want my gate, my EQ, my dynamics, any of that to be affecting the audio" ([Drew Brashler, 157k](https://www.youtube.com/watch?v=y4kxfwblFTs)). Alan Hamilton agrees for recording: "you generally want the red ring… it's all one to one" ([Alan Hamilton Audio](https://www.youtube.com/watch?v=xYmJGyroVe0)) **[V: 2 channels, 157k + 100k-class channel]**. This settles the earlier report's biggest open question. FOH fader moves, feedback notches and cuts-only presets on the MR18 cannot leak into the stream. A web guide lists the tap options as Analog, Input, Pre EQ, Post EQ, Pre Fader and Post Fader, each with a "+Mute" variant. **No tap carries per-channel post-effects audio** ([TridentSound via search summary](https://vk.ru/@tridentsound-naznachenie-usb-vyhodov-pri-zapisi-multitreka-s-xr18-i-mr18)), so the server has to build all effects itself. Alan also warns that "Behringer's own graphic… is wrong about the position of the highpass filter" relative to one tap point ([Alan Hamilton, tap points](https://www.youtube.com/watch?v=hUxVALTQ3Po)). At the first soundcheck, engage the MR18 low-cut on one channel and check whether the server feed changes **[UNVERIFIED/inferred test]**. On the USB Returns page, the "off analog" setting keeps every channel fed from its preamp rather than the computer ([Alan Hamilton](https://www.youtube.com/watch?v=xYmJGyroVe0); [Drew Brashler virtual soundcheck, 82k](https://www.youtube.com/watch?v=cGROKcBcjRc)) **[V: 2 channels]**.

Three practical details follow from this. First, the Analog tap still follows the **preamp gain**. Drew shows a kick clipping in the DAW and fixes it with channel gain, aiming for "nominal… about −18, −20" ([157k](https://www.youtube.com/watch?v=y4kxfwblFTs)). The user's "never touch preamp gain" rule therefore means a *human* checks the raw headroom once at soundcheck and then locks it. The cloud agent has no write path to the MR18 at all. Second, USB sends 17/18 default to the Aux In. Drew suggests repointing them to **Main L/R** to record a reference mix when the aux input is unused ([157k](https://www.youtube.com/watch?v=y4kxfwblFTs)) **[V: 157k]**. For this band, a better use is a **stereo audience/ambience pair on the Aux In** (see the bus section), with 17/18 left at the default **[UNVERIFIED/inferred choice]**. Third, set the clock to **48 kHz** on the MR18 first, then match it on the laptop's ASIO host with the Behringer driver. One engineer needed an older driver as well as the newest ([Alan Hamilton](https://www.youtube.com/watch?v=xYmJGyroVe0); [Drew Brashler](https://www.youtube.com/watch?v=y4kxfwblFTs)) **[V: 2 channels]**. X-Air also has a Dugan-style automix ([Behringer "Auto Mixing in Depth", 153k](https://www.youtube.com/watch?v=FQrVHU0AClc)) **[V: official]**. It shares gain between speech mics, so it is irrelevant to a band mix and does not touch the Analog USB sends.

**The loudness target moves from −14 to −16 LUFS integrated.** The earlier −14 came from YouTube's *upload/VOD* normalisation reference. No official YouTube document gives a live-stream target ([Sweetwater summary](https://www.sweetwater.com/insync/?p=225563)). Engineers who actually stream say: "For most of our streaming platforms, we should be targeting −16 LUFS" ([Drew Brashler, 109k](https://www.youtube.com/watch?v=2jhggSKR2AI)). Another: "if I were to calibrate it to YouTube it's −14, which is fairly hot… I usually shoot for −16" ([Michael Curtis, 6.4k](https://www.youtube.com/watch?v=tpFsW1G-sVg)) **[V: 2 channels, 109k + 6.4k]**. The decisive fact is asymmetry. "YouTube music will not apply positive gain on a quiet master" ([Mixdown Online, 147k](https://www.youtube.com/watch?v=VKpCaFST6zU)), and "YouTube will leave it where you had it" ([The Frugal Streamer](https://www.youtube.com/watch?v=s0vt6gK7DMo)) **[V: 2 channels, 147k]**. At −16 the stream plays only 2 dB quieter than a −14 reference. It keeps 2 dB more groove dynamics and more headroom for the 128 kbps AAC encoder, and the VOD archive will never be turned down. A −14 master would need about 2 dB more limiting to sound no louder after normalisation. The agent should accept −15 to −17 LUFS-I across a song. To check in production, right-click the player → Stats for nerds: "content loudness −3.8 dB" means about −17.8 LUFS ([Michael Curtis](https://www.youtube.com/watch?v=tpFsW1G-sVg)). One unverified engineer claims YouTube does not touch live-stream loudness at all, which would make the archive's behaviour the only normalisation that matters.

## Sixteen channel strips, rebuilt from verified numbers

Each strip runs in this order: polarity/delay → HPF/LPF → gate (kick only) → EQ → compressor (auto make-up matched to bypass loudness) → de-esser where listed → fader/pan → sends. Faders are server dB starting from the band's test-rig balance **[U]**. The FOH app's "cuts only, no make-up" restriction does not apply here: the USB feed has no acoustic loop, so the feedback rings the user saw at 129, 160, 196, 226 and 3377 Hz are irrelevant **[U]**.

### Drums: kick gated lightly, snare never gated (channels 1–3)

The high-view drum tutorials agree on three points. Put a **partial-range** gate on the kick, never on the snare: "I gate the kick, I do not gate the snare" ([A, 227k](https://www.youtube.com/watch?v=H9NbaELL6nE)). Ross Stratton removes snare gates because "you might miss some intricate parts" ([E](https://www.youtube.com/watch?v=FIlwKWlfXc0)). Ghost notes are the funk snare's identity, so this decision matters more than any EQ value. And the kick compressor needs a **slow-ish attack** so the beater click passes: "transients on kick drums are somewhere between 30 and 50 ms" ([B, 215k](https://www.youtube.com/watch?v=WxOnpsuAsqw)).

| Ch | Stage | Starting value | Status |
|---|---|---|---|
| 1 Kick | Fader / pan | −10.0 dB / C | [U]; centre [V: FF 322k] |
| 1 | HPF | **None** | [U rule] — **[CONFLICT]** D (222k) high-passes at ~38 Hz; rule wins |
| 1 | Gate | Range **12 dB** (up to 20), attack fastest (~0.5 ms), hold **45 ms**, release **10 ms**; key HPF ~200 Hz on the beater | [V: A 227k; range corroborated by 2 more channels]; key freq **[CONFLICT]** 60 Hz in a 2.5k video |
| 1 | EQ | −3 dB @ **285 Hz** Q≈1.5 (low-mid scoop) | [V: D 222k; E's 150 Hz dip, 2 channels on the scoop] |
| 1 | EQ | −2 dB @ **118 Hz** only when bass masks | [V: K 219k] |
| 1 | EQ | +2 dB high band @ ~16 kHz (click) | [V: D 222k] |
| 1 | EQ | +2 dB @ 60 Hz "thud" | [UNVERIFIED/inferred] (D boosts lows without a stated frequency) |
| 1 | Compressor | **4–5:1**, attack **25–30 ms**, release **70–100 ms**, **2–4 dB GR**, hard knee | [V: 5 channels, B 215k + C 145k + 3 more] — **changed** from earlier 4:1/10 ms |
| 1 | Sends | Short room −22 dB; pre-fader to DRUM PARALLEL | "a little reverb" [U]; level [UNVERIFIED/inferred] |
| 2 Snare | Fader / pan | −14.9 dB / C | [U] |
| 2 | HPF | **100 Hz** | [V: 2 channels, D 120 Hz 222k + E 100 Hz] — **changed** from 80 Hz |
| 2 | Gate / expander | **None** | [V: 2 channels, A 227k + E] — **changed**: earlier 8 dB expander removed |
| 2 | EQ | −3 dB @ **420 Hz** Q≈2 (box) | [V: 2 channels, D ~415 Hz + E 460 Hz] |
| 2 | EQ | +2 dB @ **2.5 kHz** ("translates… small speakers") | [V: F 387k] — **changed** from +2.5 @ 5 kHz |
| 2 | EQ | +2 dB @ **8 kHz** (crack; limited by hi-hat bleed) | [V: F 387k] |
| 2 | EQ | 200 Hz: 0 dB start, agent may move ±2 | **[CONFLICT]** F boosts for fatness, E cuts "too much body" |
| 2 | Compressor | **4:1 peak, attack 15 ms, release 50 ms**, 3–6 dB GR (lifts ghost notes and rolls) | [V: C 145k]; GR [UNVERIFIED/inferred]. Alternative "explosive" 7:1 / 50 ms / 90 ms [V: B 215k] |
| 2 | Sends | Short room −15 dB; pre-fader to DRUM PARALLEL | [U] / [UNVERIFIED/inferred] |
| 3 OH | Fader | −23.4 dB, auto-mute when no signal | [U] |
| 3 | HPF | **180 Hz** | [V: 2 channels, D 200 Hz + E 160 Hz] |
| 3 | Compressor | 4:1, attack 15 ms, 1–2 dB GR | ratio/attack [V: B 215k]; GR [UNVERIFIED/inferred]. "Almost uncompressed" OH in the D'Angelo *Voodoo* sound is [UNVERIFIED, 55k] |

### The bass pair: compress hard, define in the mids, carve with the kick (channels 12 and 14)

Bass carries the strongest consensus in the dataset. Four channels high-pass bass at about 40 Hz; that conflicts with the user's rule, so it is not applied. The verified sources also agree on hard compression, ratio 4:1, with "about 5 to 10 dB of compression" and an attack near 20 ms because "too fast thins out the bass" ([G, 198k](https://www.youtube.com/watch?v=ctBDFPnhrOs)). They agree that small-speaker definition comes from **midrange, not lows**: "resist the urge to boost lows… boost around 800 Hz" ([H, 160k](https://www.youtube.com/watch?v=FNa7avcUUSM)). For the MR18 family specifically, the XR18 "Bass" compressor preset has 6 dB of make-up gain built in ([H](https://www.youtube.com/watch?v=FNa7avcUUSM)). Saturation for phones is verified in principle across three channels. Upper harmonics "separate the two instruments with less low-frequency phase interference" ([L, 243k](https://www.youtube.com/watch?v=27ewHn5SAiI)), and Maserati adds tape and distortion for "energy" ([M, 144k](https://www.youtube.com/watch?v=x8uzol0NixE)). The synth-bass rule comes from Maserati: EQ *before* the compressor, reduce the synth's low-mids "so it's not stepping on the real bass", and focus its push "around that 50 to 60 Hz area" ([M](https://www.youtube.com/watch?v=x8uzol0NixE)). Scheps states the division of labour: "the kick needs to be a very consistent bottom… the bass will be more of a melodic low end" ([K, 219k](https://www.youtube.com/watch?v=BMW4K7FzQp8)).

| Ch | Stage | Starting value | Status |
|---|---|---|---|
| 12 Bass DI | Fader / pan | −10.0 dB / C | level matched to kick and DI2 [UNVERIFIED/inferred]; centre [V: FF 322k] |
| 12 | HPF | **None** | [U rule] — **[CONFLICT]** 4 channels (J 415k, G, H, I) use 40 Hz; rule wins |
| 12 | LPF | **6 kHz** (string/fret noise) | [V: 3 channels, H + G + I] |
| 12 | EQ | −2 dB @ **250 Hz** Q≈1.5 (mud) | [V: 3 channels, J 240 Hz + H 250 Hz + 550 Hz on X32] — **changed** from 350 Hz |
| 12 | EQ | +2 dB @ **800 Hz** Q≈1 (notes on phones) | [V: H 160k; Scheps' "honky" mids K 219k] |
| 12 | EQ | +1.5 dB @ **2.5 kHz** (string attack, 2–4 kHz) | [V: H 160k] |
| 12 | Compressor | **4:1 soft knee, attack 15 ms (10–20), release 150 ms (100–250), 6–9 dB GR**; detector sidechain HPF | [V: 4 channels on 4:1; G 198k + I 113k + H 160k on timing and GR] — **changed** from the earlier two-stage 8:1 + 3:1 |
| 12 | Kick-keyed duck | Dynamic EQ band at kick fundamental (~55–60 Hz), **−3 to −4 dB**, attack 10 ms, hold 50 ms, release ~130 ms | principle [V: K + L + G, 3 channels]; numbers [UNVERIFIED: N 74k] — **changed** from −2 dB/5 ms/80 ms |
| 12 | Parallel saturation send | Send → LPF 400 Hz → saturate → HPF 150 Hz → return ~25% wet (−12 to −15 dB under dry) | saturation [V: 3 channels, L 243k + M 144k + Q]; 25% [UNVERIFIED: Q 41k]; filter design [UNVERIFIED/inferred] |
| 14 Synth bass | Fader / pan | −9.8 dB / C, mono below 120 Hz | [U]; mono [UNVERIFIED/inferred] |
| 14 | HPF | **None** | [U rule]; Maserati's "get rid of things below" 50 Hz is **[CONFLICT]** |
| 14 | EQ (pre-comp) | −3 dB @ 300 Hz Q≈1 (low-mids); +1.5 dB @ 55 Hz (sub focus); +1.5 dB @ 1.5 kHz (high-mid) | moves [V: M 144k]; exact values [UNVERIFIED/inferred] |
| 14 | Compressor | 3:1, attack 20 ms, release 150 ms, 2–4 dB GR, driven by the EQ'd low end | [UNVERIFIED/inferred] |
| 14 | Kick-keyed duck | As channel 12 | as channel 12 |

When both basses play, the electric bass carries 100 Hz–1 kHz and the synth carries the sub. No source gave crossover numbers, so this split is **[UNVERIFIED/inferred]** from Scheps and Maserati.

### Keys and guitars: stay out of 1–4 kHz, where the singer lives (channels 4–8)

The keys finding that changes the earlier preset comes from two channels: **1–2 kHz decides whether a keyboard is foreground or background**. "More 1–2 kHz… is literally like the difference between the piano being a background instrument and… a priority instrument" ([HMSP, 64k](https://www.youtube.com/watch?v=fM9OwnQ_uRI)), and you "may even need to cut a little in this area" ([CWK, 93k](https://www.youtube.com/watch?v=XJaEkLbxoEk)) **[V: 2 channels]**. The earlier +1 dB Rhodes "bark" at 1.5 kHz therefore becomes a dip. Keys compression should "barely move". Pensado's Jill Scott Rhodes "meter didn't move", and a light touch is the goal ([PEN, 99.5k](https://www.youtube.com/watch?v=FmdQsxbR5Oc); [ATK, 83k](https://www.youtube.com/watch?v=UXF70zgc-Q4)) **[V: 2 channels, qualitative]**. Guitars converge on an HPF near 90–100 Hz and a small notch "right around 4K" ([HMSG, 178k](https://www.youtube.com/watch?v=xYK-GM3MPD8)). Cory Wong, Vulfpeck's funk guitarist, uses "90… dip a little bit around 4k" with a compressor at about 50% mix, because more "starts to feel choked" ([CWONG, 526k](https://www.youtube.com/watch?v=Z3fStcglxoQ)) **[V: 2 channels, 178k + 526k]**.

| Ch | Stage | Starting value | Status |
|---|---|---|---|
| 4 Acoustic DI | Fader / pan | −14 dB (muted until active) / L20 | [UNVERIFIED/inferred] |
| 4 | HPF / EQ | HPF **100 Hz**; −2.5 dB @ **250 Hz**; −3 dB narrow @ **~1 kHz** (search 900 Hz–1.2 kHz, or 315/630 Hz octaves); +1.5 dB shelf @ **12 kHz** | [V: 2 channels, ATA 106k + OTM 106k] |
| 4 | Compressor | Fast attack, soft knee, medium release → 3:1, 5 ms, 150 ms, ~3 dB GR | character [V: ATA 106k]; numbers [UNVERIFIED/inferred] |
| 4 | Reverb | Off, or instrument plate ≤ −24 dB ("in a live setting I rarely add reverb") | [V: ATA 106k] — **changed** from −18 |
| 5 Guitar amp | Fader / pan | −12 dB / L30; +2 dB in SOLO state | [UNVERIFIED/inferred] ("medium" [U]) |
| 5 | HPF / EQ | HPF **100 Hz**; −2 dB narrow @ **4 kHz**; solo state +2 dB @ **2–2.5 kHz** (bite); +1 dB @ 5 kHz only if pick scratch is lost | [V: HMSG 178k + CWONG 526k] |
| 5 | EQ | −2 dB @ 350 Hz; LPF 12 kHz ("tiny top-end roll-off") | [UNVERIFIED/inferred]; roll-off concept [V: CWONG] |
| 5 | Compressor | ~4:1, 10 ms, 100 ms at **50% wet/dry** | 50% mix [V: CWONG 526k]; ratio/timing [UNVERIFIED/inferred] |
| 5 | Sends | Short room −20 dB; delay −20 dB on solos | "a little reverb" [U]; levels [UNVERIFIED/inferred] |
| 6+7 Piano/Rhodes/pads | Fader / pan | **−10.0 dB, floor −13 dB**, grouped / L60–R60 | [U]; width [UNVERIFIED/inferred] |
| 6+7 | HPF | 35 Hz subsonic only (keeps the "rich low-mids") | [U intent]; Nic Hard's "HPF to the lowest note" is [UNVERIFIED, 66k] |
| 6+7 | EQ | +1 dB @ 200 Hz Q0.8 (rich); −2 dB @ **500 Hz** Q≈2 (mud, 400–600 Hz); **−1.5 dB @ 1.5 kHz** Q≈1 (sit behind); −2 dB @ 3 kHz; −1.5 dB @ 4.5 kHz; no 5 kHz boost | 1–2 kHz role [V: 2 channels, HMSP + CWK] — **changed** from +1 dB; 3/4.5 kHz cuts [U prior app]; 500 Hz [UNVERIFIED: CWK 93k]; 200 Hz [UNVERIFIED/inferred] |
| 6+7 | Compressor | 2:1, attack 30 ms (lets the hammer through), release 200 ms, **1–3 dB GR** | light touch [V: 2 channels, PEN + ATK]; 2:1 [U prior app] |
| 6+7 | Sends | Instrument plate −14 dB; optional chorus/Dimension-style width only if it passes a mono check | plate [UNVERIFIED/inferred]; chorus [UNVERIFIED: PEN, single] |
| 8 Guitar DI / GT board | Fader / pan | −13 dB / R30 | [UNVERIFIED/inferred] |
| 8 | HPF / EQ | HPF **120 Hz** (150 Hz for chicken-scratch; clean guitar tolerates up to 200 Hz); −2 dB @ **4 kHz**; LPF 9 kHz for modeler fizz | HPF range and 4 kHz [V: HMSG + CWONG]; LPF [UNVERIFIED/inferred] |
| 8 | Compressor | 50% parallel, ~4:1, 10/100 ms, 2–4 dB GR | mix [V: CWONG]; numbers [UNVERIFIED/inferred] |

### Vocals: ride for intelligibility, cut 250–300 Hz, add air not 4 kHz (channels 9 and 10)

The most-viewed sources in the dataset are vocal tutorials, and they correct the earlier report in two places. First, **4 kHz is "where the harshness… the piercing quality" lives**, especially on female voices ([COLT, 1.01M](https://www.youtube.com/watch?v=Wq1di2luMcs); [WSG](https://www.youtube.com/watch?v=NeqfK1Z9JKI)). The earlier +2 dB at 4 kHz is removed, and presence moves to air at about 10 kHz ([AHV, 403k](https://www.youtube.com/watch?v=oP4sdpkkNhY)). Second, the verified compressor attack is **10–15 ms, not 5 ms**: Collaborate Worship uses 3:1, about 10 ms and about 50 ms, warning that "if you compress more than 6 dB the vocal starts to sound lifeless" ([CWV, 809k](https://www.youtube.com/watch?v=nF0uezOA4UA)). Attaway uses 4:1 at 12–15 ms and 250 ms, and notes that a **slower attack sounds thicker**, which suits a "warm, intimate" neo-soul voice ([ATC, 258k](https://www.youtube.com/watch?v=vcdwTwAXjmg)) **[V: 3 channels]**. Male versus female differs mainly in where body sits. "Higher end male voices and most female voices don't have a lot of 100 Hz… 200 on a female… is where the warmth and body lies" ([COLT](https://www.youtube.com/watch?v=Wq1di2luMcs)). For a thin male voice, boost about 160 Hz, never 80 Hz ([AHV](https://www.youtube.com/watch?v=oP4sdpkkNhY)). Vulfpeck's touring engineer describes the job that StageMix could not do: "My main job during the show is to ride the solo instruments and then the vocals." He adds a multiband compressor that tames low notes and S's ([VULF, 305k](https://www.youtube.com/watch?v=g-HC64mO9-Q)). Bleed from the band should be kept rather than gated out, because over-processing it makes "the cymbals… really loud then… out" ([Warren Huart](https://www.youtube.com/watch?v=y1q5e3jYfZc); [Audiotree](https://www.youtube.com/watch?v=1Aj_YsEFMto)) **[V: 3 channels]**. The earlier 8 dB vocal expander therefore drops to an optional 3 dB.

| Ch | Stage | Male / female starting value | Status |
|---|---|---|---|
| 9 Vocal Centre | Fader / pan | −2.0 dB / C | [U]; centre [V: FF] |
| 9 | HPF | **100 Hz** male / **120 Hz** female | 100 Hz [V: AHV 403k + COLT 1.01M]; female value inside CWV's 120–180 Hz [V: 809k] — **[CONFLICT]** CWV puts *every* vocal at 120–180 Hz |
| 9 | Gate / expander | None, or expander with 3 dB range between songs only | [V: 3 channels, embrace bleed]; 3 dB [UNVERIFIED/inferred] — **changed** from 8 dB |
| 9 | EQ body | Male +1.5 dB @ 160 Hz only if thin; female keep 200 Hz flat | [V: AHV 403k; COLT 1.01M] |
| 9 | EQ mud | **−3 dB wide @ 250 Hz (male) / 300 Hz (female)**, Q≈1.2 | [V: 3+ channels, AHV + ATE 444k + COLT; WSG −4.5 dB @ 300 Hz female] |
| 9 | EQ box | −2 dB @ **600 Hz** only if honky | [V: AHV 403k; ATE 500 ± 100 Hz] |
| 9 | EQ harsh | Female: narrow −2 dB @ **4 kHz** if harsh; male: check 2–3 kHz | [V: COLT 1.01M + WSG] |
| 9 | EQ presence | 2 kHz: 0 dB start, agent range ±2 | **[CONFLICT]** COLT: 2 kHz "pops out"; ATE: narrow cut ~2 kHz |
| 9 | EQ air | **+2 dB high shelf @ 10 kHz** | [V: AHV 403k] — **changed**: replaces +2 dB @ 4 kHz and the 11 kHz shelf |
| 9 | De-esser | Split-band, 6 kHz male / 7.5 kHz female (inside 5–8 kHz), 3–5 dB max | band [V: AHV 403k]; split points and depth [UNVERIFIED/inferred] |
| 9 | Compressor 1 | **3:1, attack 12 ms, release 150 ms (80 ms for fast lyrics), RMS detector, 3–6 dB GR** | [V: 3 channels, AHV + CWV 809k + ATC 258k] — **changed** from 5 ms/120 ms |
| 9 | Low-band/sibilance multiband | Low band catches dips into chest voice; top band backs up the de-esser | [V: VULF 305k; Audiotree corroborates] |
| 9 | Sends | Vocal reverb −8 dB ("good amount"); tempo delay −18 dB for throws | [U]; "live takes more reverb" [V: 4 channels]; levels [UNVERIFIED/inferred] |
| 10 Vocal Piano | Fader / pan | −2.3 dB / L15 | [U]; pan [UNVERIFIED/inferred] |
| 10 | Chain | Same as ch 9 with its own male/female detection; HPF 120 Hz | [U] HPF from prior app; chain as ch 9 |
| 10 | Backing role | Joins the BV bus compressed "as a package"; optional −2 dB wide 800 Hz–4 kHz so the lead stands out | package [V: TMBV 646k]; the cut [UNVERIFIED: 22k] |

### Role-switching channels: congas, guest soloists, sax, flute and harmonica (11, 13, 15, 16)

These channels have the thinnest evidence. Every horn source is under 100k views, so values count only where two channels agree, and **no engineer-level YouTube source gives harmonica numbers**. Conga brightness is verified at 4–5 kHz by two channels: the slap at "3.5–4.5 kHz" and the tumba at "4–5 kHz" ([R](https://www.youtube.com/watch?v=oLDVLFYGjQ8)), and brightness "about 5 kHz" ([S](https://www.youtube.com/watch?v=ASFeqBOGk2Q)). Horns are approached "the same exact way I would approach a vocal… lush not harsh," with fast-attack, medium-release compression ([ALI](https://www.youtube.com/watch?v=3OOwjTQABVc); [SB](https://www.youtube.com/watch?v=zpBd3MBeIFM)) **[V: 2 channels, qualitative]**.

| Ch / role | Starting preset | Status |
|---|---|---|
| 11 / 13 Congas | Fader −16 dB; pan to stage (ch 11 R35, ch 13 R50) | [UNVERIFIED/inferred]; Losada's layout (main slightly left, tumba ~9 o'clock) [UNVERIFIED: R 44k] |
| | HPF 90 Hz (under the ~200 Hz tumba / ~270 Hz conga fundamentals); −2.5 dB @ 350 Hz; **+2.5 dB @ 4.5 kHz** | 4–5 kHz [V: 2 channels, R + S]; fundamentals [UNVERIFIED: S]; HPF/mud [UNVERIFIED/inferred] |
| | 4:1, 15 ms, 80 ms, 2–4 dB GR (borrowed from snare so ghost strokes read); short room −18 dB | [UNVERIFIED/inferred] |
| 11 Guest trombone/brass | Fader −6 dB (+2 dB while soloing); HPF **100 Hz**; −2 dB @ 500 Hz; **−3 dB narrow @ 2.2 kHz**; +1.5 dB @ 10 kHz after the compressor | HPF [V: 3 channels]; 2–2.2 kHz [V: 2 channels, SB + RCS]; 400–600 Hz mud [V: 2 low-view channels]; 10 kHz [UNVERIFIED: SB] |
| | 3:1, attack 10 ms, release 120 ms, 3–5 dB GR; instrument plate −12 dB, delay −20 dB | fast/medium character [V: 2 channels]; numbers [UNVERIFIED: SB 4k] |
| 11 / 16 Third vocal or BV | Vocal chain from ch 9, HPF 120 Hz, joins BV bus | [V: as ch 9/10] |
| 15 Sax (wireless lav) | Fader −2.1 dB / L25; HPF **120 Hz** (100–200 Hz range) | [U]; HPF [V: 3 channels] |
| | −2.5 dB @ 400 Hz; **dynamic −3 dB narrow, sweep 2–2.2 kHz (fizz) and 4 kHz (harsh)**; **+2 dB shelf @ 8 kHz** | mud [V: 2 channels]; 2 kHz and 4 kHz [V: 2 channels each, RCS/SB and HRN/COLT]; 7–12 kHz air [V: 2 channels] |
| | 3:1, attack 10 ms, release 120 ms, **5–6 dB GR** (range 5–10) | GR range [V: 2 channels, FM 5 dB + RCS 9–10 dB]; timing [UNVERIFIED/inferred] |
| | Instrument plate −10 dB (short 0.5 s ambience plus ~1.5 s main); 1/8-note echo, ~33% feedback, low wet | short+main reverb [V: 2 low-view channels]; echo [V: 2 channels with ATD 107k] |
| 15 Flute role | HPF 190 Hz; −2 dB @ 350 Hz; +1.5 dB @ 1.5 kHz; wide +1 dB @ 3 kHz; dynamic −3 dB @ 5–7 kHz (breath); 5:1, ≤5 dB GR, medium attack, fastest release; quarter-note delay | **[UNVERIFIED: HRN 16k, single]** |
| 16 Harmonica | Fader −10 dB / R25; HPF 120 Hz; LPF 9 kHz | [U]; LPF [UNVERIFIED/inferred] |
| | +1 dB @ 250 Hz (warmth); **dynamic −3 to −6 dB @ 3–4 kHz, Q1.5, only above threshold**; −2 dB @ 1.2 kHz | **[UNVERIFIED/inferred]**: harp players say turn the treble down ([Tomlin Leckie, 34k](https://www.youtube.com/watch?v=pV8wgssIUdI)); implements "soften" [U] |
| | 3:1, threshold −18 dB, 20/150 ms; short room −12 dB | [U] prior app and "short room reverb" |

Role switches require **8 seconds of consistent classification**, a 2-second crossfade and an operator role-lock **[UNVERIFIED/inferred]**. The classifier itself is described in the "How the AI hears" section below.

## Buses, effects and imaging glue the band without flattening it

TV and session engineers agree on a light touch. SNL uses "very light compression… a little bit on the main bus… it barely moves" ([SNL, 112k](https://www.youtube.com/watch?v=tlmK-QCLthI)). Snarky Puppy's mixer uses "super light" SSL bus compression ([Nic Hard](https://www.youtube.com/watch?v=bNQkbY7A9XY)) **[V: 3 channels]**. Parallel drum compression is verified across two channels with different styles. Drew Brashler's X32 recipe sends **shells only** (no cymbals) into 10:1, 10 ms attack, 70 ms release and about 12 dB of gain reduction ([O](https://www.youtube.com/watch?v=C3K60IS8Pj4)). CLA uses a gentle 2:1 with 100 ms recovery and no stereo link, with **+3 dB at 60 Hz and +3 dB at 8 kHz** on the return ([P, 153k](https://www.youtube.com/watch?v=Z0eqw_3cY2A)).

| Bus | Members | Starting processing | Status |
|---|---|---|---|
| DRUMS | 1, 2, 3 | **2:1, attack 10 ms, fast release, 1–2 dB GR**; −2 dB @ 400 Hz; optional +1 dB @ 63 Hz | light glue [V: 3 channels]; numbers [UNVERIFIED: Nic Hard 66k] — **changed** from 4:1 |
| DRUM PARALLEL | 1, 2 pre-fader (shells only) | 10:1, attack **10 ms**, release 70 ms, 10–12 dB GR → return EQ **+3 dB @ 60 Hz, −2 dB @ 400 Hz, +3 dB @ 8 kHz**, blended 6–10 dB under the dry bus. "Glue" option: CLA 2:1, 100 ms, unlinked | technique and return EQ [V: 2 channels, P 153k + O]; smash numbers [UNVERIFIED: O 52k]; blend [UNVERIFIED/inferred] — **changed** from 1 ms attack |
| BASS | 12, 14, saturation return | 3:1, attack 30 ms, auto release, 1–2 dB GR; mono below 120 Hz | [UNVERIFIED/inferred]; Scheps' low-end glue on the mix bus is [V: K 219k] |
| KEYS | 6+7 | 1.5:1, 1–2 dB GR; vocal-keyed dynamic EQ −2 dB @ 1–3 kHz; **floor −13 dB** | floor [U]; keyed dip follows the verified 1–2 kHz role [V: 2 channels]; values [UNVERIFIED/inferred] |
| GUITARS | 4, 5, 8 | 2:1, 1–2 dB GR; vocal-keyed −1.5 dB @ 2.5–4 kHz | [UNVERIFIED/inferred] |
| SOLO | 15, 16, 11 (instrument roles) | Ride the featured player up 1–2 dB while soloing; −3 dB vocal-priority duck when ch 9 sings and no solo is detected | riding solos [V: 3 channels, VULF 305k + NPR 796k + Nic Hard]; amounts [UNVERIFIED/inferred] |
| VOCALS / BV | 9, 10 (+11/16 vocal roles) | Second stage 2:1, attack 10 ms, release 150 ms, 1–3 dB GR; BV sub-bus compressed as a package | two-stage chain [V: ALM 125k]; package [V: TMBV 646k]; numbers [UNVERIFIED/inferred] |
| AUDIENCE | Stereo pair on Aux In (USB 17/18) | **HPF 250–300 Hz, LPF ~10 kHz, hard L/R**, light bus compression/limiting so "all the mics sound like one crowd"; start about −10 dB; **ride up between songs and for applause**; time-align by delaying the band, not the mics | HPF [V: 4 channels]; hard pan [V: 3 channels]; riding [V: 3 channels incl. SNL 112k]; bus comp [V: 2 channels]; alignment [V: 2 channels]; −10 dB and LPF [UNVERIFIED: 78k/24k] |

Audience mics are what make a close-miked band sound live on stream. Without them a stage sounds "like singing in a tin can" ([Attaway](https://www.youtube.com/watch?v=SFEVZkiS0J4); [Ballast Media](https://www.youtube.com/watch?v=rOSAymbwsCY); [Collaborate Worship](https://www.youtube.com/watch?v=2NyFLUsz0MA)) **[V: 3 channels]**. They must stay "the sprinkles not the cake" during songs ([Attaway](https://www.youtube.com/watch?v=SFEVZkiS0J4)). SNL's A1 rides them with a foot pedal because "you have to ride applause" ([SNL](https://www.youtube.com/watch?v=tlmK-QCLthI)). One unmanned church rig ducks them about 15 dB from the drum bus with "really long" hold and release ([Ryland Russell](https://www.youtube.com/watch?v=YM3FiDcTJRU)) **[UNVERIFIED, 36k]**. The applause classifier below is the better trigger for this band. If no audience pair can be added, sources point to slightly hotter reverb sends as the stand-in.

**Effects returns (100% wet, filtered after the reverb):**

| Return | Starting setting | Status |
|---|---|---|
| Vocal reverb (hall or plate) | **Decay ~1.5 s** (1.2 s fast funk, 2.0–2.5 s ballads); **pre-delay 40 ms**, raised to 100–150 ms to push the vocal "way out in front"; return trimmed **−12 dB** for fader resolution; HPF 250 Hz / LPF 8 kHz; optional −2 dB @ 2 kHz on the return | decay [V: AHV 403k + 2nd channel]; pre-delay range, trim, filtering, 2 kHz [V: ATR 267k]; filter values [UNVERIFIED/inferred] |
| Vocal-keyed ducking on reverb and delay | Compressor on both returns keyed by ch 9: **7–8:1, 5–8 dB GR, fast attack, longer release, no make-up** — effects bloom between phrases | [V: STK 1.25M] — **new** |
| Tempo delay | **1/8 note, feedback ~40%** (verses) or **1/4 note, ~35%** (choruses); **HPF ~400 Hz**, LPF 6 kHz; 50–100 ms slap preset; 20–50 ms doubler preset | [V: ATD 107k + FM, 2 channels]; LPF [UNVERIFIED/inferred] — **changed** from 15% feedback, HPF 300 Hz |
| Instrument plate (keys, sax, guest horns) | 1.8 s, 20 ms pre-delay, HPF 300 Hz, LPF 9 kHz; sax gets an extra ~0.5 s ambience | short+long horn reverb [V: 2 low-view channels]; values [UNVERIFIED/inferred] |
| Short room (kick, snare, congas, guitar, harmonica) | 0.6 s, 5 ms pre-delay, HPF 200 Hz, LPF 8 kHz | [UNVERIFIED/inferred]; a separate "set and forget" drum reverb [UNVERIFIED: 36k] |

Broadcast mixes take **somewhat more reverb and delay than the house, ridden musically**. "I'm using louder reverbs and delays… than I normally would because it's live" ([Warren Huart](https://www.youtube.com/watch?v=y1q5e3jYfZc)). The Vulfpeck engineer says of vocal delay: "if the song doesn't call for it, I'm not going to use it" ([VULF](https://www.youtube.com/watch?v=g-HC64mO9-Q)) **[V: 4 channels]**. Reverb and delay sends are therefore the agent's main creative dials per song section.

**Stereo imaging must survive phones.** Hard-panned signals "end up almost exactly 6 dB lower in level in the mono downmix", and boosting the side channel makes parts "literally disappear in mono" ([FF, 322k](https://www.youtube.com/watch?v=spaqBr-cCFw)) **[V: 322k]**. Kick, snare, both basses and the lead vocal therefore stay centred. Width comes from panning, real stereo keys and the audience pair. The earlier optional +1 dB side shelf on the master is **removed**. Use a −4.5 dB pan law as a compromise between FabFilter's −3 dB (stereo) and −6 dB (mono-constant) laws **[UNVERIFIED/inferred]**. A light widener belongs only on the audience bus or, "a little but not too much", on the stream bus ([Ballast](https://www.youtube.com/watch?v=rOSAymbwsCY); [Ryland Russell](https://www.youtube.com/watch?v=YM3FiDcTJRU)) **[V: 2 channels]**. Nic Hard's 0/20 ms faux-stereo delay on mono synths is **[UNVERIFIED]** and must pass a mono check. The correlation meter should average above +0.3 **[UNVERIFIED/inferred]**.

**Overall balance has no YouTube-verified dB rule.** No engineer gave a numeric "vocal X dB above the band". All of them describe *riding* the vocal and the soloist so they stay intelligible ([VULF](https://www.youtube.com/watch?v=g-HC64mO9-Q); [NPR](https://www.youtube.com/watch?v=e07bI5rz6FY)) **[V: 4 channels]**. The band's test-rig faders [U] remain the starting balance. The research-based target from the earlier report still guides the agent: a lead-to-accompaniment ratio (LAR) of **+3 to +7 dB, starting at +5**. Billboard songs average about +1 dB ([Gerdes & Siedenburg](https://acoustics.org/lead-vocal-tracks-in-popular-music-go-quiet/)), but listeners prefer about +7.6 dB ([Forum Acusticum 2025](https://dael.euracoustics.org/confs/fa2025/data/articles/000716.pdf)). The target is [UNVERIFIED by YouTube; peer-reviewed]. Between songs a TALK state lifts the speaking voice. The only YouTube number is "+6 dB in the stream versus the house" for an MC mic ([Ryland Russell](https://www.youtube.com/watch?v=YM3FiDcTJRU)) **[UNVERIFIED, 36k]**.

## The stream master stays light and lets the limiter work only 3–4 dB

| # | Stage | Starting setting | Status |
|---|---|---|---|
| 1 | Subsonic guard | 20 Hz, 12 dB/oct | [U rule-compatible; UNVERIFIED/inferred]. Drew's stream-bus **40 Hz low cut** "because viewers lack subs" ([DBL](https://www.youtube.com/watch?v=2jhggSKR2AI)) is **[V: 109k] but [CONFLICT]** with the no-low-cut rule; offer it to the user as an opt-in |
| 2 | Equal-loudness stream EQ | Low shelf **+2 dB @ 100 Hz** (Drew uses up to +4), **−1 dB broad @ 800 Hz**, **+1.5 dB high shelf @ 10 kHz** ("sparkle back" after room/audience mics) | direction [V: 2 channels, DBL 109k + WV 100k]; exact values [UNVERIFIED/inferred] |
| 3 | Glue compressor | **2:1, attack 30 ms, auto release, 1–2 dB GR ("barely moves")** | light glue [V: 3 channels, SNL + Nic Hard + Churchfront]; timing from earlier web sources |
| 4 | Multiband (optional) | 4 bands, 1.5–2:1, 1–3 dB per band; placed late because it adds latency | placement [V: WV 100k]; numbers [UNVERIFIED/inferred] |
| 5 | Slow leveler | ±3 dB, multi-second time constants, catches song↔talk jumps | [UNVERIFIED/inferred] |
| 6 | **True-peak limiter** | **Ceiling −1 dBTP**, attack ≤0.5 ms, release **100–150 ms**, stereo link on, drive set so peaks show **≤3–4 dB GR** | −1 ceiling [V: 3 channels]; GR [V: 3 channels, CWL 99.5k + 2]; attack/release/link [V: 2 channels, DBL 109k + CWL]; true-peak mode [UNVERIFIED/inferred] — **changed** from −1.5 dBTP |
| 7 | Metering | BS.1770 momentary/short-term/integrated, true peak, LRA, correlation | [official: EBU Tech 3342](https://tech.ebu.ch/publications/tech3342) |
| — | Targets | **−16 LUFS-I (±1 LU)**; song short-term −18 to −14; talk −18 to −20; ≤ −1 dBTP | [V: 2 channels for −16]; ranges [UNVERIFIED/inferred] — **changed** from −14 |

On the X32/XR family the limiter starts at +12 dB input, and then "adjust the input gain so the gain reduction meter… reads no more than three or four dB… higher than that you'll start to notice the limiter kind of sucking in" ([CWL](https://www.youtube.com/watch?v=5jA7-GLzt0M); [DBL](https://www.youtube.com/watch?v=2jhggSKR2AI)). On the server, the drive becomes a *result* of the −16 target, not a fixed preset. If hitting −16 needs more than 4 dB of limiting, the balance or EQ upstream is wrong. The fix belongs in the buses, not the limiter. A Waves broadcast engineer keeps L3 limiting to "about 3 dB… at the very most" ([WV, 100k](https://www.youtube.com/watch?v=LCgUWA8D2Zs)). Pushed harder, a stream limiter exposes snare brightness and low-end distortion ([Ascension Worship](https://www.youtube.com/watch?v=XpkYd09WFXc)) **[UNVERIFIED, 45k]**. Run the internal mix at 48 kHz. YouTube's live encoder spec is AAC at **128 kbps stereo, 44.1 kHz** ([YouTube Help](https://support.google.com/youtube/answer/2853702?hl=en)) **[V: official]**, so resample only at the encoder.

### What changed from the earlier report

| Item | Earlier (inferred) | Now | Evidence |
|---|---|---|---|
| Loudness | −14 LUFS, −1.5 dBTP | **−16 LUFS, −1 dBTP, ≤3–4 dB GR** | 2 channels on −16; 3 on −1 and on GR |
| MR18 USB tap | "verify pre-processing" | **Analog tap, 1:1** | 2 channels, 157k |
| Kick gate / comp | range 25 dB, hold 30 ms / 4:1 at 10 ms | **12–20 dB, 45 ms / 4–5:1 at 25–30 ms** | A 227k; 5 channels |
| Kick EQ | −4 dB @ 350 Hz | **−3 dB @ 285 Hz** (+ −2 dB @ 118 Hz on demand) | D 222k; K 219k |
| Snare | expander 8 dB, HPF 80, +2.5 dB @ 5 kHz, 120 ms release | **no gate, HPF 100, +2.5 & +8 kHz, 15/50 ms** | 2 channels; F 387k; C 145k |
| Bass DI | two-stage 8:1 + 3:1, −2.5 dB @ 350 Hz | **single 4:1, 15/150 ms, 6–9 dB GR, −2 dB @ 250 Hz** | 4 and 3 channels |
| Kick→bass duck | −2 dB, 5/80 ms | −3 to −4 dB, 10/50/130 ms (numbers unverified) | principle 3 channels |
| Lead vocal | +2 dB @ 4 kHz; 3:1 at 5 ms; 8 dB expander | **no 4 kHz boost, +2 dB @ 10 kHz air; 3:1 at 12 ms; ≤3 dB expander** | 1.01M; 3 channels |
| Keys | +1 dB @ 1.5 kHz | **−1.5 dB @ 1.5 kHz** | 2 channels |
| Delay | 15% feedback, HPF 300 Hz | **35–40% feedback, HPF 400 Hz, vocal-ducked FX** | ATD 107k; STK 1.25M |
| Drum bus / parallel | 4:1 bus; 1 ms parallel attack | **2:1 light bus; 10 ms parallel, +3 dB @ 60 Hz/8 kHz return** | 3 channels; P 153k |
| Master M/S | optional side +1 dB > 10 kHz | **removed** | FF 322k |

## Raw PCM over SRT feeds a Carla-hosted server that the agent can address

The YouTube evidence leaves the transport and server design from the earlier research unchanged. The **venue laptop only captures and sends**. It runs the Behringer ASIO driver at 48 kHz with all 18 channels selected; one Windows user found capture worked only that way ([Audacity forum](https://forum.audacityteam.org/t/multitrack-recording-behringer-x18/45653)). It uses wired Ethernet rather than Wi-Fi, which adds jitter ([SonoBus](https://sonobus.net/)), and Studio One keeps recording a local backup. Sixteen channels at 48 kHz/24-bit is **18.4 Mbps** raw, or about 22 Mbps with the audience pair, so plan for 25–35 Mbps of uplink. **SRT in caller mode** with a 300–1000 ms latency window carries one sample-locked stream: either 18 channels of `pcm_s24le` in Matroska/NUT (untested, verify first), or SMPTE 302M, which FFmpeg supports only in 2/4/6/8-channel streams ([FFmpeg source](https://ffmpeg.org/doxygen/4.0/s302menc_8c_source.html)). The fallback is JackTrip, which has no retransmission ([jacktrip](https://man.archlinux.org/man/extra/jacktrip/jacktrip.1.en)). Clock drift between the MR18 and the server reaches roughly half a second over three hours at 50 ppm. It needs an adaptive resampler such as zita-ajbridge's control-loop approach ([zita-ajbridge](https://kokkinizita.linuxaudio.org/linuxaudio/zita-ajbridge-doc/quickguide.html)) or FFmpeg `aresample=async`.

On a **dedicated-vCPU DigitalOcean droplet**, which avoids noisy neighbours ([DigitalOcean](https://docs.digitalocean.com/products/droplets/concepts/choosing-a-plan/)), JACK or PipeWire runs at 48 kHz with 256–512-frame buffers. **Carla** hosts LSP Plugins (gate, EQ, compressor, dynamic EQ, multiband) and the x42-dpl true-peak limiter, with "full OSC control" of every parameter ([Carla](https://git.kx.studio/falkTX/Carla/src/commit/240132bd9acce75b427afa73ea6febfa882c8aa9); [LSP](https://github.com/lsp-plugins/lsp-plugins); [x42-dpl](https://rg42.org/oss/lv2/dpl)). That OSC surface is the agent's only write path, and a deterministic controller sits in front of it. Video runs on its own path: phone cameras over WebRTC, through a compositor, encoded as H.264 1080p60 with a 2 s (120-frame) keyframe interval over RTMPS ([LiveKit Egress](https://docs.livekit.io/server/egress); [streamer.guide](https://streamer.guide/guides/bitrate-encoder-settings-cheat-sheet)). Secondary sources disagree on bitrate, so confirm it on YouTube's official settings page. A/V sync cross-correlates each phone's own audio against the board mix with GCC-PHAT every 5–10 s ([MathWorks](https://www.mathworks.com/help/phased/ref/gccphat.html)). It median-filters the offsets and holds the board audio at the slowest video path's delay. A soundcheck clap gives the initial offsets. The same correlation gives the audience-pair alignment delay, replacing the balloon-pop method the YouTube engineers use.

## How the AI hears the mix

StageMix failed for two reasons that no amount of preset tuning fixes. By the user's account it had **no sound recognition**. It processed "channel 11" the same whether a conga, a third singer or a trombone was in front of it. It also had **no oversight of whether the result sounded great**. Its cuts-only FOH chains [U] were judged by meters and rules, never by listening. The YouTube engineers describe mixing as continuous listening and reacting: riding solos and vocals all show, pulling audience mics up "because of the cheers", riding delay "musically" ([VULF](https://www.youtube.com/watch?v=g-HC64mO9-Q); [Warren Huart](https://www.youtube.com/watch?v=y1q5e3jYfZc)). The new design therefore gives Claude four layers of hearing, each faster and dumber than the one above it. Everything in this section is **[UNVERIFIED/inferred] system design** anchored to the cited research. None of it comes from YouTube.

**Layer 1 is fast on-server classifiers (about 1 s).** Small audio models run on each stem and on the program bus at about 1 s hops. Per stem, they detect activity (is this source playing?) with an envelope follower like the one MedleyDB used to label instrument activations ([arXiv 1511.05520](https://arxiv.org/pdf/1511.05520)). They also classify instrument and role, so channel 11 reads as conga, voice or brass, channel 15 as sax or flute, and channel 16 as harmonica or voice. For channels 9 and 10 they estimate singer register/gender from median f0 and formants, which drives the male/female HPF and de-esser presets. On the program bus they detect **solo** (a source active, louder than its section baseline and melodically novel while the lead vocal rests), **applause/crowd**, **talk versus song**, and **feedback or howl**. Howl detection uses the peak-to-harmonic and peak-to-neighbour criteria from the notch-suppression literature ([van Waterschoot & Moonen](https://ftp.esat.kuleuven.be/pub/SISTA/vanwaterschoot/abstracts/09-207.html)). A howl would come from the venue PA leaking into mics, and the broadcast should then duck that channel. Frame-level instrument-activity detection can reach F1 of about 0.96 on curated data ([LLark, arXiv 2310.07160](https://arxiv.org/pdf/2310.07160)). Stage bleed is the known failure mode: one study discarded bleed-affected stems to get valid labels ([arXiv 2506.21167](https://arxiv.org/abs/2506.21167v1)). Calibrate thresholds against the room's bleed at soundcheck. Optionally clean analysis signals with a real-time separator of about 23 ms latency ([HS-TasNet](https://arxiv.org/abs/2402.17701)). Classifier outputs never move audio directly. They raise *events* with confidence, such as `ch11_role=brass (0.91, 9 s)`, and the controller applies the hysteresis rules.

**Layer 2 is objective quality metrics (continuous).** The server computes the numbers an engineer reads off meters and analysers:

- BS.1770 loudness (momentary, short-term, integrated) and true peak against the −16 LUFS / −1 dBTP targets
- **tonal balance** of the program against reference curves built from three or four tracks the band likes, as iZotope's genre targets do with thousands of masters ([Splice](https://splice.com/blog/how-to-mix-izotope-neutron))
- **vocal clarity**: gated LAR plus a masking index of the music bus against ch 9 in the 1–4 kHz band
- **kick–bass conflict**: coincident energy below 120 Hz on kick hits
- **harshness**: excess energy at 2–5 kHz relative to the reference curve, with a separate flag per source for harmonica and sax
- **mono compatibility**: correlation and mono-minus-stereo loudness loss
- limiter gain reduction, as an upstream-problem alarm

Masking metrics "correlate poorly with perceived masking" ([Hafezi & Reiss](https://aes2.org/publications/elibrary-page/?id=17637)). They tell Claude *where to look*, not whether the mix is good.

**Layer 3 is a hosted real-time audio-language "listener".** This is the oversight StageMix lacked. Every 5–10 s the server sends a short clip of the program mix to a hosted audio-native model. It sometimes adds a soloed stem or the shadow-mix candidate. The model answers Claude's structured questions with a verdict and confidence. Examples: "Is the lead vocal intelligible over the band? Is anything harsh or piercing? Is the bass audible on a phone-sized speaker? Did the change between clip A and clip B make it better, worse or the same? Is someone soloing, and on what instrument?" The user chose a hosted model. By the user's own estimate, **Gemini Live is the cheapest option at roughly $1–2 per 3-hour show**, with **OpenAI's realtime audio model** as the alternative. This research did not verify either price, so check both against current pricing pages before launch. Questions must be specific and comparative ("A or B?"), because absolute quality ratings from a single model drift. Only program audio is sent, never private talkback.

**Layer 4 is Claude as director.** Claude reads events (layer 1), metrics (layer 2) and listener verdicts (layer 3) every few seconds. It decides only bounded setpoint changes, then **verifies by listening again**. Every change runs first on the shadow mix. The listener compares before and after clips, and the change commits only when the metrics improve *and* the listener prefers it, or at least does not prefer the old version. If a change ships and the next two listener checks say "worse", it rolls back automatically. Claude acts on the listener alone only for small, reversible moves such as a ±1 dB send. Larger moves need agreement from the metrics. This closes the loop StageMix never had: hear what is happening, decide, change, listen again.

## Claude controls through clamps and learns from replayed shows

The earlier report's two-layer control design stands, and the YouTube evidence sharpens what the agent should spend its moves on. A fast deterministic layer runs at audio rate: compressors, de-essers, kick-keyed ducking, vocal-keyed FX ducking, the vocal rider and the limiter. Claude acts every 2–10 s, writing setpoints that a controller ramps toward. This also reconciles the user's "lock vocals once balanced" rule with every engineer's "ride the vocal" practice. The **fader baseline** locks, and the deterministic rider and multiband do the riding within ±3 dB **[UNVERIFIED/inferred]**.

| Control | Max per action | Rate / ramp | Hard clamp | Rule overlay |
|---|---|---|---|---|
| Fader | 1.5 dB | ≤3 dB per 10 s; ramp ≥300–500 ms; same parameter ≤ once per 8 s | −12/+6 dB from soundcheck | Kick, snare, OH, vocals locked (±1 dB); bass deadband 2.5 LU; piano floor −13 dB [U] |
| EQ band | 1 dB | ramp ≥200 ms | ±6 dB from preset; Q fixed | No HPF on 1, 12, 14 [U] |
| Compressor threshold | 2 dB | ramp ≥200 ms | ±6 dB | Bass GR stays 4–10 dB; vocal GR ≤6 dB (per CWV) |
| FX sends | 2 dB | per song section | −40 dB to preset +4 | Ch 9 vocal reverb ≥ −14 dB in SONG [U] |
| Solo lift | +1 to +2 dB | several seconds minimum dwell | +3 dB | Only on classifier solo event ≥ 4 bars |
| Audience bus | 3 dB per step | 0.5–1 s ramp on applause event | −30 to 0 dB | Down during songs |
| Pan, master limiter | none live | preset load only | limiter always on, ≤ −1 dBTP | — |
| MR18 (any parameter) | **no write access** | — | — | "Never touch preamp gain" [U] |

Every action passes hysteresis (enter and exit thresholds, minimum dwell), the shadow-mix-plus-listener check, snapshot rollback (to last-known-good and to soundcheck baseline), and human override. A phone UI move locks that parameter for several minutes and is logged as a preference, and a global freeze drops to the static presets above. All values in this table are **[UNVERIFIED/inferred]** engineering bounds, because no YouTube or peer-reviewed source gives slew limits for automated live mixing.

**Learning across shows** happens offline, where mistakes are free. Record all 18 raw stems, the program and the full decision log. Each log entry holds the time, song section, event, metrics before and after, listener verdicts, the delta, the rationale and the outcome. After each show, replay the multitrack through the same chain. Claude proposes preset deltas and runs A/B comparisons with the listener model on the replay. It promotes a delta only if it wins on that show *and* on earlier shows' stems, which prevents overfitting to one night. Presets are keyed by song and by performer, because channel 11 or 15 can be a different guest every week. Ch 9's register setting is learned per singer. The band's or engineer's ratings tune a few interpretable dials (LAR target, tonal tilt, compression amount, reverb wetness), echoing the finding that one or a few parameters can approach a professional EQ result ([Hafezi & Reiss](https://aes2.org/publications/elibrary-page/?id=17637)). The most valuable learning target is turning [UNVERIFIED/inferred] rows in this report into measured values. Each show's replay data is the evidence that YouTube could not supply for flute, harmonica and congas.

## Conclusion

The YouTube evidence did less to change the architecture than to change the defaults, and nearly every change points the same way: **less processing, applied later and more gently**. Slower compressor attacks, no snare gate, no 4 kHz vocal boost, keys pulled back from 1–2 kHz, glue that "barely moves", and a quieter −16 LUFS master with only 3–4 dB of limiting all describe the open, dynamic sound of SNL, Tiny Desk and Vulfpeck's crew. That is better news for a neo-soul/funk band than the earlier, more aggressive inferred chain. The evidence is also lopsided. Drums, bass, lead vocal, guitars and the master stage are verified by videos with hundreds of thousands to a million views. Flute, harmonica, conga dynamics and every automation bound remain fallbacks. The first shows should therefore be treated as measurement sessions for exactly those channels.

The deeper lesson concerns StageMix. Its presets were not the problem. It had no ears and no judge. Engineers on YouTube describe their real job as listening and riding. An agent that classifies what each channel is, measures what the mix is doing, asks a listener model whether a change actually sounded better, and refuses to keep any change it cannot confirm is the minimum needed to replace that human loop. The clamps make it safe, and the post-show replays are where it improves.
