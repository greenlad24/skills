# Master/loudness for YouTube LIVE + MR18/XR18 USB multitrack routing (YouTube-sourced)

Verification tags: [N videos / N channels, view counts]. Per the coordinator's rule, a finding counts as **verified** if it comes from a video with at least 100k views, from at least 2 independent channels, or (for MR18 routing) from official Behringer/Midas material. Each section ends with an "Unverified" list for claims that pass none of these tests. View counts come from the yt.py search helper on 2026-10-16. Transcripts are auto-captions, so quotes are lightly cleaned.

## Q1. Which X-Air USB send tap point gives raw (pre-processing) channels, and how do you set it?

### Takeaway
In X-Air Edit, go to In/Out > USB Sends and set the tap point to **"Analog"**. The legend's "Default signal tap" dropdown applies it to every channel at once. This records the preamp signal before gate, EQ, dynamics and fader, and it is the setting recording tutorials recommend [2 channels; 156.6k + 189.7k-channel]. The signal still follows the preamp **gain**, so gain staging affects the recording.

### Cited Findings
- Path: In/Out tab > USB Sends. That page sets "what actually goes out of our USB audio interface to our DAW." Quote: "when we're recording this audio, we want to have it unprocessed, meaning that I don't want my gate, my EQ, my dynamics, any of that to be affecting the audio... we want to have this set on... analog. And... we can go down to default signal tap, and we can set this to analog, and then... select all of our channels." The alternative named is post fader, which includes the processing. — Behringer XR18 Multitrack Recording Setup — Drew Brashler — https://www.youtube.com/watch?v=y4kxfwblFTs [156.6k views]
- Agreement from a second channel: on USB sends, "for recording purposes you generally want the red ring [the colour the legend gives this tap]... it's all one to one." — Connecting The Behringer XR18 To Reaper — Alan Hamilton Audio — https://www.youtube.com/watch?v=xYmJGyroVe0 (Alan Hamilton's channel also has XR18 videos at 189.7k, 150.5k and 119.7k views; the view count of this video was not printed) [2 channels agree]
- Gain still matters with the Analog tap. Drew shows a kick clipping in the DAW and fixes it with channel gain, "hitting that nominal gain of about -18 -20 mark." — Drew Brashler, y4kxfwblFTs [156.6k]
- Full list of tap options, from a web source rather than a video: Analog (default), Input, Pre EQ, Post EQ, Pre Fader, Post Fader, each also available with a "+Mute" variant. There is **no post-effects tap** per channel. — [TridentSound VK guide (Russian), via search snippet](https://vk.ru/@tridentsound-naznachenie-usb-vyhodov-pri-zapisi-multitreka-s-xr18-i-mr18). The page could not be fetched (DNS failure), so this rests on the search-result summary only. MusicRadar also confirms selectable pre/post fader and pre/post EQ tapping for USB, Aux, Ultranet and Main outs — [MusicRadar review](https://musicradar.com/reviews/behringer-x-air-xr18)
- Source-side switch: on the **USB Returns** tab, the "off analog" button "makes sure that all the mixer channels are getting their signal from the preamp and not the USB input." Use it for recording. "Ch 1-16" switches the channels to USB playback for a virtual soundcheck. — Alan Hamilton Audio, xYmJGyroVe0; virtual soundcheck also covered in Drew Brashler "Behringer XR18 Virtual Sound Check" https://www.youtube.com/watch?v=cGROKcBcjRc [82k] [2 channels]
- Do not confuse these with the **channel/aux send tap points**, which are a separate matrix. Aux send tap points are all pre-fader variants. Pre-EQ is the safest choice for monitors, Post-EQ adds EQ without compression, and "Pre-fader" includes both EQ and compressor. Output (Aux Out) tap should stay Post Fader. Alan notes "behringer's own graphic showing the signal flow chart is wrong about the position of the highpass filter in relation to one of the tap points." — Demystifying XR18 Channel Send & Output Tap Points | Mixing Station and X-Air Edit — Alan Hamilton Audio — https://www.youtube.com/watch?v=hUxVALTQ3Po (single video, but on a 100k+ channel)
- Mixing Station shows the same options: "click the arrows icon, choose output routing"; channel sends offer the same tap dropdowns. — Alan Hamilton Audio, hUxVALTQ3Po

### Inferences
- For Sunrise Jam, set USB Sends 1–16 to Analog, 1:1. The cloud server then gets raw channels and can apply its own HPF/gate/EQ/comp. MR18 trim settings still change the level, so lock them after soundcheck.
- Whether "Analog" or "Input" includes the digital low-cut or polarity flip could not be confirmed from video. Alan flags a known error in the official flow chart. Test it: engage the HPF on one channel and check whether the DAW track changes.

### Gaps
- No video read out the full tap-option list with exact definitions. The official XR18 manual block diagram was not fetched.

### Unverified
- The claim that per-channel pre/post cannot be set individually comes from a Bonedo (German) review snippet, based on older software. — [Bonedo](https://www.bonedo.de/artikel/behringer-x-air-xr18-test/)

## Q2. 18x18 USB layout, channels 17/18, sample rate, Windows driver/ASIO, Studio One

### Takeaway
The USB interface carries 18 sends and 18 returns, 1:1 by default. USB 17/18 default to the Aux In (L/R). Replace that with Main L/R if the aux input is unused, which records a reference mix alongside the 16 raw tracks. On Windows, install the Behringer USB/ASIO driver, set the mixer clock to 48k, and match it in the DAW.

### Cited Findings
- On Windows, "you will need to download the Behringer driver... at behringer.com." Mac uses Core Audio class-compliant. Any DAW works; Studio One is named. In the DAW, select X18/XR18 or MR18 as the device. — Drew Brashler, y4kxfwblFTs [156.6k]
- Tip: if you use only the XLR inputs, set USB sends **17/18 to Main L/R** instead of Aux In, optionally post-fader. That gives "the multi track files of the 16 inputs, but then also a post mix of your left right fader." — Drew Brashler, y4kxfwblFTs [156.6k]
- Clock rate: "In Setup > Audio/MIDI... the clock rate line you have the two choices of 48k and 44.1... reaper will need to have the same clock setting... let's just use 48k." DAW: ASIO, 48000, block size 256. — Alan Hamilton Audio, xYmJGyroVe0 [2 channels agree on the driver/ASIO setup]
- Driver pitfall: "I installed the most recent driver first but then I needed to install the older driver as well to make things work correctly." He also advises updating X-Air Edit and the firmware. — Alan Hamilton Audio, xYmJGyroVe0
- By default USB returns 17/18 feed Aux In L/R. The Aux channel's source must be set to "USB" for DAW playback. — Alan Hamilton Audio, xYmJGyroVe0; "how to use channels 17/18" — Ben Isaac — https://www.youtube.com/watch?v=gJGRla6fhNE [32.9k] [2 channels]
- Official Behringer how-to videos cover USB playback and recording: "X AIR How To: USB Audio Playback (X18/XR18)" https://www.youtube.com/watch?v=EbrxvIzi9Fs and "X AIR How To: Recording from the XR18 directly to your iPad using Auria" https://www.youtube.com/watch?v=iGQASoHKZX0 [221k]

### Inferences
- 48 kHz matches video and broadcast practice. Set it on the MR18 first, then on the laptop's ASIO host.

### Gaps
- No video gave the current Windows driver version or a 96 kHz option. 44.1 and 48 kHz were the only rates shown.

## Q3. Does X-Air have automix?

### Takeaway
Yes. Behringer's own "X AIR How To" series has videos titled "Auto Mixing in Depth" and "Auto-Mixing (Android)." Retail descriptions call it Dugan-based gain sharing for up to 16 mics.

### Cited Findings
- "X AIR How To: Auto Mixing in Depth" — Behringer — https://www.youtube.com/watch?v=FQrVHU0AClc [152.6k]; "X AIR How To: Auto-Mixing (Android)" — Behringer — https://www.youtube.com/watch?v=PdMpPLodRRk [81k]; "Using the AutoMix feature on the XR12/XR16/XR18 via Mixing Station" — https://www.youtube.com/watch?v=Szc5soVcr-k [1.4k] [official + 3 channels]. Transcripts were unavailable (rate-limited), so details were not extracted.
- Retail copy: "Dan Dugan-based gain sharing... up to 16 live microphones." Older listings said "(future firmware)." — [Gear4music listing](https://www.gear4music.com:443/us/en/PA-DJ-and-Lighting/Behringer-X-AIR-XR18-Digital-Mixer/18DJ)

### Inferences
- Automix is designed for speech/panel mics. It is not meant for a band and does not affect raw USB Analog-tap sends.

### Gaps
- The automix group (X/Y) structure and per-channel weighting were not confirmed from video.

## Q4. Loudness target and YouTube LIVE normalization

### Takeaway
Stream engineers target about **-16 LUFS integrated**, with a limiter ceiling of **-0.5 to -1 dBFS** [2 channels; 109k + 6k]. YouTube does **not turn up** quiet content [2 channels; 147k + 0.5k], so a quiet stream stays quiet. One engineer reports YouTube does not touch live-stream loudness at all, which is unverified. Treat loudness as the cloud mixer's responsibility.

### Cited Findings
- "For most of our streaming platforms, we should be targeting -16 LUFS." — Church Stream Audio Setup - Louder Stream Audio LUFS — Drew Brashler — https://www.youtube.com/watch?v=2jhggSKR2AI [109.5k]
- Agreement: "if I were to calibrate it to youtube it's negative 14, which is fairly hot in my opinion... I usually shoot for negative 16." — LUFS and Loudness For Livestreamed Events Explained — Michael Curtis — https://www.youtube.com/watch?v=tpFsW1G-sVg [6.4k] [2 channels agree on -16]
- No positive gain: "YouTube music will not apply positive gain on a quiet master," while louder masters are turned down. — Don't Make This Loudness LUFS Mistake — Mixdown Online — https://www.youtube.com/watch?v=VKpCaFST6zU [147k]; also "YouTube will not normalize your audio up to meet the -14 LUFS... YouTube will leave it where you had it." — Perfect YouTube LUFS Every Time — The Frugal Streamer — https://www.youtube.com/watch?v=s0vt6gK7DMo [530] [2 channels]
- How to check: right-click the player > "Stats for nerds" > "Volume / Normalized ... content loudness -3.8 dB," meaning 3.8 dB under YouTube's -14 reference (about -18 LUFS). — Michael Curtis, tpFsW1G-sVg
- "Streaming not loud enough" is the most common live-stream complaint. The fix is a limiter on the stream bus. — SOLVED: Live Stream Not Loud Enough — Collaborate Worship — https://www.youtube.com/watch?v=5jA7-GLzt0M [99.5k]; Drew Brashler 2jhggSKR2AI [109k] [2 channels]
- Web check: no official YouTube document sets a LUFS target for live streams. The -14 figure comes from VOD/upload behaviour. — [web search summary; Sweetwater/Youlean pages](https://www.sweetwater.com/insync/?p=225563)

### Inferences
- A live stream's VOD archive probably gets the same "turn down only" treatment as uploads, so -16 to -14 LUFS integrated is safe both live and as VOD. Avoid going much hotter, because the VOD would only be turned down and the extra squash would sound worse.

### Gaps
- No official YouTube source confirms whether normalization applies **during** a live broadcast.
- No video gave a true-peak (dBTP) figure specifically for 128 kbps AAC live. Ceilings in videos were sample-peak settings of -0.5, -1 and -3.3 dBFS.

### Unverified
- "If I'm going live to YouTube it is not looking at my level and is not going to touch it." — Michael Curtis, tpFsW1G-sVg [6.4k, single]
- "They say that's negative [1]4 LUFS... we found that if our broadcast matrix is near clipping then it works well going into our ATEM." The caption is garbled as "negative4." — Broadcast Mix on an X32 — Ryland Russell — https://www.youtube.com/watch?v=YM3FiDcTJRU [35.9k]
- The Frugal Streamer's claim that YouTube "over compresses" loud audio is likely wrong. YouTube applies a gain reduction, not compression, per Mixdown Online. — s0vt6gK7DMo [530]

## Q5. Master-chain settings (glue comp, EQ, multiband, limiter)

### Takeaway
The consensus chain is light bus glue (about 2:1, a few dB), gentle tonal EQ (a small high-shelf "air" lift and a mid cut), optional dynamic EQ or multiband, then a brickwall limiter that peaks at only **about 3–4 dB gain reduction**. It sits last in the chain, inserted post on the stream bus, with input gain of about +12 dB as a starting point [limiter: 2 channels, 109k + 99.5k].

### Cited Findings
- X32/XR "Precision Limiter" starting point (Drew): input gain +12, squeeze 60%, output -0.5, knee 0, attack 0.1, release 96 (keep release ≤100 ms), stereo link on, auto gain off. — Drew Brashler, 2jhggSKR2AI [109.5k]
- Same effect (Collaborate Worship): input +12 dB, output -1 dB ("makes sure that the output will never exceed -1dB"), squeeze 20% ("too high... can add a bit of distortion"), knee 3, attack 0.5 ms, release 150 ms, stereo link on, auto gain off. "Adjust the input gain so the gain reduction meter... reads no more than three or four dB... higher than that you'll start to notice the limiter kind of sucking in." Set the bus **insert position to post**. Recheck at every rehearsal. — Collaborate Worship, 5jA7-GLzt0M [99.5k] [2 channels agree on +12 in, limiter last, ceiling ≤ -0.5/-1]
- Broadcast master (Waves-sponsored engineer): F6 dynamic EQ first, "just a couple dB... a little bit of high end... putting a little bit of that sparkle back that may have dissipated by the time you added room mics and audience mics," plus a mid-range cut. Then a multiband stage ("adds about 100 ms latency... that's why this is at the very end"). Then an L3 Ultramaximizer with "about 3 dB of attenuation at the very most." Output ceiling -3.3 dBFS, checked against a hardware meter. Prefers "a brick wall limiter" over "straight compressors" for the final stage. — How to Level Broadcast Mixes without Overcompressing — Waves Audio — https://www.youtube.com/watch?v=LCgUWA8D2Zs [100k]
- Glue/bus comp: drums go to a drum bus with light compression "to help glue." The instrument bus is about 2:1 with zero attack and slower release, "almost function a little bit like a limiter." Vocals go through a subgroup bus with CLA-2A. The master uses a "Master bus super glue" preset (Waves Abbey Road TG Mastering Chain) followed by a limiter. — How I Mix a Church Live Stream in Logic Pro — Churchfront — https://www.youtube.com/watch?v=2FfNDsyd8O0 [99k]; Ryland Russell (35.9k) also uses a precision limiter last, "just trying to knock about [a few dB]," warning against "pumping your mix" [2 channels on light glue and limiter last]
- Tonal EQ for the stream: match the stream tonality to the room mix. Drew adds an EQ curve to restore warmth and low end that gets lost when monitoring at lower levels. — Drew Brashler, 2jhggSKR2AI [109k]

### Inferences
- In a cloud DAW: 2:1 glue at 1–3 dB GR, then a +1–2 dB high shelf and a small mid dip, then optional multiband (watch latency against A/V sync), then a true-peak limiter at about -1 dBTP with ≤3–4 dB GR, aiming for about -16 to -14 LUFS-I. The -1 dBTP figure is my extrapolation from the -0.5 to -1 dBFS ceilings above plus AAC overshoot, which is not video-verified.

### Gaps
- No video gave specific multiband crossover or threshold settings for a live music stream.

## Q6. Stereo widening, mid-side, mono safety

### Takeaway
Keep the low end and lead elements centered. Hard-panned elements drop about 6 dB in mono, and any side-channel boost or widening disappears entirely in mono, so do not lean on wideners for the stream mix. Verified by one high-view video (322k).

### Cited Findings
- "Hard-panned signals will end up almost exactly 6 dB lower in level in the mono downmix." A -6 dB pan law keeps the mono downmix constant, while -3 dB suits stereo. Boosting side via M/S EQ makes parts "literally disappear in mono as the side channel will just cancel out." Removing mid entirely "is going to literally disappear completely in mono... a bit too extreme." Treat reverb/delay returns as mix elements and pan them deliberately. — How to Mix in Stereo... Without Sucking in Mono (part 1) — FabFilter — https://www.youtube.com/watch?v=spaqBr-cCFw [321.8k]
- Related video, title only (not transcribed): "You Suck at Mixing #3: True vs. Fake Panning & Mono Compatibility" — You Suck at Producing — https://www.youtube.com/watch?v=8DQeE3WUKEI [250.8k]
- Stream bus pans can differ from the house mix. Mono house channels are panned slightly in the stream bus for width. — Ryland Russell, YM3FiDcTJRU [35.9k]

### Gaps
- No live-stream-specific video on M/S processing of the master was found.

## Q7. Ambience/audience mics, aux-fed stream mixes, ducking, codec

### Takeaway
Audience/crowd mics that feed only the stream, plus slightly more reverb than in the house, are the standard way to restore "liveness" [3 channels; 99k + 35.9k + 32k]. An independent stream bus or matrix (sends-on-fader) is preferred over taking the main L/R. YouTube's AAC encoding mainly softens high-frequency detail, but 2026-era encoding is broadly equivalent to a good MP3 (single low-view source).

### Cited Findings
- Crowd L/R mics go only to the stream bus. Stream FX sends are set "hotter... a good blend of crowd mic and reverb makes for a more live feel." The stream bus (11/12) uses sends-on-fader as "an independent starting point," combined with a pre-fader drum bus into a broadcast matrix. — Ryland Russell, YM3FiDcTJRU [35.9k]
- Crowd mic on/off demo, plus more reverb on stream vocals: "helps simulate what it's like to actually be in that room." — Why Your Church Livestream Sounds Awful — REACHRIGHT — https://www.youtube.com/watch?v=M2lSjjLai8Y [32.4k]
- Plans to add crowd mics "would add so much more life to this mix." — Churchfront, 2FfNDsyd8O0 [99k] [3 channels agree]
- After adding room/audience mics, the master needs a high-end lift to restore sparkle. — Waves, LCgUWA8D2Zs [100k]
- Aux-fed pitfall: a stream bus fed from house-dependent sends ties the stream to house fader moves. Use an independent stream bus, or here, raw USB. — Ryland Russell (35.9k) and Michael Curtis "Mixing The House AND Your Livestream At The Same Time" https://www.youtube.com/watch?v=lrcp6vR2LhM [12.5k] (title/topic only)

### Inferences
- In this rig, the cloud server receives raw USB channels, so house fader moves cannot affect the stream. If Sunrise Jam has no audience mic, an ambience mic on one of MR18 inputs 17/18 (via the Aux In) or a spare input would cover this need.

### Unverified
- Ducking crowd mics with a sidechain keyed from a drum bus (bus 9), about 15 dB reduction while drums play, with "really long" hold and release. — Ryland Russell, YM3FiDcTJRU [35.9k, single]
- Codec: YouTube audio is AAC, and "the first thing to suffer is the high end." The hi-hat detail lost is "quite subtle... broadly equivalent" to high-rate MP3. — "YouTube Compression": What Is It... — Joe Perkins — https://www.youtube.com/watch?v=vCU93TcX21I [3.8k, single]
- The specific 128 kbps AAC live artifacts (pre-echo, stereo-side swishing) were not covered by any video found. The idea of keeping limiter ceiling headroom for encoder overshoot is supported only by the Waves engineer's -3.3 dBFS ceiling (100k), and he does not state that reason.
