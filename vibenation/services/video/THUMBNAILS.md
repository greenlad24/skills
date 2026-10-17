# YouTube thumbnails

Two generators, same look:
- **`vn_video/thumbs_ai.py` (main):** tonight's guest performers, drawn from their approved character sheets, on the venue's real stage (OpenAI image edit, paid per image).
- **`vn_video/thumbs.py` (fallback, free):** the best real frame from the show, cropped tight and graded. Used when no guest has a sheet, or there's no OpenAI key.

## Research: Scary Pockets (Oct 2026, 415 videos)
Their top 20 (4.5M–35M views) all follow the same formula:
- **No text and no logo on the thumbnail.** The title sells: a famous song, the original artist and "funk cover ft. [singer]". Song fame is the biggest driver.
- **The singer is the hero, mid-belt:** mouth open, eyes closed or intense, head large in frame.
- **A mic right in front of the face:** reads "live" instantly and adds foreground depth.
- **Warm, bright, natural light,** with the room readable but secondary.
- **Band members visible behind** in about half of them: a real band, not a solo act.

Their weakest covers (58k–106k) break it: gimmicks (text, split screens, costumes), flat purple or green backgrounds, letterbox bars, side-on faces.

## The brief (what both generators aim for)
1. **One hero performer** mid-song, emotion over glamour, head about ⅓ of the image height, on a third.
2. **A mic in the foreground; instruments and band behind** in softer focus.
3. **The venue's actual stage** (AI): the semicircular teal-green lattice backdrop, concrete walls, bamboo ceiling, partly visible and out of focus. Never a generic stage.
4. **The R604 finish:** warm brown-black shadows, golden highlights, restrained saturation, fine grain, real skin texture.
5. **YouTube spec:** 1280×720 JPEG under 2 MB; no faces in the bottom-right (badge).

## Rules
- No text, no logo, no venue name, no signs, no location, ever.
- Only approved performers are drawn from sheets: Jesse, Alyona (sheet name "aliona"), Greg (the usual Saturday guests). The lead singer is listed first. Never give a sheet's likeness to anyone else.
- **Stage reference = `stage/plate-empty-stage.png` only:** the venue's stage with every person and instrument removed (made once with gpt-image-2). The original stage photos had real strangers on them, and the models copied them.
- **Layout:** `--layout <id>` copies a viral thumbnail's framing exactly (`layouts/index.json`, Scary Pockets' top 20). The reference is image 1 (the image to edit), letterboxed into the 3:2 canvas, and its 16:9 band is cut back out 1:1.
- References stay off GitHub: `/home/vibe/vibenation-media/thumbnail-refs/` (mode 700) holds `performers/<name>/`, `stage/` (crops with no map, names or app UI) and `finish/R604.jpg`.
- Every AI image is reviewed before use: everyone is on the stage, lattice backdrop behind them (never the lounge, bar or crowd); likeness matches the sheets; hands, mics and instruments are physically right; the stage is recognisable; no text. A failed candidate is regenerated or dropped, never "fixed" with a filter. The user approves or swaps it on Go Live.
- Model: `gpt-image-2` by default (the user's choice); `VN_THUMB_MODEL=gpt-image-2.5-sunburst` for comparison tests. About $0.29 vs $0.13 per image. The cost is stated before generating.
