# Buses, Time-Based FX, Stereo Imaging and Broadcast Master Chain for Live Music on a YouTube Live Stream

Research note: WebFetch failed with DNS errors (ENOTFOUND) on mixonline.com, soundonsound.com, tech.ebu.ch, waves.com and thebroadcastbridge.com during this session. Findings below come from search-result extracts of those pages and other sources. Primary PDFs (EBU R128, Tech 3342, AES TD1008) were NOT read in full. Values marked "practitioner convention (unsourced)" come from general engineering knowledge and must not be presented as cited.

## 1. Loudness targets for YouTube live (LUFS, true peak, short-term vs integrated, R128 / A/85, LRA)

### Takeaway
Broadcast standards are -23 LUFS ±1 LU (EBU R128) and -24 LKFS ±2 (ATSC A/85), both measured with ITU BS.1770. Streaming practice centres on -14 LUFS integrated and -1 dBTP for YouTube. AES TD1008 (2021) recommends -16 LUFS for music. No official YouTube document confirms that loudness normalization applies to live streams, so treat a live mix of about -14 to -16 LUFS integrated, ceiling at -1 dBTP or lower, as the safe target. YouTube live audio is AAC at 128 kbps stereo, so leave extra true-peak headroom for the codec.

### Cited Findings
- EBU R128: target -23 LUFS ±1 LU. ATSC A/85 and ARIB: -24 LKFS ±2 LK. LUFS is identical to LKFS (ITU BS.1770) — [Lawo mc56 loudness metering docs](https://docs.lawo.com/audio-production-mc-mixing-consoles/mc56/mc56-operation/mc56-user-configuration/mc56-system-settings/mc56-system-settings-loudness-metering); [TC Electronic broadcast standards](https://www.tcelectronic.com/broadcast-standards)
- A/85 is built on BS.1770 and anchors on dialogue loudness. Since March 2013 it prescribes BS.1770-3 for all programming. A/85 and R128 "differ significantly in philosophy" — [TV Technology, Improving loudness control](https://tvtechnology.com/opinions/improving-loudness-control)
- True-peak ceilings: R128 is -1.0 dBTP and A/85 is -2.0 dBTP. Streaming services such as Spotify and YouTube also use -1.0 dBTP — [FabFilter Pro-L 2 help, output options](https://www.fabfilter.com/help/pro-l/using/outputoptions)
- AES TD1004 (2015) recommended -16 to -20 LUFS with a maximum of -1 dBTP. Its successor TD1008 (2021) recommends -16 LUFS for music, -18 for speech and -17 for mixed content — [Production Expert](https://www.production-expert.com/production-expert-1/aes-update-loudness-recommendations-for-audio-only-streaming); [Production Advice TD1008](https://productionadvice.co.uk/td1008/)
- One commentator says lossy codecs cannot handle peaks much above -3 dBTP and suggests a -3 dBTP limiter. This is opinion, not a standard. A third-party crate's docs cite TD1008 as -1.0 dBTP for encodes below 256 kbps and -0.5 dBTP at 256 kbps or above (unverified) — [Production Advice](https://productionadvice.co.uk/td1008/); [baken crate docs](https://docs.rs/crate/baken/3.0.0/source/docs/true-peak-ceiling.md)
- YouTube live encoder specs: AAC or MP3, 128 kbps stereo, 384 kbps 5.1 (AAC over RTMP/RTMPS only). Sample rate 44.1 kHz for stereo, 48 kHz for 5.1 — [YouTube Help: live encoder settings](https://support.google.com/youtube/answer/2853702?hl=en)
- YouTube's normalization of uploaded videos to about -14 LUFS (turning loud content down, never up) is described only by third-party guides. No official statement says it applies to live streams. AES is cited as saying real-time loudness processing cannot predict the rest of a live programme — [IRPR Sound guide](https://sounddesign.irpr.agency/guides/what-is-the-right-lufs-for-youtube-podcast-broadcast/); [Youlean](https://youlean.co/?p=30813)
- LRA (EBU Tech 3342, currently v4 from November 2023) measures loudness variation. R128 only says LRA "may be used" to evaluate a programme and does not set a hard limit. LRA is not recommended for programmes under 1 minute. Algorithm: 3 s short-term loudness, absolute gate at -70 LUFS, relative gate 20 LU below the mean, LRA = 95th percentile minus 10th percentile — [EBU Tech 3342 page](https://tech.ebu.ch/publications/tech3342); [cacophony.js LRA docs](https://cacophony.js.org/functions/loudnessRange.html); [EBU R 128 (Wikipedia)](https://www.wikipedia.org/wiki/EBU_R_128)
- R128 measures the whole signal, without emphasis on voice, music or effects (A/85 anchors on dialogue) — [EBU R128 v4 PDF (search extract)](https://tech.ebu.ch/docs/r/r128v4_0.pdf)

### Inferences
- A YouTube live music show should run about -14 to -16 LUFS integrated over the show, with a true-peak ceiling of -1 dBTP. Use -1.5 to -2 dBTP for margin, because the stream is AAC 128 kbps, which is well under the 256 kbps level where the stricter ceilings apply. If YouTube does normalize after the event (VOD replay), it will only turn the replay down, never up, so mixing louder than about -14 gains nothing.
- Short-term (3 s) loudness during songs will typically swing a few LU above and below the integrated value. A practical live rule is to hold song choruses around -12 to -14 LUFS short-term and MC talk around -16 to -18. This is practitioner convention (unsourced).
- A/85 is dialogue-anchored, which matters if the show has a lot of host talk: keep speech consistent and let music sit at or slightly above it.

### Gaps
- No official YouTube documentation found on whether loudness normalization or "stable volume" applies to live streams or only to the VOD archive. Recommend a test with a private or unlisted stream.
- No published numeric LRA target for music broadcast. EBU guidance is genre-dependent. Commonly quoted values of about 5–10 LU for pop/rock TV music and up to 15–20 for classical are NOT sourced here.
- The primary R128, Tech 3342 and TD1008 PDFs were not readable in this session. The R128 live-programme tolerance text was not verified directly.

## 2. How broadcast engineers build the broadcast mix (SNL, Jools Holland, Tiny Desk, Coachella), audience mics, MC talk, ducking

### Takeaway
TV and festival broadcasts use a dedicated broadcast or music-mix position (often a separate truck or console) that is independent of FOH. A music A1 mixes the band, then a broadcast or production A1 combines that music mix with host mics, audience mics and playback. Coachella-scale streams mix "for a 15-year-old's Bluetooth speaker". Tiny Desk favours a minimal-processing, natural stereo-pair sound that includes the room and audience.

### Cited Findings
- SNL: the music A1 mixes the vocals and instruments of the performance. The broadcast A1 then mixes all show elements, including the band's mixed music track — [Ferro Productions, Mike Fortunato profile](https://www.ferroproductions.com/oh-so-fortunato/)
- SNL production mixer Bob Palladino (about 40 years on the show) is the final stage. He receives audio from about 20 crew and three consoles and combines booms, lavaliers, audience mics, sound effects, playback and the house and guest bands into one broadcast sound — [Twenty Thousand Hertz, "He's mixed SNL for 40 years"](https://20k.org/episodes/snl-bobby)
- SNL50 Homecoming Concert at Radio City: Music Mix Mobile used two Lawo mc²56 consoles with 448 mic preamps (224 per desk) — [Mix, "Mixing SNL50 the Homecoming Concert for Broadcast"](https://www.mixonline.com/post-and-broadcast/mixing-snl50-the-homecoming-concert-for-broadcast); [Fast and Wide](https://www.fast-and-wide.com/faw-news/20576-snl50)
- SNL co-music engineer Josiah Gluck and associate music production mixer Teng Chen discussed SNL music mixing in a Mix blog. Details were not retrieved — [Mix, "Mixing Prince on SNL"](https://www.mixonline.com/blog/mixing-prince-on-saturday-night-live-and-what-that-has-to-do-with-ai)
- Coachella: American Mobile (owner Chris Shepard) provides real-time audio mixes for Springboard Productions' webcasts, about 40 bands and 450 songs per day. Stage racks feed control-room mixers over Dante, with Focusrite RedNet D64R MADI for real-time sample-rate conversion (96 kHz artist rigs to a 48 kHz broadcast). Mixes go to a broadcast A1 in an NEP truck, who marries them to video and outputs several streams. Mixers cite mixing for a 15-year-old's Bluetooth speaker — [Mix, American Mobile refines festival streaming setup](https://www.mixonline.com/recording/facilities/american-mobile-refines-festival-streaming-setup); [ProSoundWeb, Focusrite at Coachella](https://www.prosoundweb.com/focusrite-at-the-heart-of-the-broadcast-workflow-at-coachella-stagecoach/); [The Broadcast Bridge](https://www.thebroadcastbridge.com/content/entry/18557/broadcast-audio-for-coachella-with-american-mobile-studio/?cat_id=132)
- Coachella crowd handling: one fan Reddit thread claims the crowd was filtered out of a Green Day stream feed. This is anecdotal and unverified — [Reddit r/greenday](https://reddit.sudovanilla.org/r/greenday/comments/1jxzil3/coachella_set)
- Later... with Jools Holland: Sound supervisor Mike Felton has run the sound since the show began. Bands are set up around the perimeter of a single studio (originally BBC TV Centre Studio 1) and recorded live. Freelance mixer Tudor Davies multitracks to JoeCo BLACKBOX BBR64-MADI recorders — [Sound On Sound, Making Later... with Jools Holland](https://www.soundonsound.com/techniques/making-later-jools-holland); [Fast and Wide, Tudor Davies](https://www.fast-and-wide.com/faw-news/fast-news/9875-tudor-davies); [Erin McKeown Substack](https://erinmckeown.substack.com/p/fame-adjacent)
- Tiny Desk: Josh Rogosin (NPR concert audio technical director, lead since 2015, more than 800 shows) uses a hanging stereo rig, "Fritz", with two mics mimicking human ears that captures performers and the studio audience. The goal is a natural sound with minimal production — [Berklee, Behind the Mic of NPR's Tiny Desk](https://www.berklee.edu/news/berklee-now/Behind-the-Mic-of-NPRs-Tiny-Desk-Concert-Series?ss=213221); [Public Radio East, Josh Rogosin](https://www.publicradioeast.org/people/josh-rogosin); [NAMM session](https://namm.org/thenammshow/2024/session/audio-nprs-tiny-desk-concert-series)
- Ducking MC talk with a sidechain compressor on the music, keyed by the talk mic. Suggested settings: threshold about -20 dBFS, ratio 4:1–8:1, attack 10–30 ms, release 200–500 ms (too fast pumps) — [Voxbooster guide](https://voxbooster.com/blog/mix-voice-with-background-music); [zZounds blog, ducking in live broadcasts](https://blog.zzounds.com/2022/06/21/ducking-vocals-with-sidechain-compression-during-live-broadcasts/)
- Pitfall: on an Allen & Heath SQ5 livestream, a ducker for audience ambience mics worked on the main mix but not on the aux mixes feeding the stream. Verify the duck on every output path to the encoder — [Allen & Heath community](https://community.allen-heath.com/?p=105396)
- Apple's Ducker (Logic/MainStage) is not real-time, so do not use it for live MC ducking — [Apple Logic Pro effects help](https://help.apple.com/logicpro/mac/9.1.6/en/logicpro/effects/chapter_4_section_5.html)

### Inferences
- Architecture for a TV-quality YouTube show: take a split (analogue, Dante or MADI) from stage. A separate broadcast music mixer builds a band mix with its own bus processing, independent of FOH, which is shaped by the room and PA. A program mixer (or a second layer) adds the host or MC mic and stereo audience mics, then feeds the master chain and the encoder.
- Audience mics: keep them low during songs to add "live" air, and push them up between songs and on applause so the transitions don't feel dead. Audience mics are typically shotguns or a spaced pair aimed at the crowd, high-passed around 150–250 Hz. When the MC talks, duck the audience mics a few dB rather than muting them. All of this is practitioner convention (unsourced).
- Delay-align the audience mics to the close mics, or accept their natural delay as "room". Large time offsets can smear transients (unsourced).

### Gaps
- Full text of the Mix SNL50, SOS Jools Holland and Broadcast Bridge Coachella articles could not be fetched (DNS failures). Specific processing chains, compressor settings and audience-mic counts from those engineers are not captured.
- No sourced detail on the Glastonbury (BBC) broadcast mix workflow.

## 3. Bus processing: drum bus / parallel (NY) compression, vocal bus, music bus, SSL-style mix-bus glue, mid/side EQ

### Takeaway
Mix-bus glue is typically an SSL-style compressor at 2:1, 30 ms attack, auto release, with 1–3 dB of gain reduction (up to about 4 dB). Parallel (NY) drum compression uses a heavily compressed send (8:1–20:1, about 1 ms attack, 50–150 ms release, 10–20 dB of gain reduction) blended about 15–40% under the dry drums.

### Cited Findings
- SSL bus compressor on the mix bus: common start is 2:1 ratio with 30 ms attack. Slow attacks of about 10–30 ms preserve punch. Auto release adapts to the programme — [Waves, How to use an SSL Bus Compressor](https://www.waves.com/how-to-use-ssl-bus-compressor-classic-mix-glue); [Violet Recording, glue compressor plugins](https://violetrecording.com/best-glue-compressor-plugins/)
- Gain-reduction guidance varies: 1–2 dB on the biggest sections, or 1–3 dB, with some practitioners up to 3–4 dB. Attack too fast flattens punch; release too fast pumps — [Violet Recording](https://violetrecording.com/best-bus-compressor-plugins/); [Gearspace](https://gearspace.com/threads/waves-ssl-g-comp-on-rap.80763/post-833587); [Fab Dupont on SSL bus comp, Puremix](https://www.puremix.com/blog/fab-dupont-ssl-bus-compressor)
- Parallel drum compression: send the drum group to a compressor at 8:1 with low threshold and fast attack and release, then blend under the dry drums — [MusicRadar, NY compression on drums](https://www.musicradar.com/tuition/tech/how-to-use-new-york-compression-on-drums-605461)
- Attack about 1 ms or less, because the dry path keeps the transients. Release about 100 ms (range 50–150 ms). Ratio 8:1–20:1 or maximum. 10–20 dB of gain reduction. Blend 15–40% wet, or 70–80% dry / 20–30% compressed for "balanced punch". Level-match when comparing — [Music Guy Mixing, parallel compression on drums](https://www.musicguymixing.com/parallel-compression-on-drums/); [Dubspot](https://blog.dubspot.com/ultimate-guide-to-parallel-drum-compression-in-edm?hsLang=en); [Practical Audio Lab](https://practicalaudiolab.substack.com/p/lab-report-6-parallel-compression)

### Inferences (practitioner convention, unsourced)
- Drum bus insert: SSL or API-style compressor, ratio 4:1, attack 10–30 ms, auto or fast release, 2–4 dB of gain reduction. Optional sidechain HPF of about 60–100 Hz so the kick doesn't drive the compressor. Add an NY parallel return on top.
- Vocal bus: gentle optical or VCA compression, 2:1–3:1, 1–3 dB of gain reduction to glue lead and BVs. De-esser around 5–8 kHz. In a live broadcast the vocal bus usually also carries a fast peak limiter, because live singers vary more than studio takes.
- Music or instrument bus (keys, guitars, horns): 1.5:1–2:1, 1–2 dB of gain reduction. Optionally a dynamic EQ dip at 1–4 kHz keyed from the lead vocal to "make room" (spectral ducking).
- Mid/side EQ on the music or master bus: HPF the side channel at about 100–150 Hz (mono low end, which protects phones and mono playback and helps the codec). Optionally a small high-shelf lift on the side above 8–10 kHz for air. A slight mid dip at 2–4 kHz can push guitars and keys out wide while the vocal stays centred. Changes should be small, about ±1–2 dB.
- Live broadcast caveat: everything must be real-time. Avoid linear-phase or high-latency plugins, because the audio must stay in lip-sync with video, or the latency must be compensated in the video path.

### Gaps
- No sourced vocal-bus or music-bus specific settings, and no sourced mid/side EQ guidance (fetches to FabFilter and iZotope learning pages were not attempted, owing to the tool budget and DNS issues).

## 4. Stereo width, wideners, Haas tricks and mono compatibility

### Takeaway
Haas widening (one side delayed about 5–35 ms) creates comb filtering when summed to mono, and parts can thin out or vanish on phones, TVs and mono speakers. For a YouTube stream heard largely on phones, keep the core elements (kick, bass, snare, lead vocal) mono-centred, use real stereo sources or modulation instead of Haas on key parts, and check mono constantly.

### Cited Findings
- Haas technique: duplicate, pan and delay one side. Sweet spots are cited from about 5–35 ms to 5–40 ms, with up to about 25 ms giving perceived width. Under 5 ms produces comb filtering and phase artefacts rather than width — [iZotope, What is the Haas effect](https://www.izotope.com/en/learn/what-is-the-haas-effect); [eMastered](https://emastered.com/blog/haas-effect)
- When summed to mono, Haas parts can disappear or change in tone and level through phase cancellation. Many radios, TVs and smartphones play mono. Don't use Haas on critical elements. DAB radios are often mono, and FM car radios fall back to mono on weak signals — [Sound On Sound, Q: Can Haas delays be mono compatible?](https://www.soundonsound.com/sound-advice/q-can-haas-delays-be-mono-compatible)
- Mitigations: delays beyond the Haas window (heard as a discrete echo), tuning delay time, level and EQ, or chorus-style modulation, which reduces comb filtering. Always check in mono — [iZotope](https://www.izotope.com/en/learn/what-is-the-haas-effect.html); [Computer Music via PressReader](https://www.pressreader.com/australia/computer-music/20221130/282449943028787)

### Inferences
- Phone-speaker reality: most phone speakers are mono or near-mono and roll off below about 150–200 Hz. Bass must have harmonics (about 200–800 Hz) to be heard, and anything wide or out of phase gets lost (unsourced convention).
- Keep the correlation meter mostly positive (above about 0 to +0.3 on average). Avoid "stereo enhancer" plugins on the master (unsourced).

### Gaps
- No authoritative statistic found on the share of YouTube live viewers listening on phone speakers or in mono.

## 5. Reverbs and delays (plate, hall, room, pre-delay, decay, filtering, slapback, tempo sync), neo-soul/funk choices, sends vs inserts

### Takeaway
A vocal plate has about 20–40 ms pre-delay and 0.8–1.8 s decay (1–1.5 s for up-tempo funk, 2–2.5 s for ballads). Filter the return with a HPF around 200–400 Hz and an LPF around 8–12 kHz. Run reverbs and delays on aux sends (100% wet) so several sources share one space, and keep inserts for EQ and dynamics.

### Cited Findings
- Vocal plate pre-delay of 20–40 ms keeps the first word clear (20–60 ms range). Pre-delay can be tempo-synced — [Violet Recording, How to add reverb to vocals](https://violetrecording.com/how-to-add-reverb-to-vocals/); [Rysup Audio, reverb settings for vocals](https://rysupaudio.com/blogs/news/reverb-settings-for-vocals)
- Plate decay of about 0.8–1.8 s. Shorter (1–1.5 s) for fast songs, longer (2–2.5 s and up) for ballads — [Violet Recording](https://violetrecording.com/how-to-add-reverb-to-vocals/); [Rysup Audio](https://rysupaudio.com/blogs/news/reverb-settings-for-vocals)
- Return filtering: HPF at 200–400 Hz (or 200–300 Hz) to avoid mud. LPF or shelf above 8–12 kHz — [Violet Recording](https://violetrecording.com/how-to-add-reverb-to-vocals/); [Rysup Audio](https://rysupaudio.com/blogs/news/reverb-settings-for-vocals)
- Manufacturer preset reference: QSC Q-SYS "Vocal Plate" defaults to a 60.5 Hz low-cut, 12.1 kHz high-cut and 20 ms pre-delay — [QSC Q-SYS reverb help](https://q-syshelp.qsc.com/Content/Schematic_Library/effect_reverb.htm)

### Inferences (practitioner convention, unsourced; flag for verification)
- Neo-soul and funk: a lead-vocal plate of about 1.2–1.8 s with 20–40 ms pre-delay, plus a tempo-synced 1/4 or dotted-1/8 delay (HPF about 300 Hz, LPF about 5–8 kHz, 10–25% feedback) thrown on phrase ends. Slapback is about 60–120 ms, single repeat, for a retro or soul vibe on vocals or guitar. Drums get a short room or ambience (0.4–0.9 s, 0–10 ms pre-delay) on snare and toms, keeping the kick mostly dry. Keys (Rhodes) get a shared plate or medium hall at a low level. BVs get more reverb than the lead, to sit behind it.
- Tempo-sync formula: quarter-note delay in ms = 60000 / BPM. For example, at 96 BPM a quarter is 625 ms and a dotted eighth is 469 ms.
- Sends vs inserts: time-based effects go on aux sends at 100% wet (one plate, one room, one delay, perhaps a hall for big moments), with EQ after the reverb on the return. Dynamics and EQ go on inserts. In a live broadcast, the shared returns let you ride the "wet" amount per song.
- Watch reverb in mono: wide or decorrelated reverb tails partially cancel in mono, so judge the reverb level in mono as well as stereo.

### Gaps
- No sourced slapback ms values, room-reverb drum settings, or genre-specific (neo-soul/funk) reverb references from named engineers.

## 6. Broadcast master chain: order and settings (EQ, multiband, limiter, true peak)

### Takeaway
A typical order is corrective/tonal EQ, then gentle bus compression (glue), then multiband compression, then a true-peak limiter with oversampling, then a loudness meter. Use gentle multiband ratios (1.5:1–2:1, 1–3 dB per band) with crossovers around 120 Hz, 800 Hz–2 kHz and about 5 kHz. Set the limiter ceiling to -1 dBTP (or lower for AAC) with 4x oversampling.

### Cited Findings
- Multiband (mastering) ratios of 1.5:1–2:1, nothing at 4:1 or above on the bus. Gain reduction of about 1–3 dB per band. A band that compresses 6 dB continuously indicates an EQ problem — [Violet Recording, multiband in mastering](https://violetrecording.com/how-to-use-multiband-compression-in-mastering/)
- Example crossovers: 120 Hz / 800 Hz / 5 kHz, or 120–2000 Hz as a mid band, or 200 Hz / 2 kHz. A glue preset uses 1.5:1 on 120–1200 Hz and 1.6:1 on the lows — [Music Guy Mixing, multiband mastering settings](https://www.musicguymixing.com/multiband-compression-mastering/); [iZotope, multiband basics](https://www.izotope.com/en/learn/multiband-compression-basics-izotope-mastering-tips.html)
- True-peak limiter: 4x oversampling with a minimum 0.1 ms lookahead keeps true peaks within about 0.1 dB. Oversampling matters more with short lookahead or heavy limiting. Ceiling: -1.0 dBTP for R128 and YouTube, -2.0 dBTP for A/85 — [FabFilter Pro-L 2 help, oversampling](https://www.fabfilter.com/help/pro-l/using/oversampling); [FabFilter output options](https://www.fabfilter.com/help/pro-l/using/outputoptions)

### Inferences (practitioner convention, unsourced)
- Live-broadcast master chain:
  1. HPF at about 25–30 Hz plus broad tonal EQ.
  2. Optional M/S EQ (side HPF at about 100–150 Hz).
  3. SSL-style glue (2:1, 30 ms, auto, 1–3 dB).
  4. Multiband (3–4 bands, 1.5:1–2:1, slower attacks of 10–50 ms on lows, faster on highs, 1–3 dB) to stop a hot band such as a crowd roar or cymbals from dominating.
  5. True-peak limiter: lookahead 1–5 ms, release 50–200 ms or auto, 2–4 dB of gain reduction max on peaks, ceiling -1 to -2 dBTP.
  6. Loudness meter showing momentary, short-term and integrated loudness plus LRA and true peak.
- Broadcast-style "safety" processing: many broadcast trucks also put a final broadcast processor or leveller (AGC-style, slow) before the encoder to catch MC-to-band level jumps. Keep it gentle so music dynamics survive.
- The limiter should rarely work hard: the integrated loudness should come mainly from the bus and fader balance, not the limiter, to avoid pumping on a live mix.

### Gaps
- No sourced broadcast-specific (as opposed to mastering) multiband or limiter release values. No sourced description of how named TV music-show engineers order their master chain.

## 7. Stereo panning conventions for a band

### Takeaway
There is no industry standard for drum-kit orientation, but audience perspective is more common and is argued to suit content that accompanies video, matching what viewers see on screen.

### Cited Findings
- Most mixers use audience perspective, with no hard rules. Drummer perspective pans the kit as if seated at it — [iZotope, Drum Panning 101](https://www.izotope.com/community/blog/drum-panning)
- Mike Senior (Sound On Sound): there is no "industry standard". For mixes accompanying visuals, the argument for matching on-screen drum positioning (usually audience perspective) is stronger — [Sound On Sound](https://www.soundonsound.com/node/4920130)
- A forum poll split about 56% drummer / 44% audience perspective (n=32) — [Recording.org](https://recording.org/tags/drum/drum-panning)

### Inferences (practitioner convention, unsourced)
- For a video stream, use audience perspective and match the stage plot: if the keys player is stage-right (camera-left), pan the keys left.
- Kick, snare, bass and lead vocal go centre. Overheads go about L/R 70–100%. Toms follow the overheads. Hi-hat goes slightly toward its overhead side.
- Guitar and keys go opposite each other at about 30–70%. Stereo keys should be narrowed so the Rhodes or piano doesn't swamp the image. BVs are spread L/R (about 30–60%) or follow their stage positions. Horns follow stage positions. Audience mics go hard L/R.
- Keep the panning mono-safe: anything hard-panned still lands in a mono sum, but level balance changes by roughly 3–6 dB depending on the console's pan law.

### Gaps
- No sourced panning documentation from specific TV music-show engineers.
