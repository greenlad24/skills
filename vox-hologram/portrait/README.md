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

> No portrait? VOX ships a built-in stylized standing-figure placeholder, so the
> app still runs on first launch. Add your own whenever you like.

## Full-body figure or head-and-shoulders? (set `VOX_FACE_BOX` to match)

VOX v2 projects a **full-body standing Vox** on a pedestal, but it works with either
kind of photo — you just tell VOX where the head is via the `VOX_FACE_BOX`
environment variable (a normalized `x,y,w,h` box, 0..1) so lip-sync and blinking land
on the face:

- **Full-body photo** — full figure on a plain/dark background, head near the
  **top-center** of the frame. **Keep the default `VOX_FACE_BOX`**; it already expects
  the head at the top of a full-body portrait. This is the intended v2 look.
- **Head-and-shoulders photo** — a square-ish bust that fills the frame. Run VOX with
  **`VOX_FACE_BOX=0,0,1,1`** so the whole image is treated as the face.

Either way the file lives at the same path, `web/assets/portrait.png`.

## What makes a good hologram portrait

The effect is a flickering, semi-transparent, cyan-tinted "projection" of your
face. It looks best when the source photo is clean and centered:

- **Framing to match your `VOX_FACE_BOX`:** a full-body figure with the head near
  the top-center (default box), or a square-ish head-and-shoulders crop filling the
  frame (`VOX_FACE_BOX=0,0,1,1`). Very wide images get cropped oddly.
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
