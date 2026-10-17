"""Phone cameras from LiveKit (room 'show', participants 'cam-<id>').

Joins as a hidden subscriber 'vn-video', decodes every camera track to I420 and hands
frames to the program router. Cameras that are not needed right now are asked for their
lowest simulcast layer (when the phone publishes simulcast) so only the on-air /
vertical cameras arrive at full resolution.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

from livekit import api, rtc

log = logging.getLogger('vn_video.cams')


class Cam:
    def __init__(self, cam_id: int, identity: str):
        self.id, self.identity = cam_id, identity
        self.width = self.height = 0
        self.rotation = 0
        self.frames = 0
        self.fps = 0.0
        self._n0, self._t0 = 0, time.time()
        self.last_frame_t = 0.0
        self.last_frame: rtc.VideoFrame | None = None
        self.publication: rtc.RemoteTrackPublication | None = None
        self.quality = None
        self.task: asyncio.Task | None = None

    def info(self) -> dict:
        return {'id': self.id, 'identity': self.identity, 'width': self.width, 'height': self.height,
                'fps': round(self.fps, 1), 'rotation': self.rotation,
                'lastFrameAgeMs': round((time.time() - self.last_frame_t) * 1000) if self.last_frame_t else None,
                'quality': {0: 'low', 1: 'medium', 2: 'high'}.get(self.quality) if self.quality is not None else None,
                'simulcast': bool(self.publication and self.publication.simulcasted)}


class Cams:
    def __init__(self, url: str, key: str, secret: str, room: str, on_frame):
        self.url, self.key, self.secret, self.room_name = url, key, secret, room
        self.on_frame = on_frame          # (cam_id, rtc.VideoFrame) on the event loop
        self.cams: dict[int, Cam] = {}
        self.room: rtc.Room | None = None
        self.state = 'idle'
        self.error: str | None = None
        self.wanted: set[int] = set()     # cameras that should be at full resolution

    # ---------- connection ----------
    async def _ensure_room(self):
        http = self.url.replace('ws', 'http', 1)
        lk = api.LiveKitAPI(http, self.key, self.secret)
        try:
            rooms = await lk.room.list_rooms(api.ListRoomsRequest(names=[self.room_name]))
            if not rooms.rooms:
                await lk.room.create_room(api.CreateRoomRequest(name=self.room_name, empty_timeout=12 * 3600, max_participants=20))
        finally:
            await lk.aclose()

    def _token(self) -> str:
        return (api.AccessToken(self.key, self.secret)
                .with_identity('vn-video').with_name('VibeNation program')
                .with_grants(api.VideoGrants(room_join=True, room=self.room_name, can_subscribe=True,
                                             can_publish=False, can_publish_data=False, hidden=True))
                .to_jwt())

    async def run(self):
        while True:
            if not self.key or not self.secret:
                self.state, self.error = 'off', 'LIVEKIT_API_KEY / LIVEKIT_API_SECRET not set'
                await asyncio.sleep(30)
                continue
            try:
                self.state = 'connecting'
                await self._ensure_room()
                room = rtc.Room()
                gone = asyncio.Event()
                room.on('track_subscribed', self._subscribed)
                room.on('track_unsubscribed', self._unsubscribed)
                room.on('track_published', self._published)
                room.on('participant_disconnected', lambda p: self._drop(p.identity))
                room.on('disconnected', lambda *_: gone.set())
                await room.connect(self.url, self._token(), rtc.RoomOptions(auto_subscribe=True))
                self.room, self.state, self.error = room, 'connected', None
                log.info('LiveKit: joined %s', self.room_name)
                for p in room.remote_participants.values():
                    for pub in p.track_publications.values():
                        if pub.kind == rtc.TrackKind.KIND_AUDIO:
                            pub.set_subscribed(False)
                await gone.wait()
                log.warning('LiveKit: disconnected')
            except Exception as e:  # noqa: BLE001
                self.error = str(e) or type(e).__name__
                log.warning('LiveKit: %s', self.error)
            self.state, self.room = 'reconnecting', None
            for c in list(self.cams.values()):
                self._drop(c.identity)
            await asyncio.sleep(3)

    # ---------- tracks ----------
    @staticmethod
    def _cam_id(identity: str) -> int | None:
        if identity.startswith('cam-'):
            try:
                return int(identity[4:])
            except ValueError:
                return None
        return None

    def _published(self, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if pub.kind == rtc.TrackKind.KIND_AUDIO:
            pub.set_subscribed(False)

    def _subscribed(self, track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        cid = self._cam_id(participant.identity)
        if cid is None or track.kind != rtc.TrackKind.KIND_VIDEO:
            return
        old = self.cams.get(cid)
        if old and old.task:
            old.task.cancel()
        cam = Cam(cid, participant.identity)
        cam.publication = pub
        self.cams[cid] = cam
        cam.task = asyncio.ensure_future(self._read(cam, track))
        self.apply_quality()
        log.info('camera %s subscribed (%sx%s, simulcast=%s)', cid, pub.width, pub.height, pub.simulcasted)

    def _unsubscribed(self, track, pub, participant):
        cid = self._cam_id(participant.identity)
        if cid is not None and cid in self.cams and self.cams[cid].publication is pub:
            self._drop(participant.identity)

    def _drop(self, identity: str):
        cid = self._cam_id(identity)
        cam = self.cams.pop(cid, None) if cid is not None else None
        if cam and cam.task:
            cam.task.cancel()

    async def _read(self, cam: Cam, track: rtc.Track):
        stream = rtc.VideoStream(track, capacity=2, format=rtc.VideoBufferType.I420)
        try:
            async for ev in stream:
                f = ev.frame
                now = time.time()
                cam.frames += 1
                cam.width, cam.height, cam.rotation = f.width, f.height, int(ev.rotation)
                cam.last_frame, cam.last_frame_t = f, now
                if now - cam._t0 >= 1.0:
                    cam.fps = (cam.frames - cam._n0) / (now - cam._t0)
                    cam._n0, cam._t0 = cam.frames, now
                self.on_frame(cam.id, f)
        except asyncio.CancelledError:
            pass
        finally:
            await stream.aclose()

    def apply_quality(self):
        """Full resolution for the cameras in use; lowest layer for the rest — unless VN_VIDEO_ALL_HIGH
        (default on): then every camera stays at full resolution, so a cut is sharp from its first frame
        (no layer switch on air). The c-16 show server has the headroom (measured 17 Oct 2026)."""
        all_high = os.environ.get('VN_VIDEO_ALL_HIGH', '1') == '1'
        for cam in self.cams.values():
            q = rtc.VideoQuality.VIDEO_QUALITY_HIGH if all_high or cam.id in self.wanted else rtc.VideoQuality.VIDEO_QUALITY_LOW
            if cam.publication and cam.quality != q:
                try:
                    cam.publication.set_video_quality(q)
                    cam.quality = q
                except Exception:  # noqa: BLE001
                    pass

    def info(self) -> dict:
        return {'state': self.state, 'error': self.error, 'cams': [c.info() for c in sorted(self.cams.values(), key=lambda c: c.id)]}
