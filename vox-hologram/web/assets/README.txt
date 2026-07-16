VOX — your hologram face goes here
==================================

Drop a photo in THIS folder named exactly:

    portrait.png

That's it. Reload VOX in your browser and the face becomes your portrait,
projected as a glowing cyan hologram that speaks and lip-syncs to Vox's voice.

Full-body figure or head-shot? (set VOX_FACE_BOX to match)
----------------------------------------------------------
VOX v2 projects a full-body standing Vox on a pedestal, but either kind of photo
works -- you just tell VOX where the head is with the VOX_FACE_BOX environment
variable (a normalized x,y,w,h box, values 0..1) so the lip-sync/blink land on
the face:

* FULL-BODY photo (the v2 look): full figure on a plain/dark background, head
  near the TOP-CENTER of the frame. Keep the DEFAULT VOX_FACE_BOX -- it already
  expects the head at the top of a full-body portrait.
      ./run.sh

* HEAD-AND-SHOULDERS photo: a square-ish bust filling the frame. Run with
  VOX_FACE_BOX=0,0,1,1 so the whole image is treated as the face.
      VOX_FACE_BOX=0,0,1,1 ./run.sh

Either way the file is the same: web/assets/portrait.png.

Tips for the best hologram
--------------------------
* Match the framing to your VOX_FACE_BOX (full body with head at top-center, or
  a centered head-and-shoulders crop). The lip-sync region follows the face box.
* Plain / dark backgrounds look great: dark areas of the image become
  transparent, which is what gives the "translucent ghost" hologram effect.
* Bright, evenly-lit faces glow the most.
* PNG or JPG both work if you name it portrait.png. Square-ish or 3:4 (portrait
  orientation) framing fills the projector nicely. Very large images are fine
  but ~800-1200px is plenty and loads faster on older machines.

No portrait yet?
----------------
No problem. If portrait.png is missing, VOX shows a built-in stylized
standing-figure placeholder so the app still looks good on first launch. This
placeholder is a generic silhouette -- it does not depict any real person.

Privacy
-------
This image never leaves your Mac. The portrait is served only by your own local
server and rendered entirely in your browser -- it is never uploaded anywhere.
(The optional v2 web layer searches and fetches PUBLIC web pages to ground Vox's
answers; it never sends your photo. And the LLM itself always stays local.)
