// One subscribe-only LiveKit connection per tab, opened when the show has real phone
// cameras. Exposes each phone's video track by participant identity ("cam-<id>").

import { useEffect, useSyncExternalStore } from 'react';
import { Room, RoomEvent, Track, VideoQuality, type RemoteTrackPublication, type RemoteVideoTrack } from 'livekit-client';

let room: Room | null = null;
let connecting = false;
let wanted = false;
let retry = 0;
let tracks = new Map<string, { track: RemoteVideoTrack; pub: RemoteTrackPublication }>();
let highId: string | undefined;
const subs = new Set<() => void>();
const emit = () => subs.forEach((f) => f());

function rebuild() {
  const next = new Map<string, { track: RemoteVideoTrack; pub: RemoteTrackPublication }>();
  room?.remoteParticipants.forEach((p) => {
    p.trackPublications.forEach((pub) => {
      if (pub.kind === Track.Kind.Video && pub.track) next.set(p.identity, { track: pub.track as RemoteVideoTrack, pub: pub as RemoteTrackPublication });
    });
  });
  tracks = next;
  applyQuality();
  emit();
}

/** The on-air camera gets the full layer; tiles get the small simulcast layer. */
function applyQuality() {
  tracks.forEach(({ pub }, id) => pub.setVideoQuality(id === highId ? VideoQuality.HIGH : VideoQuality.LOW));
}

async function open() {
  if (connecting || room || !wanted) return;
  connecting = true;
  try {
    const r = await fetch('/api/cams/viewer-token');
    if (!r.ok) throw new Error(`viewer token ${r.status}`);
    const { url, token } = (await r.json()) as { url: string; token: string };
    const rm = new Room({ adaptiveStream: false, dynacast: false });
    rm.on(RoomEvent.TrackSubscribed, rebuild)
      .on(RoomEvent.TrackUnsubscribed, rebuild)
      .on(RoomEvent.ParticipantDisconnected, rebuild)
      .on(RoomEvent.TrackMuted, rebuild)
      .on(RoomEvent.TrackUnmuted, rebuild)
      .on(RoomEvent.TrackSubscriptionFailed, (sid, p, reason) => console.warn('camera video subscription failed', p?.identity, sid, reason))
      .on(RoomEvent.Disconnected, () => {
        if (room !== rm) return;
        room = null;
        tracks = new Map();
        emit();
        if (wanted) setTimeout(() => void open(), 3000);
      });
    await rm.connect(url, token, { autoSubscribe: true });
    room = rm;
    retry = 0;
    rebuild();
  } catch {
    retry = Math.min(retry + 1, 6);
    if (wanted) setTimeout(() => void open(), 1000 * 2 ** retry);
  } finally {
    connecting = false;
  }
}

/** Connect while `needed` is true; `liveIdentity` gets the high-quality layer. */
export function useLiveVideo(needed: boolean, liveIdentity: string | undefined) {
  useEffect(() => {
    wanted = needed;
    if (needed) void open();
    else if (room) { const r = room; room = null; tracks = new Map(); emit(); void r.disconnect(); }
  }, [needed]);
  useEffect(() => {
    highId = liveIdentity;
    applyQuality();
  }, [liveIdentity]);
}

export function useCamTrack(identity: string | undefined): RemoteVideoTrack | undefined {
  return useSyncExternalStore(
    (f) => { subs.add(f); return () => { subs.delete(f); }; },
    () => (identity ? tracks.get(identity)?.track : undefined),
  );
}
