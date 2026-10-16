# Linux/Open-Source DSP, Venue-to-Cloud Audio Transport, and A/V Sync for a 16-Channel Cloud Live Mix (DigitalOcean)

Scope note: 15 tool calls. Several primary sites (lsp-plug.in, docs.pipewire.org) could not be reached (DNS failures), so module lists and PipeWire filter-chain syntax are marked as gaps rather than filled in from memory. Arithmetic-based estimates (bandwidth, sample budgets) are listed under Inferences and labelled as calculations, not measurements.

## 1. DSP options: real-time suitability, control APIs, quality, licenses

### Takeaway
The best-documented open-source path is LV2/CLAP plugins (LSP Plugins for gate/EQ/comp/multiband/de-ess-style dynamics, x42-dpl for the true-peak limiter) hosted in Carla, which offers MIDI CC automation and full OSC control. Almost everything in this ecosystem is GPL or LGPL. Because the system runs as a hosted service and the binaries are not distributed, GPL's copyleft obligations are generally not triggered (the AGPL would be the exception). This is a licensing inference and needs legal review.

### Cited Findings
- **LSP Plugins** are an open-source collection in CLAP, VST2/LinuxVST, VST3 and LV2 (all full support), LADSPA (partial: no MIDI or file-loading plugins), GStreamer (experimental), and standalone builds with JACK and Dummy backends (the JACK backend is not available on Windows). Plugin source lives in separate repos under github.com/lsp-plugins. — [LSP GitHub](https://github.com/lsp-plugins/lsp-plugins)
- LSP's license is LGPLv3; package metadata lists it as LGPL-3.0-or-later. — [LSP GitHub](https://github.com/lsp-plugins/lsp-plugins); [SUSE PackageHub](https://packagehub.suse.com/packages/lsp-plugins/); [Alpine lsp-plugins-clap](https://pkgs.alpinelinux.org/package/v3.23/community/riscv64/lsp-plugins-clap)
- Debian has packaged LSP 1.2.33 and 1.2.35, so it is a mature 1.2.x series. — [Debian codegraph 1.2.35](https://codegraph.jelmer.uk/lsp-plugins/1.2.35-1/)
- **x42-dpl (dpl.lv2)** is a look-ahead digital peak limiter based on Fons Adriaensen's DPL-1, in mono and stereo versions.
  - It has digital-peak and true-peak modes. True-peak changes only detection (the key input is 4x oversampled); the audio itself is not altered directly.
  - Latency is 1.2 ms (64 samples at 48 kHz).
  - It is GPLv3, by Robin Gareus, and the latest version found is v6.6 (2024-03-29).
  - Sources: [x42 dpl page](https://rg42.org/oss/lv2/dpl); [x42-dpl man page](https://man.archlinux.org/man/x42-dpl.1.en.txt); [Ubuntu manpage](https://manpages.ubuntu.com/manpages/jammy/man1/x42-dpl.1.html)
- **Carla** offers "automation of parameters via MIDI CC (and send output back as MIDI too)" and "full OSC control". A separate Carla-Control app controls Dry/Wet, Volume, Balance and every plugin parameter over OSC. — [Carla repo README](https://git.kx.studio/falkTX/Carla/src/commit/240132bd9acce75b427afa73ea6febfa882c8aa9)
- The LAC 2018 Carla workshop describes Carla as a host with remote control over OSC, among other methods. — [LAC 2018](https://lac.linuxaudio.org/2018/pages/event/24/)
- **SonoBus** is GPLv3. This matters if its code or AOO is reused. — [SonoBus user guide](https://sonobus.net/sonobus_userguide.html)

### Inferences
- **Suggested plugin map** (LSP module names come from general knowledge of the project and should be verified against lsp-plug.in, which was unreachable):
  - Per channel: LSP Gate Mono, LSP Parametric/Graphic Equalizer x16 Mono, LSP Compressor Mono (sidechain variants can serve as a de-esser via sidechain EQ), plus LSP Dynamic Processor.
  - Buses: LSP Multiband Compressor Stereo.
  - Master: x42-dpl in true-peak mode as the final stage, followed by an EBU R128 meter (x42-meters) or an ffmpeg `ebur128` tap.
  - Reverb: Dragonfly Reverb (Room/Hall/Plate), or LSP impulse-response/convolution reverb.
  - Delay: LSP delay modules.
  - Stereo width: an Airwindows or LSP stereo tool.
- **Control path for an AI agent:**
  - Carla in headless/no-GUI mode with OSC (UDP/TCP) gives the agent a network API for every plugin parameter.
  - Alternatively, write a small custom LV2 host (lilv) or CLAP host that exposes a JSON/WebSocket API. Parameter changes must be smoothed (ramped over 10–50 ms) to avoid zipper noise. Many LSP and x42 controls interpolate internally, but this was not verified.
- **FFmpeg filters** (acompressor, equalizer, alimiter, loudnorm, afir) are fine for offline work or a simple broadcast safety chain, but fit poorly as an interactive live mixer:
  - Parameters can only be changed at runtime through `asendcmd`/`zmq` for filters that support commands.
  - `loudnorm` in single-pass "dynamic" mode is not a substitute for a true-peak brickwall.
  - This judgement is not verified from FFmpeg docs in this session.
- **FAUST** (GPL compiler; generated code can be under any license) is a good option for writing custom DSP compiled into a single-process engine with zero plugin-host overhead.
- **Ardour/Mixbus headless:** Ardour has an OSC surface, and headless operation would use `ardour-lua`/`headless` builds. This is unverified in this session.

### Gaps
- Full LSP module catalog (lsp-plug.in was DNS-unreachable from the research environment).
- Licenses for Airwindows Consolidated (believed MIT), Dragonfly Reverb (believed GPLv3), Calf (LGPL), ZaMaximx2 (GPL), Surge XT FX (GPL3) were not confirmed by sources in this session.
- Carla's exact headless OSC message paths were not found. Check Carla's source (`CarlaEngineOsc*.cpp`) or the Carla-Control client.
- PipeWire filter-chain (supports builtin/LADSPA/LV2 nodes; runtime control via `pw-cli set-param ... Props`) could not be confirmed because docs.pipewire.org was unreachable.
- No sourced GStreamer audio-plugin (lv2 element) suitability data was found.

## 2. CPU cost, buffer/latency budget, and DigitalOcean / RT-kernel feasibility

### Takeaway
PREEMPT_RT has been in mainline Linux since 6.12, but stock Ubuntu kernels do not enable it. DigitalOcean's dedicated-vCPU (CPU-Optimized) plans avoid noisy-neighbour hyperthread sharing. Because the venue-to-cloud network path already adds tens to hundreds of ms of jitter buffering, the cloud mix can run at relaxed buffers (256–1024 frames), which makes VM jitter manageable without an RT kernel.

### Cited Findings
- **PREEMPT_RT in mainline:**
  - It was fully merged into mainline on 2024-09-20, and Linux 6.12 is the first release with real-time support built in for x86/x86_64, ARM64, RISC-V and others. — [Wikipedia PREEMPT_RT](https://en.wikipedia.org/wiki/PREEMPT_RT); [Phoronix](https://www.phoronix.com/news/Linux-6.12-Does-Real-Time)
  - It is now a matter of enabling the CONFIG_PREEMPT_RT options at compile time. — [InfoQ](https://www.infoq.com/news/2024/10/linux-6-12-real-time); [heise](https://heise.de/-10061458)
  - As of March 2026, Ubuntu's stock kernel is not built with CONFIG_PREEMPT_RT=y. You need the Ubuntu Pro real-time kernel or a custom build. — [OneUptime guide (2026-03)](https://oneuptime.com/blog/post/2026-03-02-how-to-install-real-time-kernel-preempt-rt-on-ubuntu/markdown)
- **DigitalOcean plans:**
  - CPU-Optimized droplets are dedicated-vCPU plans with 2–48 vCPUs and 2 GB RAM per vCPU. — [DO free-trial VM page](https://try.digitalocean.com/virtualmachines)
  - Dedicated vCPUs get "guaranteed access to the full hyper-thread at all times". Shared vCPUs may get only fractions of hyper-threads when neighbours are loaded. — [DO: Choosing a plan](https://docs.digitalocean.com/products/droplets/concepts/choosing-a-plan/)
  - Premium CPU-Optimized variants exist. — [DO blog](https://digitalocean.com/blog/introducing-premium-cpu-optimized-droplets)
- **Latency perspective:** JackTrip's own paper notes that delays as low as 25 ms are already problematic for ensemble playing. That is irrelevant here, because no musician monitors the cloud mix. — [Cáceres & Chafe 2009](https://ccrma.stanford.edu/~jcaceres/publications/PDFs/conferences/2009-caceres_chafe-ICMC-jacktrip.pdf)

### Inferences
- **CPU estimate** (calculation from typical figures, not measured):
  - Gate, 4–8-band IIR EQ and RMS/peak comp per mono channel typically cost well under 1% of one modern core each at 48 kHz. So 16 channels × 3 plugins is roughly 48 instances, or about 0.5–1.5 cores.
  - Two algorithmic reverbs (Dragonfly), delays, 4–6 bus compressors, a multiband comp and a 4x-oversampled limiter on master add roughly 0.5–1 core. Convolution reverb with long IRs is heavier.
  - Total is about 1–3 cores. A 4-dedicated-vCPU CPU-Optimized droplet could handle audio, but video encode must be sized separately (see section 5).
  - Benchmark the actual chain with `jack_iodelay`/`perf` or Carla's DSP-load meter before relying on this.
- **Buffer recommendation:**
  - Run JACK or PipeWire on a dummy/null driver (there is no sound card in a droplet) at 48 kHz with 256–512 frames (5.3–10.7 ms) and 2–3 periods.
  - Pin the audio thread to a dedicated vCPU (`isolcpus`/`taskset`) with SCHED_FIFO via `rtprio` limits. The PREEMPT_RT kernel can be custom-built from mainline 6.12+.
  - xruns on a VM cause clicks in the broadcast, so prefer larger buffers. A 20 ms buffer is negligible compared to the end-to-end YouTube latency of several seconds.
- **End-to-end latency budget** (all estimates):
  - Venue USB capture, about 5–10 ms.
  - Encode/packetize, about 5 ms.
  - Internet path, 20–80 ms.
  - Jitter buffer/SRT latency, 120–500 ms.
  - Cloud DSP, about 10–20 ms (plus limiter look-ahead of 1.2 ms).
  - Video compositing and encode, 50–200 ms.
  - YouTube ingest-to-viewer, several seconds.
  - The audio path must be deliberately delayed to match the slowest video path (see section 4).

### Gaps
- No published benchmarks were found of LSP or Carla DSP load on DigitalOcean vCPUs.
- Whether DigitalOcean droplets allow booting a custom PREEMPT_RT kernel. DO supports custom kernels via GRUB on most images, but this was not verified.
- Measured VM scheduling jitter on DO was not found.

## 3. Transport: Windows laptop (X-Air/MR18 USB) to the cloud server

### Takeaway
The raw stream is about 18.4 Mbps (16 ch × 48 kHz × 24-bit), which is affordable on most venue uplinks, though about 2x headroom is needed. The most robust internet options are:
- SRT carrying lossless audio, with ARQ retransmission and a configurable latency window.
- JackTrip or SonoBus/AOO, which are purpose-built for multichannel uncompressed PCM with jitter buffers.

In both cases the server must do adaptive resampling to absorb the laptop-vs-server clock drift.

### Cited Findings
- **Capture hardware and drivers:**
  - X-Air X18/XR18 units are 18x18 USB audio interfaces. — [listing](https://avlgear.com/collections/new-collection/products/behringer-x-air-x18-18-channel-12-bus-tablet-controlled-digital-mixer)
  - Behringer documentation says the XR18 driver supports WDM, WASAPI and ASIO.
  - A user recording 18 channels on Windows reported two quirks: it only worked when all 18 channels were selected, and only when the Behringer driver was also the output device. — [Audacity forum](https://forum.audacityteam.org/t/multitrack-recording-behringer-x18/45653)
  - A third-party page cites X18 USB driver version 5.72.0. This is not confirmed as current. — [acoustics-engineering](https://acoustics-engineering.com/html/x18-driver.html)
  - "Midas M18" was not found in searches. It most likely refers to the Midas MR18, the Midas-branded sibling of the XR18 (same 18x18 USB). This identification is unverified.
- **JackTrip:**
  - Both sides must use the same sample rate and buffer size, or the connection fails.
  - The receive jitter queue (`-q`) defaults to 4 packets, or "auto" in the managed service. A CCRMA guide suggests `-q8` if you hear dropouts. — [JackTrip support](https://support.jacktrip.com/managing-virtual-studios); [jacktrip man page](https://man.archlinux.org/man/extra/jacktrip/jacktrip.1.en); [CCRMA course notes](https://ccrma.stanford.edu/~cc/deck.js/153bSpring2020/index.html)
  - Lower-bandwidth or lower-QoS links run better with a lower sample rate and a larger buffer. — [ZHdK JackTrip manual](https://blog.zhdk.ch/zmoduletelematic/files/2014/02/Operation-Jacktrip-Manual.pdf)
  - Stereo 48 kHz needs about 2.0 Mbps in the managed-service presets. — [JackTrip support](https://support.jacktrip.com/managing-virtual-studios)
- **SonoBus:**
  - SonoBus offers full uncompressed PCM at 16/24/32-bit, or Opus at 16–256 kbps per channel. — [SonoBus GitHub](https://github.com/essej/sonobus)
  - It has per-user manual or automatic jitter-buffer control. Audio goes peer-to-peer, and the connection server only handles discovery. — [SonoBus user guide](https://sonobus.net/sonobus_userguide.html)
  - It is GPLv3. — [SonoBus user guide](https://sonobus.net/sonobus_userguide.html)
  - Wi-Fi adds jitter and loss, which requires a bigger buffer. — [sonobus.net](https://sonobus.net/)
- **AOO (Audio over OSC):**
  - Implemented codecs are PCM and Opus.
  - The sink-side jitter buffer handles jitter, reordering and loss, and sinks can request resends of dropped packets. — [AOO fork README](https://github.com/faisyl/aoo)
  - A SonoBus–AOO link was not verified in this session.
- **SMPTE 302M (AES3 PCM in MPEG-TS) via FFmpeg:**
  - The encoder supports only 2, 4, 6 or 8 channels, at 48 kHz, S16/S32. — [FFmpeg s302menc source](https://ffmpeg.org/doxygen/4.0/s302menc_8c_source.html)
  - MPEG-TS muxing support was added in 2012. — [ffmpeg-user 2012](https://ffmpeg.org/pipermail/ffmpeg-user/2012-April/006038.html)
  - A 2020 ticket (#8660) reports that s302m is muxed as a private data stream and may not be recognized on reading. — [FFmpeg trac #8660](https://ffmpeg.org/pipermail/ffmpeg-trac/2020-May/054245.html)
  - So 16 channels would need two 8-ch s302m streams in one TS.
- **Clock drift:**
  - zita-ajbridge (the sibling of zita-njbridge) uses zita-resampler with a slowly varying ratio, typically within a few ppm, driven by a control loop. Resampling can be disabled only when devices share word-clock. — [zita-a2j man page](https://manpages.ubuntu.com/manpages/jammy/man1/zita-j2a.1.html); [zita-ajbridge quickguide](https://kokkinizita.linuxaudio.org/linuxaudio/zita-ajbridge-doc/quickguide.html)
  - Two unsynchronized sound cards drift against each other. — [jack-devel list](https://lists.linuxaudio.org/archives/jackaudio/2018-January/001221.html)

### Inferences
- **Bandwidth arithmetic:**
  - 16 × 48,000 × 24 = 18.43 Mbps raw PCM. Packet and SRT overhead plus retransmission headroom bring it to roughly 22–30 Mbps.
  - Sending 32-bit containers (S32) raises the raw figure to 24.6 Mbps.
  - FLAC typically compresses live multitrack by about 40–60%, to roughly 8–11 Mbps, but adds block latency and is less common in TS. These are general estimates, not sourced.
  - Opus would reduce bandwidth sharply but is lossy. That is acceptable for some sources but not "uncompressed" as the brief requests.
- **Recommended transport ranking** for "transmit only, robust over the public internet":
  1. **SRT** (open source, MPL-2.0 libsrt; license not verified this session). Run in caller mode from the laptop with `latency=300–1000ms` for ARQ recovery. Payload is either 2× s302m 8-ch in MPEG-TS, or a custom framing such as raw PCM in Matroska/NUT over SRT via FFmpeg (`-f nut` or `-f matroska` with `pcm_s24le` 16-ch, `-c:a pcm_s24le -ac 16`). This keeps all channels in one sample-locked stream. Latency is tunable and handles loss via retransmission.
  2. **JackTrip** (hub-server mode on the droplet; the Windows client uses ASIO) with `-n 16` channels and a larger `-q`. This gives native multichannel uncompressed PCM, but its UDP has no retransmission, only PLC/queueing.
  3. **SonoBus** (Windows app with ASIO; supports multichannel send). It is GUI-oriented, and a headless Linux receive needs verification.
  4. **VBAN/NDI:** designed for LANs, not appropriate for WAN without a VPN tunnel. This is general knowledge, not sourced here.
  5. **WebRTC Opus:** standard WebRTC Opus is stereo. Multichannel Opus (the "multiopus" extension) is non-standard and lossy, so it is a poor fit (unsourced).
  - RIST is a valid SRT alternative (librist, BSD-2), but no source was collected.
- **Windows capture:** Use ASIO (the Behringer X-AIR driver) into FFmpeg via a DirectShow/WASAPI capture of the 18-ch device, or use JackTrip/SonoBus's built-in ASIO. Do no processing on the laptop. Set the Windows power plan to High Performance, disable USB selective suspend, and use wired Ethernet rather than Wi-Fi (SonoBus notes Wi-Fi jitter).
- **Drift handling on the server:** The laptop's USB audio clock (driven by the mixer's 48 kHz clock) will differ from the server's system clock by tens of ppm. Over a 3-hour show, 50 ppm ≈ 0.54 s of accumulated drift (calculation). The receiver must therefore either:
  - make the incoming stream the master clock (a JACK dummy driver slaved to it), or
  - adaptively resample (zita-resampler, as in zita-njbridge; GStreamer `audiorate`/clock-slaving; FFmpeg `aresample=async=1` with `min_hard_comp`).

### Gaps
- Official current Behringer/Midas driver version and its Windows 11 behaviour.
- Confirmed FFmpeg behaviour for 16-ch `pcm_s24le` over SRT in Matroska/NUT (believed to work, but untested and unsourced).
- zita-njbridge documentation itself was not retrieved.
- No head-to-head WAN loss/latency benchmarks of SRT vs JackTrip vs SonoBus for 16 channels were found.

## 4. A/V sync: board audio (laptop path) vs phone video (WebRTC path)

### Takeaway
Rely on automatic alignment by cross-correlating each phone's own mic audio, which arrives with its video, against the board mix. GCC-PHAT or FFT cross-correlation gives a global offset plus a confidence score. Then apply a continuously adjusted delay to the audio, or to the video, so that all paths are aligned to the slowest one. Clap/slate measurement is a manual fallback. NTP/PTP alone cannot account for codec, capture and buffer latencies that differ per device.

### Cited Findings
- GCC-PHAT is a frequency-domain generalized cross-correlation that normalizes by spectral magnitude. It is computationally cheap and noise-robust (Brandstein & Silverman 1997). — [USPTO patent 9877066](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9877066)
- GCC-PHAT estimates delay by locating the cross-correlation peak, and inputs must share a sample rate. — [MathWorks gccphat](https://www.mathworks.com/help/phased/ref/gccphat.html)
- FFmpeg's `axcorrelate` filter computes windowed cross-correlation, giving a time series rather than one offset. FFT-based `scipy.signal.correlate(method="fft")` gives one global offset with confidence. — [video-studio multicam-sync doc](https://raw.githubusercontent.com/brianwestphal/video-studio/HEAD/docs/multicam-sync.md)
- An open-source example of offset-plus-confidence multicam sync exists (Node + ffmpeg). Its docs describe it as partially complete. — [video-studio multicam-sync doc](https://raw.githubusercontent.com/brianwestphal/video-studio/HEAD/docs/multicam-sync.md)
- A ComfyUI node applies GCC-PHAT for audio alignment. — [RunComfy Audio Align XCorr](https://www.runcomfy.com/comfyui-nodes/ComfyUI-Egregora-Audio-Super-Resolution/audio-align-x-corr)

### Inferences
- **Practical design:**
  - Resample each phone's WebRTC audio (Opus, 48 kHz) and the board mix (pre-reverb main bus or a vocal-heavy sum) to 8–16 kHz mono.
  - Every 5–10 s, run GCC-PHAT over a 5–10 s window with a search range of ±2 s.
  - Accept the result only if the peak-to-sidelobe ratio exceeds a threshold, and median-filter the offsets.
  - Apply the offset as a smoothly slewed delay to that phone's video in the compositor (GStreamer `queue`/`timestamp offset` on pads, e.g. `pad.set_offset()`).
  - Hold the board audio at a fixed delay equal to the maximum video-path latency.
- **Why correlation beats clock sync:** Room acoustics add distance delay (about 2.9 ms/m from stage to phone mic, a physics calculation). This bias is small compared to frame time (16.7 ms at 60 fps) for phones within about 5 m. Each phone's capture pipeline, encoder and WebRTC jitter buffer add variable latency that RTCP Sender Reports/NTP timestamps only partly expose.
- **Using RTP timestamps:**
  - WebRTC RTCP SR packets map RTP timestamps to the sender's NTP wallclock. Phones' NTP sync accuracy is typically tens of ms, which is insufficient alone.
  - The laptop stream can carry its own timestamps (SRT carries source timestamps; MPEG-TS PCR/PTS). Combine them with correlation to track drift continuously.
- **Slate fallback:** Clap at soundcheck, measure the offset per phone from the correlation peak or by eye in a waveform view, and store it as the initial offset.

### Gaps
- No dedicated, maintained open-source real-time GCC-PHAT A/V sync tool for live streams was found. Expect to build it with SciPy/numpy or FFTW.
- Typical measured WebRTC capture-to-receive latency variance for phones at 1080p60 was not found.

## 5. Video: WebRTC ingest, compositing, 1080p60 encode to YouTube

### Takeaway
Use a WebRTC SFU (LiveKit, mediasoup or Janus) to ingest the phones. Composite with GStreamer (`compositor`) or LiveKit Egress (headless Chrome), then encode H.264 1080p60 CBR with a 2-second keyframe interval to YouTube over RTMPS. CPU x264 at 1080p60 needs a large dedicated-vCPU droplet. DigitalOcean GPU droplets exist, but NVENC exposure on them was not confirmed.

### Cited Findings
- **LiveKit Egress:**
  - RoomComposite launches headless Chrome, which joins as a hidden participant and captures the rendered template. GStreamer handles transcoding.
  - Output can be MP4, HLS, or RTMP(S) to YouTube, Twitch or Facebook.
  - Track egress exports individual tracks without transcoding video. — [LiveKit Egress docs](https://docs.livekit.io/server/egress); [pkg.go.dev egress](https://pkg.go.dev/github.com/livekit/egress@v1.8.4)
  - LiveKit chose Chrome over FFmpeg and GStreamer for composition because their multi-video stitching APIs were "rigid, verbose and difficult to debug". — [LiveKit blog](https://livekit.com/blog/livekit-universal-egress-launch)
- **YouTube live settings:**
  - Use CBR with a 2-second keyframe interval (maximum 4 s). At 60 fps that is 120 frames.
  - AAC audio at 128 kbps is recommended; use RTMPS where possible. — [streamer.guide (June 2026)](https://streamer.guide/guides/bitrate-encoder-settings-cheat-sheet); [space-node 2026 guide](https://space-node.net/blog/youtube-live-encoder-settings-bitrate-guide-2026)
  - The 1080p60 H.264 bitrate guidance conflicts across secondary sources: "6 Mbps min / 17 Mbps recommended" vs "6 Mbps" vs "6–9 Mbps". Verify on YouTube's official "Choose live encoder settings" page. — [space-node](https://space-node.net/blog/youtube-live-encoder-settings-bitrate-guide-2026); [macmyths](https://macmyths.com/ffmpeg-command-for-1080p-60fps-youtube-live-streaming/)
- **DigitalOcean GPU Droplets** offer NVIDIA H100, H200, L40S, RTX 4000 Ada and RTX 6000 Ada, plus AMD MI300X. The L40S/RTX 4000/RTX 6000 options come with 8 vCPUs and 32–64 GiB RAM. — [DO droplet features](https://docs.digitalocean.com/products/droplets/details/features/index.html.md)
- CPU-Optimized droplets list video encoding among their use cases. — [DO VM page](https://try.digitalocean.com/virtualmachines)

### Inferences
- The L40S and RTX 4000/6000 Ada are workstation/datacenter GPUs that physically include NVENC hardware. H100 has no NVENC, which is general knowledge, not sourced here. Whether DO's drivers and images expose NVENC must be tested.
- **CPU encode:** x264 1080p60 at `veryfast`/`faster` at about 9–12 Mbps typically needs about 4–8 modern cores. Adding decode of N phone streams (VP8/H.264 1080p60) plus compositing points to a 16-dedicated-vCPU CPU-Optimized droplet, or a split architecture: an audio droplet and a video droplet, or one GPU droplet. This is a general estimate, not measured.
- **Audio into the video pipeline:** Feed the processed stereo master from JACK/PipeWire into GStreamer (`jackaudiosrc`/`pipewiresrc`) or FFmpeg (`-f jack`), then AAC-encode it at 128–320 kbps and mux it with the composited video. A common timeline clock is essential, so make the GStreamer pipeline clock follow the audio clock.
- **Licensing:**
  - LiveKit server/egress is Apache-2.0 and mediasoup is ISC (both unverified this session).
  - GStreamer core is LGPL, but x264 is GPL. For a hosted service (no distribution), GPL/LGPL obligations are generally not triggered.
  - FFmpeg builds with `--enable-gpl --enable-nonfree` (fdk-aac) are not redistributable, but are usable internally.
  - Patent licensing for H.264/AAC is a separate consideration.

### Gaps
- No source confirmed NVENC availability on DigitalOcean GPU droplets.
- No sourced CPU benchmarks were found for x264 1080p60 or for GStreamer `compositor` with N inputs on DO vCPUs.
- GStreamer `webrtcsrc`/`webrtcsink` (gst-plugins-rs) and Janus/mediasoup ingest details were not researched due to the tool-call budget.
