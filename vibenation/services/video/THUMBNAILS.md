# YouTube thumbnails

Made from a real frame of the show by `vn_video/thumbs.py`. Faces are never AI-edited.
The finish comes from the band's poster style (the R604 reference); the poster template itself (headline system, logo, schedule block, characters, scene rebuilding) is deliberately not used.

## What makes a live-music thumbnail get clicked
1. **One real moment:** the singer mid-note, or a player lost in it. Candidate frames are scored on face size, sharpness (no motion blur) and exposure; the best one wins.
2. **Tight crop:** the performer fills the frame, face about 20% of the height, eyes on the upper third, on the side with more room. Other band members stay in when they fit.
3. **Instrument or mic in shot:** signals "live music" instantly.
4. **Depth:** the performer bright and crisp; the background darker and less saturated. No fake blur.
5. **Warm finish (R604):** brown-black shadows, olive mids, golden highlights, cream tops, fine grain. Real skin texture, no beauty smoothing, no orange filter. Tuned for punch at phone size.
6. **YouTube spec:** 1280×720 JPEG under 2 MB. Nothing important bottom-right (YouTube's duration/LIVE badge).

## Rules
- No logo, no venue name, no location, ever.
- Text is optional and off by default. If used: 1–3 words, huge, heavy condensed caps (Anton), cream `#F0EADE`, top-left.
- Guests are named only in the title and description, never in the picture.
- Claude checks the chosen frame before it is uploaded (eyes open, no awkward mouth, nothing embarrassing). It can be replaced on the Go Live screen.
