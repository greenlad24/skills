# Live Broadcast Mix Processing Chain: Vocals, Keys, Guitar (modeler DI), Ambience/Audience, MC Speech, Neo-Soul/Funk Aesthetics

Context: automated server-side mixer, Sunrise Jam (Neo-Soul/Funk), 16-ch Midas M18 / X-Air platform, streamed to YouTube 1080p60.
Research note: several primary trade sites (soundonsound.com, prosoundweb.com, mixonline.com, livesoundint.com, musicguymixing.com) returned DNS errors on fetch from this environment, so their figures below come from search-result extracts, not full-page reads. Treat numbers as starting points. Tags: [LIVE] = from a live-sound/broadcast source, [STUDIO] = studio/post source, [FORUM] = practitioner anecdote.

## Lead and backing vocals: HPF, EQ, de-esser, compression, gating/expansion, bleed

### Takeaway
Sources converge on this order: HPF (about 80-160 Hz live, higher on a loud stage) > subtractive EQ > compression with roughly 3-5 dB GR at 3:1-4:1 > de-esser or dynamic EQ at about 5-10 kHz. A second, slower leveling compressor is used in studio and podcast chains. On a loud stage, sources prefer gentle expansion to hard gating because of bleed. None of the sources give numeric gate or expander values for live vocals.

### Cited Findings
- HPF [LIVE]: live engineer Nick Malgieri high-passes vocal mics at no lower than 120 Hz, sometimes as high as 160 Hz, and uses a de-esser or dynamic EQ for sibilance. — [Live Sound Int'l, May 2013 p.25](https://digital.livesoundint.com/may-2013/page-25) (search extract)
- HPF [LIVE]: ProSoundWeb's live-event vocal guide recommends a roll-off at 70-100 Hz, which also cuts stage rumble and handling noise. — [ProSoundWeb, Vocal Mixing For Live Events](https://www.prosoundweb.com/vocal-mixing-for-live-events/2/)
- HPF and sibilance [mixed live/plugin chain]: one ProSoundWeb vocal plugin chain starts with a 160-200 Hz high-pass and puts a sibilance shelf between 6.3 and 10 kHz. — [ProSoundWeb, Making It Sing](https://www.prosoundweb.com/making-it-sing-developing-a-plugin-chain-to-optimize-vocals/). A ProSoundWeb church-sound article gives about 60 Hz as a general starting point. — [ProSoundWeb church EQ](https://www.prosoundweb.com/church-sound-eq-vocals-the-five-primary-areas-of-modification/). Across these sources the HPF range is about 60-200 Hz.
- De-esser [STUDIO]: a de-esser is a specialised compressor on the sibilant band. Keeping the band narrow avoids lisping artifacts, and you find the "ess" frequency by listening to the sidechain. Split-band mode is more precise and wideband mode is gentler. — [Sound On Sound, SuprEsser review via Plugin Boutique](https://www.pluginboutique.com/articles/333-Sonnox-Oxford-SuprEsser-Review-At-Sound-on-Sound); [SOS](https://www.soundonsound.com/node/4924112). Forum suggestions for the de-ess band are about 4-8 kHz or 3-8 kHz. — [recording.org](https://recording.org/comment/vocal-eq-sound-check)
- Main compressor [LIVE]: ratio about 3:1, soft knee about 12 dB, attack about 3 ms so consonants punch through, release about 100 ms. Avoid 8:1 because it raises noise and bleed along with the vocal. — [Music Guy Mixing, live vocal compression](https://www.musicguymixing.com/vocal-compression-settings-live/) (search extract)
- Compressor [LIVE]: 4:1-6:1 for a very strong, aggressive voice and 2:1-3:1 for others. Lower the threshold until you see about 3-5 dB GR on loud passages. Attack 20-60 ms, release 300 ms-1 s. — [ProSoundWeb, Vocal Mixing For Live Events](https://www.prosoundweb.com/vocal-mixing-for-live-events/2/). These attack and release figures conflict with Music Guy Mixing's 3 ms/100 ms. A slower attack keeps articulation and a faster attack controls peaks harder.
- Two-stage compression [STUDIO]: stage 1 uses a fast attack, long release, and a threshold that keeps the vocal lightly compressed at all times, for leveling. Stage 2 adds movement and character with an attack around 30 ms and a faster release. The order can be swapped. — [McDSP, Multi-Stage Vocal Compression](https://mcdsp.com/2021/12/08/009-multi-stage-vocal-compression/)
- Two-stage compression [FORUM, live rehearsal]: first stage attack 10-20 ms, release about 100 ms, 4:1, set to catch peaks. For belters, threshold -4/-8 at 4:1 with +6 dB output. — [Gearspace](https://gearspace.com/threads/live-vocal-compressor-settings.108615/)
- Studio pop lead reference ranges: 3:1-4:1, attack 15-25 ms, release 50-80 ms. The source says these are not rules. — [Rysup Audio 2026](https://rysupaudio.com/blogs/news/how-to-compress-vocals)
- Gate vs expander: a gate mutes abruptly, while an expander lowers level by a ratio (for example 2:1 or 4:1) and keeps some low-level spill. Expanders suit subtler cleanup. — [Sweetwater](https://www.sweetwater.com/c787--Expanders_Gates); [LEWITT](https://www.lewitt-audio.com/blog/what-is-a-noise-gate-expander). LEWITT suggests a gate for live vocals to cut feedback and bleed between phrases. One forum practitioner expands first and then gates when bleed is severe. — [Gearspace](https://gearspace.com/threads/school-me-on-using-expanders.976853/). Waves Primary Source Expander is a product marketed specifically for vocal-mic stage bleed (vendor claim). — [Woodbrass listing](https://www.woodbrass.com/en-nl/plug-ins-waves-primary-source-expander-p399552.html)
- M18/X-Air platform: each input channel has a low-cut, a 4-band parametric EQ, and a gate and compressor taken from the X32 suite. Buses and main LR have inserts, dynamics, and a 6-band PEQ or 31-band GEQ. — [Gear4music X18 description](https://gear4music.ie/PA-DJ-and-Lighting/Behringer-X18-X-AIR-Digital-iPad-Tablet-Mixer/XOX). I did not find the exact order of channel processing blocks in any source.

### Inferences
- Suggested M18 lead-vocal starting point, synthesized from the [LIVE] sources above. This is not a single source's recipe:
  - Low-cut 100-120 Hz. Raise it to 150-160 Hz if the stage is loud or the singer handles the mic a lot.
  - Expander rather than gate: range about -6 to -10 dB, attack about 1-2 ms, hold about 50-150 ms, release about 200-400 ms. These expander values are my own practitioner inference; no source gave numbers.
  - EQ: cut mud around 200-400 Hz, cut boxiness around 500-800 Hz, apply a narrow harshness cut at about 2.5-4 kHz only if needed, add about +2 dB presence around 3-5 kHz, and use a high shelf of about +1-3 dB at 10-12 kHz for air.
  - Compressor: 3:1-4:1, soft knee, attack 3-10 ms, release 100-200 ms (or auto), aiming for about 3-5 dB GR on loud lines.
- The X-Air channel has only one compressor. If the platform offers no inserted FX, you can get a second stage two ways: insert a de-esser or second compressor from the FX rack, or bus-compress the vocal group (backing vocals plus lead) gently at 2:1 with about 1-2 dB GR. This depends on the platform and should be verified in the X-Air manual.
- Backing vocals: use a higher HPF than the lead (+20-40 Hz), cut more presence or air so they sit behind the lead, and compress harder (4:1, 4-6 dB GR) for a consistent blend. This is an inference from general practice. Elevado's re-balancing of background-vocal blends on Voodoo (below) shows how much the BV balance matters in this genre.
- For an automated mixer, gain-riding the vocal fader (an automixer- or sidechain-based ride) is probably safer than heavy compression on a loud stage, because compression raises bleed.

### Gaps
- No authoritative live source gave numeric gate or expander settings for vocal mics. Sources disagree on attack and release (3 ms/100 ms vs 20-60 ms/300 ms-1 s).
- Specific dynamic-EQ and saturation values for live vocals were not found.
- Exact M18 channel block order (gate > EQ > comp, and whether the insert sits pre or post) was not found. Consult the Midas M18/X-Air manual.

## Keys (Rhodes/Wurli/synth/organ): EQ, compression, width, Leslie

### Takeaway
Sourced guidance is mostly qualitative:
- HPF organ and keys around 100 Hz to clear bass and kick.
- Leslie: be careful in the 3-5 kHz region, a lift around 600 Hz-1 kHz adds "honk", and air above 10 kHz adds shimmer.
- Organ compression is optional because the swell pedal provides expression.
- Rhodes width traditionally comes from stereo auto-pan tremolo.

### Cited Findings
- Rhodes stereo: the original tremolo was mono amplitude modulation and became a stereo panning effect when Suitcase amps went stereo in 1969. — [FenderRhodes.com effects history](https://www.fenderrhodes.com/history/effects.html)
- Width [STUDIO]: tremolo/auto-pan is "by far the most common" way to process an electric piano differently left and right. Another option is an L/R EQ that cuts highs on the left and lows on the right, mimicking the pianist's perspective. — [Sound On Sound, Rhodes technique](https://www.soundonsound.com/techniques/rhodes-hog) (search extract)
- Organ HPF: a B3's wide range can clash with bass and kick, so a high-pass around 100 Hz is common. You can cut much of the low end unless the Leslie bottom rotor is mic'd and helping the song. — [Lynda Audio Mixing Bootcamp](https://origin-www.lynda.com/Pro-Tools-tutorials/Equalizing-organ/87006/93266-4.html); [Gearspace Mixing Hammonds](https://gearspace.com/threads/mixing-hammonds.475139/) [FORUM]
- Leslie EQ [FORUM]: a lift around 600 Hz-1 kHz adds "honk" that helps it fit. The 3-5 kHz region can sound piercing on a mic'd Leslie. A lift above 10 kHz adds shimmer without harshness. — [Gearspace Mixing Hammonds](https://gearspace.com/threads/mixing-hammonds.475139/post-5209041)
- Leslie compression [FORUM]: opinions split. Some compress heavily with fast attack and release in dense mixes. Others say the swell pedal provides the expression and compression is rarely needed. Volume automation is recommended as the more reliable control. — [Music Player Network forum](https://forums.musicplayer.com/topic/112962-tips-on-processing-a-real-leslie-live); [Gearspace](https://gearspace.com/threads/mixing-hammonds.475139/)
- Leslie mic'ing: horn mic for highs and drum mic for lows. Check positions in mono, because X-Y did not translate to mono for one poster, who used M/S instead. — [Recording.org](https://recording.org/comment/micing-b3-live-recording); [Music Player forum](https://forums.musicplayer.com/topic/112962-tips-on-processing-a-real-leslie-live)

### Inferences
- In this band, keys are most likely DI or stereo line from a stage keyboard or clone. A clone's Leslie sim produces its stereo spread internally, so keep the keys stereo-linked on the M18 (two channels linked, panned about L/R 60-100%). Check mono compatibility, since YouTube is often heard on mono phone speakers.
- Starting chain:
  - HPF 60-80 Hz on Rhodes/Wurli (higher, about 100 Hz, if the left hand duplicates the bass), 100 Hz on organ.
  - Gentle dip of 2-3 dB around 250-400 Hz where Rhodes and guitar mud overlap.
  - Optional +1-2 dB bark/tine at 1-2 kHz.
  - Compression 2:1-3:1, medium attack 10-30 ms, release 100-300 ms, 2-3 dB GR. Rhodes velocity dynamics are part of the neo-soul feel, so compress lightly.
  - Synth bass or pads need separate treatment, and the automated mixer should duck pads slightly under the lead vocal.
- No gate on keys.

### Gaps
- I found no authoritative numeric compression or EQ presets for Rhodes or Wurli in a live context.

## Guitar via Mooer modeler + cab sim to line input

### Takeaway
For a clean funk "chicken-scratch" DI:
- HPF about 100-150 Hz, which is more aggressive than usual for funk.
- LPF or shelf around 8-14 kHz to remove sim fizz.
- Gentle cut of 2-4 dB at 300-500 Hz for boxiness, and a wide cut at 2-4 kHz if harsh.
- Optional +1-2 dB high shelf around 4 kHz for snap.
- Compression should be light.

### Cited Findings
- Funk HPF: start around 100 Hz and sweep up to about 150 Hz for funk. — [Music Guy Mixing, Funk Guitar EQ](https://www.musicguymixing.com/funk-guitar-eq/) (search extract). General clean or low-gain rhythm guidance is 80-100 Hz. — [Violet Recording](https://violetrecording.com/how-to-eq-electric-guitar/)
- Funk LPF: aim for the 10-14 kHz region to protect the highest transients. — [Music Guy Mixing](https://www.musicguymixing.com/funk-guitar-eq/)
- Amp-sim fizz: use a low-pass or shelf to pull back above 8-10 kHz. Nail The Mix prefers a gentle high-shelf cut to a broad low-pass in the 5-10 kHz fizz range. — [Violet Recording](https://violetrecording.com/how-to-mix-electric-guitar/); [Nail The Mix Guitar EQ FAQs](https://www.nailthemix.com/guitar-eq-faqs)
- Harshness usually lives at 2-4 kHz, so use a gentle wide cut there. For boxiness, cut 2-4 dB with a medium-wide Q at 300-500 Hz. — [Nail The Mix FAQs](https://www.nailthemix.com/guitar-mixing-faqs)
- Funk brightness: high shelf around 4 kHz, +1-2 dB. — [Music Guy Mixing](https://www.musicguymixing.com/funk-guitar-eq/)
- Compression: slight bus compression, with optional multiband control around 150-250 Hz. This is general, not funk-specific. — [Kuassa](https://kuassa.com/?p=6263)
- Reference practice: Jack Stratton describes the Fearless Flyers Blue Note setup as "a nice, dead room, we got great D.I.s coming off them, good drum mics." — [Live for Live Music](https://liveforlivemusic.com/news/the-fearless-flyers-blue-note-residency-record-new-studio-album-videos/). Vulfpeck-style funk guitar is often DI-based, so a clean modeler DI fits this genre's live-video aesthetic.

### Inferences
- Suggested M18 chain for the Mooer cab-sim line:
  - Low-cut 100-120 Hz, raised to 150 Hz for chicken-scratch parts.
  - Cut 2-3 dB at about 300-400 Hz, Q about 1, to make room for Rhodes.
  - Optional cut of about 2 dB at 2.5-3.5 kHz if harsh. That band competes with vocal presence, so consider a dynamic cut keyed from the vocal, or a static cut of about 1-2 dB there.
  - Shelf of +1-2 dB at about 4-5 kHz for pick snap.
  - High-cut or shelf at 8-10 kHz if the sim fizzes, otherwise 10-12 kHz.
  - Compressor 3:1-4:1, attack about 10-20 ms so the pick transient passes, release 80-150 ms, 2-4 dB GR. Funk scratch is very transient and over-compressing kills the "chick".
  - Turn the cab IR on in the Mooer. A modeler with the cab off sent to line will be extremely fizzy.
  - Guitar and keys should sit on opposite sides of the stereo field, for example guitar about 30-40% L and keys widened or centered-right, so the parts don't mask each other.
- No gate is needed on a line-level DI unless the modeler is noisy at high gain. If it is, use the modeler's own noise gate.

### Gaps
- No source specific to Mooer GE-series cab sims or IRs was found.

## Ambience/audience mics: placement, HPF, compression, blend, gating/ducking, delay alignment

### Takeaway
Build a dedicated broadcast mix rather than sending the house mix.
- Place crowd mics high and aimed away from the PA.
- HPF and compress gently against applause spikes.
- Blend subtly. Too much hollows the mix out.
- Ride the level up between songs and for applause, and down during songs.
- Time-align: about 0.88 ms per foot (about 2.9 ms per metre) of PA-to-mic distance. Either delay the console mix to match the mics or treat the mics as late ambience.

### Cited Findings
- Build a dedicated broadcast mix and do not send the main house mix to the stream. — [QSC training, How to set up a mix for broadcasting](https://devtraining2.qsc.com/mod/book/view.php?id=1739)
- Placement: aim away from the main loudspeakers and mount high. If the mic picks up too much PA, the stream sounds echoey or washed out. With ceiling-hung condenser pairs, hang height sets the crowd-to-room balance. Larger setups use front condenser pairs, an elevated shotgun pair for the center audience, and a rear pair for ambience. — [ProSoundWeb, Making a Connection](https://www.prosoundweb.com/making-a-connection-deploying-mics-to-capture-the-sound-of-the-room-and-or-audience/); [BZBGear knowledge base](https://bzbgear.com/knowledge-base/how-to-set-up-and-use-a-crowd-or-ambient-microphone-for-broadcast-streaming/); [Sweetwater, crowd mics](https://www.sweetwater.com/insync/understanding-crowd-mics-for-church/)
- Delay: distance from loudspeakers to mics in feet × 0.88 = ms. If you rely heavily on the ambience mics, delay the console output to match them. — [ProSoundWeb / Worship Facilities](https://digital.worshipfacilities.com/may-june-2017/page-48) (search extract)
- Blend: blend subtly once the main mix is stable, because "a little goes a long way". Too much hollows the mix out and loses clarity. Ride the level up for singing and clapping and down during speech. — [Live Design, Mixing Methods for Streaming Audio](https://www.livedesignonline.com/houses-worship/mixing-methods-for-streaming-audio-at-church); [Sweetwater](https://www.sweetwater.com/insync/understanding-crowd-mics-for-church/)
- Processing: gentle compression to stop applause spikes, an HPF to roll off lows, and a mono check of stereo pairs for phase. — [BZBGear](https://bzbgear.com/knowledge-base/how-to-set-up-and-use-a-crowd-or-ambient-microphone-for-broadcast-streaming/)
- Tiny Desk: NPR uses "Fritz," a hanging rig with two multi-directional mics that captures both the performers and the office audience. Josh Rogosin, Technical Director of NPR Music, has mixed 500+ Tiny Desk concerts. — [Berklee, Behind the Mic of NPR's Tiny Desk](https://www.berklee.edu/news/berklee-now/Behind-the-Mic-of-NPRs-Tiny-Desk-Concert-Series?ss=213221). The often-cited "dry" Tiny Desk sound comes from close mic placement in an open office. That description appears only in a non-authoritative persona page — [shapes.inc](https://www.shapes.inc/joshrogosin) — so treat it as weak.

### Inferences
- Concrete starting values for an automated mixer:
  - Ambience pair HPF at 150-250 Hz, because room low end is mostly PA and stage wash.
  - Optional LPF at 10-12 kHz.
  - Compression 3:1-4:1, fast attack 5-10 ms, release 200-400 ms, aiming for 4-8 dB GR on applause peaks. Or limit hard on peaks and leave the body uncompressed.
- Ducking logic:
  - During songs: ambience about 12-20 dB below the stage mix. It should just add width and room ("air of a real room"), not be heard as a source.
  - Song end or applause: ride up about 6-12 dB over about 0.5-1 s.
  - MC talk: keep ambience about 6-10 dB under the speech mic so the speech stays intelligible but the crowd still reacts audibly.
  - You can automate song-state detection from the stage-mic RMS, or key a sidechain from the main stage bus to duck the ambience.
- Delay: room mics are acoustically late relative to the close mics. At small-venue distances (10-30 ft) the offset is about 9-26 ms. Choose one of two approaches:
  - (a) Delay the whole stage bus by that amount so the room mics line up. This is preferred if the ambience is prominent.
  - (b) Keep the room mics low and late, so they act like a natural early-reflection or reverb tail.
  - The M18 has input delay per channel/bus. Verify in the manual.
- To make the stream feel live, keep the ambience pair panned wide stereo (hard L/R), even if the stage sources are near-center. Width plus audible applause between songs carries the live feel more than reverb does.

### Gaps
- No source gave specific dB blend ratios or compressor settings for audience mics. The values above are inference.
- No Audiotree- or KEXP-specific statements on room-mic usage were found. KEXP sources describe a minimalist SM57/SM58 template and the aim to "capture what a band delivers".

## MC/talk between songs: switching vocal processing for speech

### Takeaway
For speech, sources suggest an HPF around 70-100 Hz, a ratio of about 2:1-4:1 (4:1 is commonly cited), a threshold set for about 3-5 dB of steady GR, and a leveling/peak chain similar to podcast processing. In practice this means more steady leveling and less "musical" processing than singing: no reverb or delay, and more presence for intelligibility.

### Cited Findings
- Podcast/speech chains: HPF at about 80 Hz, low-mid cuts, and a presence boost, then fast-attack compression followed by a slower leveling compressor. — [Cleanvoice / podcast compression guides](https://cleanvoice.ai/blog/podcast-compression/)
- Speech ratios: 4:1 is called the most reasonable (Acast). 3:1-5:1 is a "sweet spot". 2:1-3:1 suits natural corporate delivery. — [Acast](https://www.acast.com/en/blog/a-guide-to-vocal-compression-for-podcasters); [Glow.fm](https://www.glow.fm/guides-tutorials/how-to-use-compression-for-better-podcast-sound); [PodcastVideos](https://www.podcastvideos.com/how-to-structure-audio-compression-settings-for-clear-corporate-podcast-vocals/)
- Thresholds of -18 to -22 dB, just below average delivery level, are suggested. One source lists -20 to -30 dB. Attack of 3-5 ms is typical on voices. — [PodcastVideos](https://www.podcastvideos.com/how-to-structure-audio-compression-settings-for-clear-corporate-podcast-vocals/); [Finchley](https://www.finchley.co.uk/finchley-learning/visual-podcast/audio-engineering-in-a-professional-podcast-post-production-tools-compressors). One podcast source had internally inconsistent figures and was excluded.

### Inferences
- Snapshot or scene switch on the M18 between "SONG" and "TALK" states. The X-Air supports snapshots, and you can also switch over OSC parameter by parameter.
- TALK state:
  - Lead vocal HPF raised by about 20-30 Hz to reduce proximity boom.
  - Vocal reverb and delay sends muted.
  - Fader +3-6 dB relative to the song level, because speech sits lower in level than singing.
  - Compression at 3:1-4:1 with a lower threshold for about 6 dB GR.
  - Band channels pulled down 10-20 dB, or kept at noodling level.
  - Ambience raised (see above).
- In an automated system, detect talk vs song with band-bus RMS plus vocal-channel spectral features. Use hysteresis of a few seconds to avoid flapping.

### Gaps
- No live-broadcast source specifically on vocal-snapshot switching for MC segments was found.

## Neo-Soul/Funk aesthetics and how live-session channels mix for YouTube

### Takeaway
The genre's reference live-session sound is minimal and "captured":
- KEXP: SM57/58 template, capture what the band delivers.
- Tiny Desk: close mics plus a two-mic overhead "Fritz" rig.
- Vulfpeck: dead room plus good DIs and drum mics.

The studio reference (D'Angelo's Voodoo, Russell Elevado) is analog and vintage-sounding, with carefully balanced background vocals. Delivery should target about -14 LUFS integrated and below -1 dBTP for YouTube.

### Cited Findings
- KEXP: Kevin Suggs, who heads audio engineering for Live on KEXP, starts from a template based on SM57/SM58 and baseline Pro Tools presets. His philosophy is to capture what the band delivers rather than recreate the studio record. KEXP logs about 300 sessions per year. Engineers previously mixed to two-track on an eight-bus Mackie digital board. — [Mix, Live on KEXP podcast](https://www.mixonline.com/recording/live-on-kexp-podcast-blurs-the-lines-between-live-and-studio-recording) (search extract); [Radio World](https://www.radioworld.com/?p=105356)
- Tiny Desk: listening matters more than gear ("Your ears are the best possible microphone"), and the hanging "Fritz" two-mic rig captures performers and audience. — [Berklee](https://www.berklee.edu/news/berklee-now/Behind-the-Mic-of-NPRs-Tiny-Desk-Concert-Series?ss=213221)
- Snarky Puppy: Eric Hartman engineered and mixed GroundUP, Family Dinner Vol. 1, and much of Vol. 2, recorded live in front of a studio audience. Nic Hard later mixed Culcha Vulcha, Live at Royal Albert Hall, and many live concerts. Puremix's "Start to Finish" series documents Nic Hard's Snarky Puppy live-to-Atmos workflow (paid). — [Fast and Wide](https://www.fast-and-wide.com/faw-news/fast-news/6088-snarky-puppy); [ProStudioMasters](https://www.prostudiomasters.com/album/page/52957); [Puremix](https://v2.puremix.com/video/start-to-finish-snarky-puppy.html)
- Vulfpeck: Jack Stratton produces and mixes. Early EPs were recorded more or less live with minimal post. The Fearless Flyers at the Blue Note were captured in a "nice, dead room" with "great D.I.s" and "good drum mics". — [Stanford Daily](https://stanforddaily.com/2016/11/21/vulfpeck-thebeautifulgame-album-review/); [Live for Live Music](https://liveforlivemusic.com/news/the-fearless-flyers-blue-note-residency-record-new-studio-album-videos/)
- D'Angelo, Voodoo: Russell Elevado's method was to recreate classic sounds with era-appropriate mics, consoles, and techniques. Vocals always went to tape. Background-vocal blends were re-balanced 3-4 times over the three-year mix. Most of the record is relatively dry, while "1000 Deaths" buries the vocals in reverb. — [NPR, 20 Years Later](https://wnyc.org/story/20-years-later-how-does-it-feel/); [Tape Op](https://new.tapeop.com/interviews/161/russell-elevado); [Vinyl Factory](https://thevinylfactory.com/features/the-making-and-re-making-of-dangelos-black-messiah/)
- YouTube loudness: YouTube normalizes down to about -14 LUFS (for example, -10 LUFS content is turned down 4 dB) and does not turn quiet content up. Rule of thumb: -14 LUFS integrated, true peak ≤ -1 dBTP. — [Wikipedia, Audio normalization](https://en.wikipedia.org/wiki/Audio_normalization); [Youlean](https://youlean.co/?p=30813). Whether the same normalization applies to live streams is not confirmed by YouTube documentation found here.

### Inferences
- Tonal targets for neo-soul/funk, synthesized from genre references and not from a single measured source:
  - Warm, round low end with kick and bass dominant, but controlled below about 40 Hz.
  - Relaxed upper mids, avoiding 2-5 kHz harshness, with the vocal carrying presence.
  - Smooth top end rather than bright and hyped.
  - Dry-ish, intimate vocal with short plate or room reverb rather than long halls.
  - Pocket-focused dynamics, with less bus compression than pop. Preserve ghost notes and Rhodes velocity.
- Live-session channels (KEXP/Tiny Desk/Audiotree) sound "live" because of minimal processing, close mics, a small amount of room or audience, and no heavy mastering limiting.
- For automation, favor:
  - gentle 2-bus glue (2:1, slow attack 30 ms, auto release, 1-2 dB GR)
  - a final limiter at about -1 dBTP
  - loudness riding toward about -14 LUFS short-term average.

### Gaps
- No direct Audiotree engineer interview or Hiatus Kaiyote / Erykah Badu live-mix interview was found within the search budget.
- No measured spectral-balance target curves for the genre were found.
- The Puremix Nic Hard content is paywalled and was not reviewed.
