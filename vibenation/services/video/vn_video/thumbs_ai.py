"""AI YouTube thumbnails: tonight's guest performers (from their approved character sheets) on the
venue's real stage, in the proven live-cover style. See ../THUMBNAILS.md.

References live OUTSIDE the repo (real faces + the venue): $VN_THUMB_REFS, default
/home/vibe/vibenation-media/thumbnail-refs/{performers/<name>/*.jpg, stage/*.jpg, finish/R604.jpg}.
Needs OPENAI_API_KEY (Keys screen). Costs money per image: the caller states the cost first.

One character per thumbnail: the hero from their sheets; the band behind is anonymous.

The framing copies a viral reference thumbnail exactly (--layout: an id from layouts/index.json or a path).

CLI: python -m vn_video.thumbs_ai --performer jesse --layout XYeuvbhKy4I [--frame live.jpg] [--n 2] --out DIR
Prints JSON: {"files": [...], "model": ..., "usage": {...}, "est_usd": ...}
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import glob
import io
import json
import os
import sys

import aiohttp
import numpy as np
from PIL import Image

from .thumbs import H, MAX_BYTES, W, faces

REFS = os.environ.get('VN_THUMB_REFS', '/home/vibe/vibenation-media/thumbnail-refs')
API = 'https://api.openai.com/v1'
MODEL = os.environ.get('VN_THUMB_MODEL', 'gpt-image-2')  # the user's default (17 Oct 2026)
# gpt-image-1 list prices (USD per 1M tokens), used as an estimate for newer models; shown as "about".
# Measured 17 Oct 2026: gpt-image-2 ≈ $0.28 per image.
PRICE = {'text_in': 5.0, 'image_in': 10.0, 'out': 40.0}

PERFORMER_BINDING = (
    'Use the attached {refs} as the exact identity references for {name}. Preserve this person\'s facial likeness, '
    'age, hair and distinguishing features. Do not invent a replacement face, blend different appearances into a new '
    'identity, or assign this likeness to another subject.'
)

PROMPT = """A real candid photograph of a live funk & soul band performing, for a YouTube thumbnail.

PEOPLE
{binding}
{lead} is the only main subject and the hero: singing mid-belt into a vocal microphone, mouth open, eyes closed or intensely engaged, head and shoulders large in frame (head about a third of the image height), placed on the left or right third. The microphone is close to the face in the foreground.{others}
{frame}{layout}
PLACE — everyone is ON the stage, performing: standing or seated on the raised wooden stage platform, with the lattice backdrop directly behind them. Never in the audience area, the lounge, at the bar or outdoors. It must be this venue's actual stage, from the attached empty stage plate: the large semicircular geometric lattice backdrop glowing teal-green, raw grey concrete walls, the bamboo-stick ceiling and black steel truss, wooden stage floor. Show the lattice backdrop partly, softly out of focus behind the performers; it must be recognisably this stage, not a generic one. No crowd, no bar, no drinks, no extra props.

LOOK — warm, bright stage light on the faces with soft falloff; shallow depth of field; natural, textured skin with pores and imperfections (no beauty smoothing, no waxy AI skin); believable hands, fingers and instrument grips. Colour finish like the attached R604 reference photo: deep warm brown-black shadows, soft golden highlights, restrained saturation, fine film grain. Use R604 for colour and tone only — do not add its drink, flowers or glass.

FRAME — landscape.{badge} Absolutely no text, letters, logos, signs or words anywhere in the image."""


LAYOUT = """
LAYOUT — image 1 is the image to edit: a proven viral thumbnail. Keep its framing EXACTLY inside the middle band between its grey bars:
same camera angle, lens and distance, same crop, and every element in the same position and at the same size —
the hero's head, eyes, shoulders and hands, the microphone and stand, instruments, background players, lights and
empty space. Fill the grey bars above and below by extending the scene naturally (no bars in the result).
Replace its singer with {lead} from the identity references, its room with this venue's empty stage plate, and its other
people with anonymous musicians. Keep nothing else from it: not its faces, clothes, colours, room or text. Where this layout differs from the composition notes above,
the layout wins.
"""
LAYOUTS = os.path.join(REFS, 'layouts')
GEN_W, GEN_H = 1536, 1024
BAND_H = round(GEN_W * 9 / 16)          # 864: the 16:9 band inside the 3:2 image
BAND_Y = (GEN_H - BAND_H) // 2          # 80


def layout_input(layout: str, tmp: str) -> str:
    """The reference, letterboxed into the 3:2 canvas so the middle band maps 1:1 back to 16:9."""
    path = layout if os.path.exists(layout) else os.path.join(LAYOUTS, f'{layout}.jpg')
    if not os.path.exists(path):
        raise SystemExit(f'No layout reference "{layout}" (ids: {LAYOUTS}/index.json)')
    ref = Image.open(path).convert('RGB').resize((GEN_W, BAND_H), Image.LANCZOS)
    canvas = Image.new('RGB', (GEN_W, GEN_H), (128, 128, 128))
    canvas.paste(ref, (0, BAND_Y))
    out = os.path.join(tmp, 'layout-letterboxed.jpg')
    canvas.save(out, quality=92)
    return out


def performer_refs(name: str) -> list[str]:
    files = sorted(glob.glob(os.path.join(REFS, 'performers', name.lower(), '*.jpg')))
    if not files:
        raise SystemExit(f'No character sheets for "{name}" in {REFS}/performers/{name.lower()}/')
    return files


BAND = (' Behind them, the rest of the band (bass, electric guitar, keys, drums) plays in soft focus: anonymous ordinary '
        'musicians, smaller in frame, faces soft or partly turned away. They must not resemble the person in the identity '
        'references or anyone else; there is only one recognisable person in the image.')


def build(performer: str, frame: str | None, layout: str | None = None) -> tuple[str, list[str]]:
    """Inputs in order: [layout to edit], identity sheets, empty stage plate, R604 finish, [tonight's frame]."""
    files = [layout] if layout else []
    sheets = performer_refs(performer)
    first = len(files) + 1
    files += sheets
    refs = ' and '.join(f'image {i}' for i in range(first, first + len(sheets)))
    binding = PERFORMER_BINDING.format(refs=refs, name=performer.capitalize())
    # Only people-free stage references: the stage photos had strangers on them, and models copied them.
    files += sorted(glob.glob(os.path.join(REFS, 'stage', 'plate-*.png')))
    files.append(os.path.join(REFS, 'finish', 'R604.jpg'))
    frame_txt = ''
    if frame:
        files.append(frame)
        frame_txt = (f'\nTONIGHT — image {len(files)} is a real frame from tonight\'s show: match the featured performer\'s outfit, '
                     'hair and instrument from it, but not its framing or lighting.\n')
    layout_txt, badge = '', ' Keep the lower-right corner free of faces (YouTube puts a badge there).'
    if layout:
        layout_txt, badge = LAYOUT.format(lead=performer.capitalize()), ''
    return PROMPT.format(binding=binding, lead=performer.capitalize(), others=BAND, frame=frame_txt,
                         layout=layout_txt, badge=badge), files


async def generate(prompt: str, files: list[str], n: int) -> tuple[list[bytes], str, dict]:
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('OPENAI_API_KEY is not set (add it on the Keys screen).')
    async with aiohttp.ClientSession(headers={'Authorization': f'Bearer {key}'}, timeout=aiohttp.ClientTimeout(total=600)) as s:
        model = MODEL
        form = aiohttp.FormData()
        for k, v in (('model', model), ('prompt', prompt), ('size', f'{GEN_W}x{GEN_H}'), ('quality', 'high'), ('n', str(n))):
            form.add_field(k, v)
        for f in files:
            ctype = 'image/png' if f.endswith('.png') else 'image/jpeg'
            form.add_field('image[]', open(f, 'rb').read(), filename=os.path.basename(f), content_type=ctype)
        async with s.post(f'{API}/images/edits', data=form) as r:
            j = await r.json()
        if not r.ok:
            raise SystemExit(f'OpenAI image edit failed ({model}): {j.get("error", {}).get("message", r.status)}')
        return [base64.b64decode(d['b64_json']) for d in j['data']], model, j.get('usage', {})


def finish(png: bytes, exact_band: bool) -> bytes:
    """1536x1024 -> 1280x720 JPEG < 2 MB. With a layout reference: exactly its 16:9 band (framing 1:1);
    otherwise crop vertically to keep the faces."""
    im = Image.open(io.BytesIO(png)).convert('RGB')
    w, h = im.size
    ch = round(w * 9 / 16)
    fs = faces(np.asarray(im))
    if not fs:
        raise ValueError('no clear face in the generated image')
    if exact_band:
        y0 = round((h - ch) / 2)
    else:
        top = min([f.y for f in fs[:3]])
        y0 = int(min(max(0, top - ch * 0.18), h - ch))  # heads near the top third, never cut
    out = im.crop((0, y0, w, y0 + ch)).resize((W, H), Image.LANCZOS)
    for q in (92, 88, 84, 80):
        buf = io.BytesIO()
        out.save(buf, 'JPEG', quality=q, optimize=True, progressive=True)
        if buf.tell() < MAX_BYTES:
            break
    return buf.getvalue()


def est_usd(u: dict) -> float:
    d = u.get('input_tokens_details', {})
    return round((d.get('text_tokens', 0) * PRICE['text_in'] + d.get('image_tokens', 0) * PRICE['image_in']
                  + u.get('output_tokens', 0) * PRICE['out']) / 1e6, 3)


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument('--performer', required=True, help='the one featured guest (e.g. jesse)')
    a.add_argument('--frame', help='a real frame from tonight (outfits, instruments)')
    a.add_argument('--layout', help='viral reference to copy the framing from: id in layouts/index.json, or a path')
    a.add_argument('--n', type=int, default=2)
    a.add_argument('--out', required=True)
    a.add_argument('--dry-run', action='store_true', help='print the prompt and inputs, spend nothing')
    args = a.parse_args()
    os.makedirs(args.out, exist_ok=True)
    layout = layout_input(args.layout, args.out) if args.layout else None
    prompt, files = build(args.performer.strip(), args.frame, layout)
    if args.dry_run:
        print(prompt)
        print('\ninputs:', *[f'  image {i + 1}: {os.path.relpath(f, REFS) if f.startswith(REFS) else f}' for i, f in enumerate(files)], sep='\n')
        return
    images, model, usage = asyncio.run(generate(prompt, files, args.n))
    out = []
    for i, png in enumerate(images):
        base = os.path.join(args.out, f'thumb-{i + 1}')
        open(base + '-raw.png', 'wb').write(png)
        try:
            open(base + '.jpg', 'wb').write(finish(png, exact_band=bool(layout)))
            out.append(base + '.jpg')
        except ValueError as e:
            print(f'candidate {i + 1} rejected: {e}', file=sys.stderr)
    print(json.dumps({'files': out, 'model': model, 'usage': usage, 'est_usd': est_usd(usage)}))


if __name__ == '__main__':
    main()
