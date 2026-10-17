"""Test publisher: N fake phone cameras into the LiveKit 'show' room as cam-1..cam-N.

Each camera is a solid colour with its number and a moving bar, so cuts and crops are
easy to see in grabbed frames. Small and slow on purpose (build-server friendly).

  .venv/bin/python tools/fake_cams.py --cams 3 --size 640x360 --fps 15
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import numpy as np
from livekit import api, rtc
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from vn_video.graphics import FONTS  # noqa: E402

COLOURS = [(200, 40, 40), (40, 160, 60), (40, 80, 200), (200, 160, 30), (150, 50, 170)]


def base_image(n: int, w: int, h: int) -> np.ndarray:
    img = Image.new('RGBA', (w, h), COLOURS[(n - 1) % len(COLOURS)] + (255,))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(FONTS / 'sora.ttf'), h // 3)
    d.text((w / 2, h / 2), f'CAM {n}', font=f, fill=(255, 255, 255, 255), anchor='mm')
    # Quarter ticks so a 9:16 crop position is visible.
    for i in range(1, 4):
        d.line((w * i / 4, 0, w * i / 4, h // 10), fill=(255, 255, 255, 255), width=3)
    return np.asarray(img).copy()


async def cam(n: int, url: str, key: str, secret: str, room_name: str, w: int, h: int, fps: int):
    token = (api.AccessToken(key, secret).with_identity(f'cam-{n}').with_name(f'CAM {n} · test')
             .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=False)).to_jwt())
    room = rtc.Room()
    await room.connect(url, token)
    src = rtc.VideoSource(w, h)
    track = rtc.LocalVideoTrack.create_video_track(f'cam-{n}', src)
    opts = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA, simulcast=False,
                                   video_encoding=rtc.VideoEncoding(max_framerate=fps, max_bitrate=800_000))
    await room.local_participant.publish_track(track, opts)
    print(f'cam-{n} publishing {w}x{h}@{fps}', flush=True)
    base = base_image(n, w, h)
    bar = max(4, w // 40)
    i = 0
    while True:
        frame = base.copy()
        x = (i * 6) % (w - bar)
        frame[h - h // 8:, x:x + bar] = (255, 255, 255, 255)
        src.capture_frame(rtc.VideoFrame(w, h, rtc.VideoBufferType.RGBA, frame.tobytes()))
        i += 1
        await asyncio.sleep(1 / fps)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cams', type=int, default=3)
    ap.add_argument('--size', default='640x360')
    ap.add_argument('--fps', type=int, default=15)
    ap.add_argument('--room', default=os.environ.get('VN_VIDEO_ROOM', 'show'),
                    help="LiveKit room (use a test room on a machine where real phones may be in 'show')")
    a = ap.parse_args()
    w, h = map(int, a.size.split('x'))
    url = os.environ.get('LIVEKIT_URL', 'ws://127.0.0.1:7880')
    key, secret = os.environ['LIVEKIT_API_KEY'], os.environ['LIVEKIT_API_SECRET']
    lk = api.LiveKitAPI(url.replace('ws', 'http', 1), key, secret)
    if not (await lk.room.list_rooms(api.ListRoomsRequest(names=[a.room]))).rooms:
        await lk.room.create_room(api.CreateRoomRequest(name=a.room, empty_timeout=12 * 3600, max_participants=20))
    await lk.aclose()
    await asyncio.gather(*(cam(n, url, key, secret, a.room, w, h, a.fps) for n in range(1, a.cams + 1)))


if __name__ == '__main__':
    asyncio.run(main())
