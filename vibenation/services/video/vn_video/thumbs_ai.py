"""AI YouTube thumbnails: tonight's guest performers (from their approved character sheets) on the
venue's real stage, in the proven live-cover style. See ../THUMBNAILS.md.

References live OUTSIDE the repo (real faces + the venue): $VN_THUMB_REFS, default
/home/vibe/vibenation-media/thumbnail-refs/{performers/<name>/*.jpg, stage/*.jpg, finish/R604.jpg}.
Needs OPENAI_API_KEY (Keys screen). Costs money per image: the caller states the cost first.

One character per thumbnail: the hero from their sheets; the band behind is anonymous.

CLI: python -m vn_video.thumbs_ai --performer jesse [--frame live.jpg] [--n 2] --out DIR
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
# Best first; the first one this key can use wins (VN_THUMB_MODEL forces one).
MODELS = ['gpt-image-2.5-sunburst', 'gpt-image-2.5-flare', 'gpt-image-2', 'gpt-image-1.5', 'gpt-image-1']  # 2.5-sunburst chosen 17 Oct 2026 (side-by-side test)
GEN_SIZE = '1536x1024'
# gpt-image-1 list prices (USD per 1M tokens), used as an estimate for newer models; shown as "about".
# Measured 17 Oct 2026: 2.5-sunburst ≈ $0.16 per 3-person image, gpt-image-2 ≈ $0.32.
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
{frame}
PLACE — must be this venue's actual stage, from the attached stage photos: the large semicircular geometric lattice backdrop glowing teal-green, raw grey concrete walls, the bamboo-stick ceiling and black steel truss, wooden stage floor. Show the lattice backdrop partly, softly out of focus behind the performers; it must be recognisably this stage, not a generic one. Use the stage photos for the room and stage only: the people in them are strangers and must NOT appear or be copied (no similar faces, heads, beards, clothes or poses). No crowd, no bar, no drinks, no extra props.

LOOK — warm, bright stage light on the faces with soft falloff; shallow depth of field; natural, textured skin with pores and imperfections (no beauty smoothing, no waxy AI skin); believable hands, fingers and instrument grips. Colour finish like the attached R604 reference photo: deep warm brown-black shadows, soft golden highlights, restrained saturation, fine film grain. Use R604 for colour and tone only — do not add its drink, flowers or glass.

FRAME — landscape. Keep the lower-right corner free of faces (YouTube puts a badge there). Absolutely no text, letters, logos, signs or words anywhere in the image."""


def performer_refs(name: str) -> list[str]:
    files = sorted(glob.glob(os.path.join(REFS, 'performers', name.lower(), '*.jpg')))
    if not files:
        raise SystemExit(f'No character sheets for "{name}" in {REFS}/performers/{name.lower()}/')
    return files


BAND = (' Behind them, the rest of the band (bass, electric guitar, keys, drums) plays in soft focus: anonymous ordinary '
        'musicians, smaller in frame, faces soft or partly turned away. They must not resemble the person in the identity '
        'references or anyone else; there is only one recognisable person in the image.')


def build(performer: str, frame: str | None) -> tuple[str, list[str]]:
    files = performer_refs(performer)
    refs = ' and '.join(f'image {i}' for i in range(1, len(files) + 1))
    binding = PERFORMER_BINDING.format(refs=refs, name=performer.capitalize())
    stage = sorted(glob.glob(os.path.join(REFS, 'stage', '*.jpg')))
    files += stage
    files.append(os.path.join(REFS, 'finish', 'R604.jpg'))
    frame_txt = ''
    if frame:
        files.append(frame)
        frame_txt = (f'\nTONIGHT — image {len(files)} is a real frame from tonight\'s show: match the featured performer\'s outfit, '
                     'hair and instrument from it, but not its framing or lighting.\n')
    return PROMPT.format(binding=binding, lead=performer.capitalize(), others=BAND, frame=frame_txt), files


async def pick_model(s: aiohttp.ClientSession) -> str:
    if os.environ.get('VN_THUMB_MODEL'):
        return os.environ['VN_THUMB_MODEL']
    async with s.get(f'{API}/models') as r:
        have = {m['id'] for m in (await r.json()).get('data', [])} if r.ok else set()
    return next((m for m in MODELS if m in have), MODELS[-1])


async def generate(prompt: str, files: list[str], n: int) -> tuple[list[bytes], str, dict]:
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('OPENAI_API_KEY is not set (add it on the Keys screen).')
    async with aiohttp.ClientSession(headers={'Authorization': f'Bearer {key}'}, timeout=aiohttp.ClientTimeout(total=600)) as s:
        model = await pick_model(s)
        for fidelity in (True, False):  # input_fidelity keeps faces closer; not every model accepts it
            form = aiohttp.FormData()
            for k, v in (('model', model), ('prompt', prompt), ('size', GEN_SIZE), ('quality', 'high'), ('n', str(n))):
                form.add_field(k, v)
            if fidelity:
                form.add_field('input_fidelity', 'high')
            for f in files:
                form.add_field('image[]', open(f, 'rb').read(), filename=os.path.basename(f), content_type='image/jpeg')
            async with s.post(f'{API}/images/edits', data=form) as r:
                j = await r.json()
            if r.ok:
                return [base64.b64decode(d['b64_json']) for d in j['data']], model, j.get('usage', {})
            msg = j.get('error', {}).get('message', str(r.status))
            if not (fidelity and 'input_fidelity' in msg):
                raise SystemExit(f'OpenAI image edit failed ({model}): {msg}')
    raise SystemExit('unreachable')


def finish(png: bytes) -> bytes:
    """1536x1024 -> 1280x720 JPEG < 2 MB, cropping vertically to keep the faces."""
    im = Image.open(io.BytesIO(png)).convert('RGB')
    w, h = im.size
    ch = round(w * 9 / 16)
    fs = faces(np.asarray(im))
    if not fs:
        raise ValueError('no clear face in the generated image')
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
    a.add_argument('--n', type=int, default=2)
    a.add_argument('--out', required=True)
    a.add_argument('--dry-run', action='store_true', help='print the prompt and inputs, spend nothing')
    args = a.parse_args()
    prompt, files = build(args.performer.strip(), args.frame)
    if args.dry_run:
        print(prompt)
        print('\ninputs:', *[f'  image {i + 1}: {os.path.relpath(f, REFS) if f.startswith(REFS) else f}' for i, f in enumerate(files)], sep='\n')
        return
    images, model, usage = asyncio.run(generate(prompt, files, args.n))
    os.makedirs(args.out, exist_ok=True)
    out = []
    for i, png in enumerate(images):
        base = os.path.join(args.out, f'thumb-{i + 1}')
        open(base + '-raw.png', 'wb').write(png)
        try:
            open(base + '.jpg', 'wb').write(finish(png))
            out.append(base + '.jpg')
        except ValueError as e:
            print(f'candidate {i + 1} rejected: {e}', file=sys.stderr)
    print(json.dumps({'files': out, 'model': model, 'usage': usage, 'est_usd': est_usd(usage)}))


if __name__ == '__main__':
    main()
