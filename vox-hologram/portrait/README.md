# Give VOX a face

VOX composites a portrait photo under its holographic shader and drives the mouth
from the live audio of each reply. This folder is just documentation — **the image
itself does not live here.**

## Where the image goes

Drop your photo at:

```
web/assets/portrait.png
```

(relative to the VOX repo root). JPG and WEBP also work:
`portrait.jpg`, `portrait.jpeg`, `portrait.webp`. Reload the browser tab after
adding or changing it.

> No portrait? VOX ships a built-in stylized placeholder face, so the app still
> runs on first launch. Add your own whenever you like.

## What makes a good hologram portrait

The effect is a flickering, semi-transparent, cyan-tinted "projection" of your
face. It looks best when the source photo is clean and centered:

- **Square-ish crop**, face centered, filling most of the frame
  (head-and-shoulders). Very wide or very tall images get cropped oddly.
- **Front-facing**, looking roughly at the camera. Profiles look strange when lit
  as a hologram.
- **Even, bright lighting.** Soft, flat light beats dramatic shadows — the shader
  adds its own glow and scanlines.
- **Plain / dark background** if you can. Busy backgrounds also get the hologram
  treatment and clutter the projection. A cleanly cut-out subject on transparent
  PNG looks fantastic.
- **Neutral or gently smiling expression** with the mouth closed reads best,
  since the app animates mouth openness itself.
- **Decent resolution** (roughly 512×512 or larger) so it stays crisp.

## Quick crops

macOS Preview can do everything you need:

1. Open the photo in **Preview**.
2. **Tools → Rectangular Selection**, drag a square around the face.
3. **Tools → Crop** (⌘K).
4. **File → Export**, choose **PNG**, save as `portrait.png` into
   `web/assets/`.

For a transparent cut-out, use the built-in subject lift: open in Preview, click
the **Instant Alpha** / **background removal** tool (or on newer macOS, right-click
the subject → *Copy Subject*), then export as PNG.

## Privacy

Everything stays on your machine. The portrait is served only by your local VOX
server to your own browser and is never uploaded anywhere. It is *your* face and
*your* project.
