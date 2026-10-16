# Drums & Bass Processing Chains for Live/Broadcast Mixing (Neo-Soul/Funk, Midas MR18 / X-Air)

> Research caveat: Search snippets were available, but the full-page fetch tool failed for every domain (soundonsound.com, prosoundweb.com, manualslib.com, sonnox.com, redbullmusicacademy.com, equipboard PDF): the proxy refused the connections or DNS failed. Every cited finding below comes from search-result excerpts, not full articles. Most numeric sources are mixing-education sites (musicguymixing, emastered, nailthemix), which are not primary engineer interviews. Treat all numbers as starting ranges. Items marked "[training knowledge, unverified]" are not cited and belong to Gaps or Inferences.

## 1. Kick drum (in/out): chain and starting settings

### Takeaway
Typical live order: HPF, then gate (fast attack, release timed to the drum's decay), then subtractive EQ (300–400 Hz box), then additive EQ (~60 Hz weight, 3–4 kHz beater), then compressor (4:1–5:1, 5–15 ms attack so the click passes, moderate/fast release). Kick in and kick out usually need a polarity check against each other.

### Cited Findings
- Gate is "usually a good first step" on the kick close mic to remove snare/tom spill. A compressor goes *after* the gate if the level is uneven, with attack ~5–10 ms to let the click through — [SOS via search excerpt](https://www.soundonsound.com/node/4922781); [Computer Music "Mixing live drums" step-by-step](https://www.pressreader.com/australia/computer-music/20200715/282089164061105)
- Example kick gate: threshold set (soloed) so only the kick opens it (−16 dB in that example), attack 0 ms, hold 0 ms, lookahead 6.8 ms, release 310 ms — [Computer Music via PressReader](https://www.pressreader.com/australia/computer-music/20200715/282089164061105)
- Gate attack trade-off: too fast clicks, too slow loses the transient. Set the threshold to pass the attack and cut as much decay as desired — [SOS "Gate Expectations"](https://www.soundonsound.com/techniques/gate-expectations); [Tape Op noise gates](https://tapeop.com/tutorials/33/noise-gates)
- Kick compressor: threshold 5–10 dB below peak, ratio ~5:1, hard knee, attack ~15 ms — [musicguymixing kick compression](https://www.musicguymixing.com/kick-compression/)
- Alternative kick comp: slowish attack to keep the initial hit, fast release, ~4:1. For a spiky kick, use fast attack/release at ~2:1 — [eMastered drum compression (NL)](https://emastered.com/nl/blog/drum-compression)
- Live worship/FOH guidance: kick fast attack, 3:1–4:1, slower release for punch, don't over-compress. A hard knee is preferred for kick and bass — [ProSoundWeb worship mix](https://www.prosoundweb.com/the-foundation-of-the-perfect-worship-mix/2/); [Church Sound / LSI May 2023](https://customdigital.livesoundint.com/may-2023/page-14)
- Reference table: kick attack ~5–15 ms, release ~50–250 ms — [musicguymixing snare compression (table)](https://www.musicguymixing.com/snare-compression/)
- Live kick EQ: fundamental ~60 Hz, bump +3–6 dB around 60 Hz. Boost 3–4 kHz for beater click. Low-mid cut variously at ~150 Hz (room for bass), 250–400 Hz, 300–400 Hz (boxiness), or 400–500 Hz (wooden knock), so sweep to find it — [musicguymixing live kick EQ](https://www.musicguymixing.com/live-kick-drum-eq/); [musicguymixing drum EQ chart](https://www.musicguymixing.com/drum-eq-chart/); [Produce Like A Pro drum EQ basics](https://producelikeapro.com/blog/drum-eq-basics/)
- Kick in/out: inside/outside kick pairs are a classic case needing a polarity flip. Check by toggling polarity and keeping the setting with more low end. Whether to flip is empirical, "it can be any way around" — [Gearspace phase issues with drums](https://gearspace.com/threads/phase-issues-with-drums.1338534/); [B&H polarity vs phase](https://www.bhphotovideo.com/explora/audio/tips-and-solutions/polarity-vs-phase-whats-the-difference); [MasteringBox phase alignment](https://next.masteringbox.com/learn/phase-alignment-polarity-time-correction)
- A polarity flip fixes only a 180° offset. Time shifting (samples/ms) corrects arbitrary misalignment — [MasteringBox](https://next.masteringbox.com/learn/phase-alignment-polarity-time-correction)

### Inferences
- Suggested automated starting point for kick in, synthesized from the sources above: HPF 30–40 Hz; gate threshold set relative to measured kick peak (open only on kick hits), range 20–40 dB, attack 0–1 ms, hold 10–50 ms, release 100–300 ms; EQ −3 to −6 dB at 300–400 Hz (Q ~2), +2 to +4 dB at 55–70 Hz (Q ~1), +2 to +4 dB at 3–5 kHz; comp 4:1, attack 5–15 ms, release 50–120 ms, 3–6 dB GR on hits.
- Kick out (resonant head): use it for low end (40–80 Hz). Cut its 2–5 kHz content, let kick in carry the click, and evaluate the polarity of the pair on the summed low end.
- Funk/neo-soul favours a short, tight, "dry" kick, which argues for shorter gate release (~100–200 ms) and less low-end bump than rock/pop.

### Gaps
- No primary FOH/broadcast engineer interview with exact kick numbers was retrievable, because full-text fetching was blocked.
- No source gave a ms value for kick in/out alignment. Distances are typically small (port to beater ~30–50 cm, so ~1–1.5 ms), but that figure is inference, not sourced.

## 2. Snare (top/bottom): chain and starting settings

### Takeaway
Order: HPF (~100–200 Hz, high enough that kick bleed doesn't trigger the gate), optional gate or expander (gentle for funk, because ghost notes must survive), EQ (body 150–250 Hz, cut box 400 Hz-ish, crack ~5 kHz), compressor 4:1–6:1, attack 3–20 ms, release ~80–250 ms, 3–6 dB GR. Bottom mic: polarity inverted relative to top, HPF higher, blended for snare-wire sizzle.

### Cited Findings
- Snare HPF around 200 Hz depending on snare size/tuning. Rack tom HPF ~100 Hz, floor tom ~60–80 Hz, overheads ~200–400 Hz — [ProSoundWeb "Frequency Bracketing for Drum Kits"](https://www.prosoundweb.com/tightening-it-up-zen-and-the-art-of-frequency-bracketing-for-drum-kits/2/) (via search excerpt)
- Snare body ~150–200 Hz (wide-Q boost if thin). Boxiness ~400 Hz (narrow sweep, then cut). Crack/crispness ~5 kHz. Ring can be tamed with a narrow cut. Buzz/rattle at 3–5 kHz can be handled with dynamic EQ that only acts on the offending hits — [eMastered snare EQ](https://emastered.com/blog/snare-eq); [mixingaband live drum EQ](https://mixingaband.com/how-to-eq-live-drums/)
- Snare compression: ratio ~6:1 [musicguymixing](https://www.musicguymixing.com/snare-compression/), or 4:1–6:1 (8:1 heavy) [Nail The Mix](https://www.nailthemix.com/how-to-use-compression-on-a-snare-drum). Threshold ~10 dB below average peak. 3–6 dB GR on the loudest hits. Attack 10–20 ms medium, or 3–15 ms (table). Release 50–250 ms, with hold 20 ms + release 80 ms named as a "healthy compromise" — [musicguymixing snare compression](https://www.musicguymixing.com/snare-compression/); [Nail The Mix](https://www.nailthemix.com/how-to-use-compression-on-a-snare-drum)
- Snare bottom: the bottom head's pressure response is opposite to the top's, so a non-inverted bottom mic sounds thin. Invert the bottom polarity, then confirm by ear on low end — [Gearspace drum waveform question](https://gearspace.com/threads/drum-waveform-question.332276/); [Gearspace inverting phase](https://gearspace.com/threads/inverting-phase.269661/); [ProSoundWeb polarity vs phase](https://www.prosoundweb.com/are-you-confusing-polarity-with-phase/)

### Inferences
- For funk/neo-soul, ghost notes are part of the groove. On snare, prefer an expander with shallow range (e.g., 6–12 dB) or no gate, rather than a hard gate, so ghost notes aren't chopped. Keep compression attack ≥10 ms and add parallel or makeup gain to lift ghosts. This is synthesized from the general gate guidance plus genre need. No genre-specific source was found.
- Snare bottom starting point: polarity inverted, HPF 200–400 Hz, boost 6–10 kHz for wires, mixed −6 to −12 dB below the top.

### Gaps
- No sourced numeric guidance specific to funk snare or ghost notes was found.
- No live-specific snare dynamic EQ settings beyond the "3–5 kHz buzz" suggestion.

## 3. Toms

### Takeaway
HPF (rack ~100 Hz, floor ~60–80 Hz). Gate (or channel muted between fills) is common live, because tom mics are mostly bleed. Some engineers key tom gates or pre-gates to reject snare spill.

### Cited Findings
- Rack tom HPF ~100 Hz, floor tom ~60–80 Hz — [ProSoundWeb frequency bracketing](https://www.prosoundweb.com/tightening-it-up-zen-and-the-art-of-frequency-bracketing-for-drum-kits/2/)
- Technique: a "pre-gate" keyed from the snare track removes snare spill from the tom track before the main tom gate — [SOS Logic gating toms](https://www.soundonsound.com/techniques/logic-pro-gating-toms)
- Gate critical controls are threshold and release, and defaults are usually fine otherwise. A longer release lets the drum ring naturally instead of chopping it — [SOS Gate Expectations](https://www.soundonsound.com/techniques/gate-expectations)

### Inferences
- Tom starting point: gate threshold high enough to reject snare, range 15–30 dB, attack 0–1 ms, hold 50–100 ms, release 200–500 ms (floor longer). EQ cut 300–500 Hz −3 to −6 dB, attack boost 3–5 kHz, LPF 8–10 kHz to reduce cymbal spill.
- With only 16 inputs, many small bands mic one rack plus one floor tom, or none, relying on the overheads. The tom count is an inference.

### Gaps
- No sourced numeric tom-gate times from a live engineer.

## 4. Overheads and hi-hat

### Takeaway
Overheads: HPF 200–400 Hz (some as low as ~100–150 Hz when the OHs supply kit image), no gate, light or no compression. Hi-hat: HPF 300–600 Hz. Time alignment rule: ~1 ms per foot, delaying the *close* mics to the overheads rather than advancing the overheads.

### Cited Findings
- Overhead HPF ~200 Hz at 24 dB/oct. Hats and overheads up to 300–600 Hz in a church/live context. Hi-hat HPF to ~400 Hz. Overhead body around 300–400 Hz — [musicguymixing EQ drums live](https://www.musicguymixing.com/eq-drums-live/); [Skool church drums EQ](https://www.skool.com/church-audio-engineers-2670/how-to-eq-drums-in-a-church-mix-the-real-world-guide); [Produce Like A Pro](https://producelikeapro.com/blog/drum-eq-basics/)
- Overheads HPF ~200–400 Hz — [ProSoundWeb frequency bracketing](https://www.prosoundweb.com/tightening-it-up-zen-and-the-art-of-frequency-bracketing-for-drum-kits/2/)
- Sound travels ~1 ft per ms, so an overhead 6 ft above the snare hears it ~6 ms late. The overhead is "late to the party", so delay the snare (close mic) to match. Check polarity too, because sometimes the phase is reversed — [SOS via search](https://www.soundonsound.com/node/4921497); [Gearspace time aligning drum mics](https://gearspace.com/threads/time-aligning-drum-mics.7887/); [Audio Masterclass](https://www.audiomasterclass.com/blog/q-there-is-a-delay-in-my-drum-overheads-how-can-i-fix-it)
- Caveat: aligning one close mic to the OHs changes its relationship to every other mic. Alignment works fully for only one drum — [Gearspace manually aligning overheads](https://gearspace.com/threads/manually-aligning-overhead-tracks.26461/); [ProSoundWeb forum](https://forums.prosoundweb.com/index.php/topic,151076.0.html)

### Inferences
- Typical live OHs sit 2–3 ft above the snare, so a snare/kick delay of ~2–3.5 ms to align with OHs. Many live engineers skip this. If the MR18/X-Air lacks per-channel input delay (see section 7), alignment can't be done natively, so an automated mixer should do it in software or skip it.
- Hi-hat: HPF 300–500 Hz, slight cut 1–2 kHz if clangy, LPF ~15–16 kHz, no gate. In funk the hat is a groove element, so keep it present but not harsh.

### Gaps
- No sourced overhead compression numbers for live use.

## 5. DI bass (pedals into a passive DI)

### Takeaway
HPF ~30–45 Hz (lower if the kick sits above it). Cut ~1 kHz-ish honk or low-mid mud as needed. Compress (hard knee, moderate-to-high ratio with make-up gain for consistency). Add harmonics (saturation or parallel drive, possibly with a low-passed send) so the bass reads on phones and small speakers. Manage the kick relationship with a kick-keyed sidechain or dynamic EQ in the ~60–120 Hz overlap, aiming for only ~2 dB of ducking.

### Cited Findings
- Clean DI bass often has too much ~1 kHz midrange, which hurts it in a full mix. Emphasizing the *harmonics* of low notes rather than the fundamentals keeps pitch clear on small speakers — [SOS (Dave Lockwood DI bass examples)](https://www.soundonsound.com/node/4929135)
- Most engineers use some compression on bass, mainly to tame loud slap or pull attacks. A good parametric or graphic EQ after the DI helps — [SOS](https://www.soundonsound.com/node/4924595)
- Compression usable range before pumping can be small, and the right setting depends on pickup output — [SOS Tech 21 Bass Compactor review](https://www.soundonsound.com/reviews/tech-21-bass-compactor-processor)
- Hard knee preferred on bass. Higher ratios (~6:1+) with make-up gain lift quiet notes. Bass players often dislike audible compression — [Church Sound / LSI May 2023](https://customdigital.livesoundint.com/may-2023/page-14); [ProSoundWeb worship mix](https://www.prosoundweb.com/the-foundation-of-the-perfect-worship-mix/2/)
- Kick/bass: if the kick sits at ~45–50 Hz, HPF the bass to keep out of its space. Conversely, if the bass is full down to 20 Hz, HPF the kick and give it punch at 50–80 Hz — [LSI April 2025](https://customdigital.livesoundint.com/april-2025/page-17)
- Kick/bass separation can start physically (kick mic toward the beater for more click) — [LSI Jan 2019](https://digital.livesoundint.com/january-2019/page-26)
- Some engineers carve a hole in the bass with EQ or kick-keyed sidechain compression. Some songs work best with kick and bass merged. Check the low end with the bass muted — [SOS bass guitars in the mix](https://www.soundonsound.com/techniques/bass-guitars-mix)
- Sidechain: compressor on bass keyed from kick, fast attack/release, "a couple of dB" of ducking. A multiband sidechain or dynamic EQ band around 60–120 Hz is more surgical. Kick/bass fundamentals are both ~70–120 Hz and overlap heavily below 150 Hz — [Mastrng substack](https://mastrng.substack.com/p/mixing-kick-and-bass); [musicguymixing sidechaining](https://www.musicguymixing.com/sidechaining/); [Sonarworks](https://www.sonarworks.com/blog/learn/rock-the-low-end); [Violet Recording](https://violetrecording.com/how-to-mix-kick-and-bass/)
- Saturation for small-speaker translation works through the missing-fundamental effect: nonlinear distortion creates harmonics small speakers can reproduce. A send with a low-pass filter into distortion is "a more flexible solution". Risk: it can make lows weaker on full-range systems, so check on multiple devices — [Computer Music "Bass on small speakers"](https://www.pressreader.com/australia/computer-music/20171004/282243780786770); [UPC virtual bass thesis](https://upcommons.upc.edu/entities/publication/53beaf2b-6dbb-4628-b2f4-e8549f05184f/full)
- Practitioner: boost ~700 Hz–1 kHz (and maybe 300–400 Hz) on electric bass for small speakers, but it can sound artificial on big speakers (anecdotal) — [R/E/P forum](https://repforums.prosoundweb.com/index.php/topic,25609.0.html)
- Transient-preserving virtual bass separates transients from tonal content so harmonic generation doesn't smear attacks — [OST thesis 2016](https://www.ost.ch/fileadmin/dateiliste/97_daten/abstracts/e_e.cansev_p.d__rst_f_2016.pdf)

### Inferences
- Two-stage compression, the common studio/broadcast practice (not directly sourced): stage 1 is a fast peak catcher (8:1+, attack 1–5 ms, release 50–100 ms, 2–4 dB GR on spikes/slaps). Stage 2 is leveling (3:1–4:1, attack 10–30 ms, release 100–300 ms or auto, 3–6 dB GR). On the MR18 the channel comp can do stage 1 and an inserted FX-slot compressor stage 2, or the reverse.
- Bass DI starting point: HPF 30–40 Hz (12–24 dB/oct); +1 to +3 dB 60–90 Hz (wide) if thin; −2 to −4 dB 200–300 Hz if muddy; −2 to −4 dB around 800 Hz–1 kHz if honky, or +2 dB 700–900 Hz for small-speaker definition, judged by mix context; +1 to +3 dB 1.5–2.5 kHz for finger/string definition; LPF 5–8 kHz to drop DI hiss and pedal noise.
- Pedals before the DI already shape the tone, so the server mixer should measure the spectrum rather than assume a flat DI.
- Neo-soul (Pino Palladino on *Voodoo*) tone is round, low-mid-heavy, and dark with little top. That suggests LPF ~3–5 kHz and minimal 2–5 kHz boosting. Funk/Vulfpeck (Joe Dart) is attack-forward, bright, and punchy, often with flatwounds-like midrange growl. This description draws on general knowledge and is not sourced (see Gaps).

### Gaps
- No primary-source numeric settings from a named broadcast engineer for bass were retrievable.
- Pino Palladino and Joe Dart signal chains: Joe Dart uses Rotosound RS66M Swing Bass strings and a Sterling/Carlo Robelli bass, with the pickup typically in passive mode ([Bassplayer](https://www.bassplayer.com/artists/joe-dart-spontaneous-soul-with-vulfpeck); [Equipboard](https://equipboard.com/joe-dart)). No mixing numbers were found.

## 6. Funk/neo-soul specifics (D'Angelo *Voodoo*, Vulfpeck)

### Takeaway
References favour dry, tight, close drums with an audible groove (ghost notes, hat dynamics) and minimal ambience. Compression is used as a "color" (Vulf Compressor: extreme attack and pumping on drums/bass). Little hard documentation of exact settings exists.

### Cited Findings
- Russell Elevado's aim on *Voodoo* was to recreate vintage sounds "using the microphones, consoles, and techniques of the era". He recorded and mixed with D'Angelo and the band over ~3 years — [NPR/WNYC "20 Years Later, How Does It Feel?"](https://wnyc.org/story/20-years-later-how-does-it-feel/)
- A Red Bull Music Academy session shows Elevado mixing "Till It's Done" on an SSL 9000J with channel EQ/compression on drums and bass. He most often uses *no mix-bus chain* — [RBMA interview](https://daily.redbullmusicacademy.com/2018/06/russell-elevado-interview) (search excerpt only)
- Vulf Compressor (Goodhertz, based on the Boss SP-303 compression algorithm) is suggested for drum breaks and electric bass "to add extreme attack". Drums can feed its sidechain to pump the master bus without raising drum level — [Goodhertz Vulf Comp manual](https://manuals.goodhertz.com/3.13/vulf-comp); [RouteNote](https://routenote.com/blog/create-your-own-tasty-funk-sounds-with-vulfpecks-own-compressor/)
- Jack Stratton calls compression "the salt of music mixing" — [Columbia Chronicle](https://columbiachronicle.com/arts-culture/924c59f8-d1de-11e5-bc7a-a3d4e0a94687/)
- Vulfpeck records quickly and live in the room ("record button within five or ten minutes") — [Guitar World Joe Dart interview](https://www.guitarworld.com/features/vulfpecks-joe-dart-we-intentionally-keep-things-on-edge-and-in-the-moment)

### Inferences
- For an automated broadcast mix in this genre: short gate releases on kick/toms, little reverb on drums (if any, a short dark room/plate on snare only), and preserved snare ghost notes and hat dynamics through gentler snare expansion and slower compressor attack. Optional parallel "smash" drum bus (10:1+, fast attack, 10+ dB GR, blended −10 to −15 dB under) for Vulf-style punch.

### Gaps
- No verifiable Elevado/Voodoo numbers (mic choices, compressor settings) were found. Full interviews were unreachable.
- No Vulfpeck engineer breakdown of drum mic count or mixing settings was found.

## 7. MR18 / X-Air native capabilities vs. extra processing; 16-input drum layout

### Takeaway
The product is the Midas **MR18** (there is no "M18"). Per channel it offers a HPF, gate/expander/ducker, compressor, and 4-band PEQ. Buses get 6-band PEQ or 31-band GEQ plus dynamics. There are 4 stereo FX engines (some can be inserted on channels). Dynamic EQ, multiband sidechain, saturation, and transient shaping are not channel-native and need an FX slot or external/server-side DSP.

### Cited Findings
- MR18: 16 Midas PRO mic preamps plus 2 line inputs, 6 aux buses plus main LR, 4-band parametric EQ on each input, "full dynamics with compression and gate", one HPF per input, 6-band PEQ or 31-band GEQ on outputs with dynamics and inserts, 4 true-stereo FX engines, 40-bit floating-point processing, 24-bit A/D at 44.1/48 kHz — [Long & McQuade](https://www.long-mcquade.com/GearHunter/1080537/Midas-MR18.htm); [7bd spec listing](https://7bd.com/radio/midas-mr18-18-input-digital-mixer-for-ipad-android-tablets.html); [Adorama](https://www.adorama.com/used-midas-mr18-18-input-digital-mixer-with-wi-fi-and-usb-recorder-for-ipad-android-tablets/p/us1891332). Sources conflict on per-channel delay: one low-quality source claims it, and the detailed spec listings don't.
- X-Air (XR18, same platform) gate modes: EXP2, EXP3, EXP4 (expansion of varying depth), GATE (aggressive), DUCKER (attenuates when signal exceeds threshold), with Range setting attenuation depth and a Hold control — [Behringer XR18 manual via ManualsLib](https://www.manualslib.com/manual/1069916/Behringer-Xr18.html?page=17)
- X-Air compressor controls include on/off, knee, threshold, gain, attack/hold/release, a Mix control (parallel blend), and an optional sidechain filter — [Christian Today XR18 review](https://christiantoday.com.au/news/behringer-xr18-review-part-2.html); [ManualOwl XR18](https://www.manualowl.com/m/Behringer/XR18/Manual/490796?page=18)
- Time-based FX should not be inserted (the insert button off) — [Scribd XR18/MR18 FX guide](https://es.scribd.com/document/823678347/Basic-Menu-Mixer) (low reliability)

### Inferences
- The compressor Mix knob allows parallel compression per channel natively, which is useful for snare/kick punch and bass, without using a bus.
- **Unverified training knowledge, needs confirming against the official manual:** X-Air shares X32-family dynamics. Gate range ~3–60 dB, attack 0–120 ms, hold ~0.02–2000 ms, release ~5–4000 ms, key filter. Comp ratios from 1.1:1 to 100:1, knee 0–5, Peak/RMS and Lin/Log envelope, attack 0–120 ms, release 5–4000 ms, comp/exp modes. Channel EQ band types LCut/LShv/PEQ/VEQ/HShv/HCut. Channel inserts consume one of the 4 FX slots. Slots 1–4 can host dual/stereo processors (e.g., dual GEQ, dual "combinator"/multiband, "Fair" or "Leisure" compressors, enhancer, "Guitar Amp", "Tube Stage"). Whether X-Air has per-input delay is unconfirmed. If not, drum time alignment must happen server-side.
- With 4 FX slots typically needed for vocal reverb, delay, and maybe drum room, there's little room for inserts. An automated server-side mixer should handle dynamic EQ, kick-to-bass sidechain ducking, bass saturation, and transient shaping in its own DSP (e.g., on a USB return or the streamed bus), keeping the MR18 channel strip for gate/comp/EQ.
- **Typical drum layout on 16 inputs** (inference, not sourced): 5–7 drum channels. Minimal 4 (kick, snare, OH L/R). Common 6 (kick in, snare top, hat, OH L/R, plus one tom or kick out). Rich 8 (kick in/out, snare top/bottom, rack tom, floor tom, OH L/R), which leaves 8 inputs for bass DI, keys (stereo), guitar, and vocals. For neo-soul/funk with several vocalists and keys, 6 drum channels is a realistic compromise (kick in, kick out *or* snare bottom, snare top, hat, OH L/R).

### Gaps
- The official MR18/X-Air manual parameter ranges could not be retrieved (fetch blocked), so all numeric ranges above are unverified.
- No source documents common drum channel counts for 16-input live/stream setups.
