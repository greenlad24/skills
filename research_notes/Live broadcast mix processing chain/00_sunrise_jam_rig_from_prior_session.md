# Sunrise Jam rig — facts recovered from the user's earlier StageMix session (Jul–Aug 2026)
Source: user's own statements + real mixer logs in a prior Claude Code session. Treat as ground truth for presets.

## Mixer
Midas MR18 (fw 1.18/1.21), X-Air OSC UDP 10024, 6 pre-fader monitor buses. USB multitrack recorded into Studio One 7.
Rule from user: never touch preamp gain.

## Channel list (final)
1 Kick — EQ, comp, a little reverb; avoid feedback; meter for high volume. User rule: don't high/low-cut kick or bass lows.
2 Snare — a little less than kick; EQ, comp, a little reverb.
3 Overheads — mostly disconnected; when on, very low (~-35 dB) because loud in room.
4 DI 1 — acoustic guitar DI (earlier "bass mic", mostly unused).
5 Guitar AMP — solo guitar (some rhythm); EQ, comp, a little reverb.
6+7 Piano stereo — classic piano / Rhodes / pads; EQ, comp, rich, sit in low-mids behind the singer; grouped; never low, soft at all times.
8 Guitar DI / GT Board — second electric guitar; EQ, comp.
9 Vocal Centre — main singer; good amount of reverb, EQ, comp; detect male vs female.
10 Vocal Piano — second/back singer; EQ, comp, reverb. 9 and 10 ALWAYS vocals.
11 Congas mic 1 — sometimes 3rd singer or guest soloist (e.g., trombone).
12 Bass DI — hand in hand with kick; impressive but not overshadowing.
13 Congas mic 2.
14 DI 2 — synth bass (sub + bass); impressive but not overshadowing. 12 & 14 are the only bass channels.
15 Saxophone (sometimes flute) — wireless lav; clear, reverb, EQ, comp.
16 Harmonica (sometimes BV) — can be very sharp, soften; EQ, comp, short room reverb; sits mid (~-30 dB relative per user).

## Level rules from the user
Lock kick/snare/OH/vocals once balanced; bass moves only if clearly over/under; piano & guitar at medium; vocals on top.
Mac test-rig balance the user built: Vox Centre -2.0, Vox Piano -2.3, Sax -2.1, Kick -10, Harmonica -10, Piano ~-10, DI2 -9.8, Snare -14.9, OH -23.4 (fader dB).

## Prior app's final starting chains (conservative, cuts only, no makeup/boosts — FOH feedback-driven)
Kick flat; Bass no HPF, 350 Hz -2.5 Q1.1, 3 kHz -2.5 Q1.1, comp -18 dB 3:1 30/150 ms; Snare/OH HPF 40, comp -12 2:1 40/120;
Congas HPF 80; Vocal HPF 100, 300 Hz -3 Q1.5, 3 kHz -2 Q1.1, comp -20 3:1 20/150; BV HPF 120; Keys no HPF, 350/3k cuts + 4.5 kHz -2 Q0.8, comp -22 2:1 30/200;
Sax/harmonica/flute HPF 120, comp -18 3:1 20/150; Solo gtr HPF 100 comp -18 3:1; Rhythm gtr HPF 120 comp -20 3:1 25/180.
Feedback rings observed in room: 129, 160, 196, 226, 3377 Hz (FOH only — a broadcast mix off the USB feed has no feedback loop, so boosts/makeup are allowed there).

## Venue
Open-stage bar in Thailand (Samui/Koh Phangan area). Neo-Soul/Funk, rotating musicians, guest soloists.
