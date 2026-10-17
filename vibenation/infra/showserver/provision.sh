#!/usr/bin/env bash
# Runs ON the show server (pushed by showserver.py). Idempotent.
set -euo pipefail
cd /opt/vibenation
mkdir -p data
export DEBIAN_FRONTEND=noninteractive

# Pinned Python packages (services/*/requirements.txt) need Python 3.12 (Ubuntu 24.04). Fail fast otherwise.
. /etc/os-release
echo "OS: $PRETTY_NAME · $(python3 --version)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' || { echo "Needs Python 3.12+ (Ubuntu 24.04); this image has $(python3 --version)" >&2; exit 1; }

# Node 22 + pnpm
if ! command -v node >/dev/null || ! node -v | grep -q '^v22'; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null && apt-get install -y -qq nodejs >/dev/null
fi
corepack enable && corepack prepare pnpm@9.15.0 --activate >/dev/null
# mod-host (headless LV2 host)
if ! command -v mod-host >/dev/null; then
  rm -rf /tmp/mod-host && git clone -q --depth 1 https://github.com/moddevices/mod-host.git /tmp/mod-host
  # localhost only: mod-host's socket protocol has no auth
  sed -i 's/htonl(INADDR_ANY)/htonl(INADDR_LOOPBACK)/' /tmp/mod-host/src/socket.c
  make -C /tmp/mod-host -j"$(nproc)" >/dev/null && install -m755 /tmp/mod-host/mod-host /usr/local/bin/mod-host
fi
# LiveKit server
command -v livekit-server >/dev/null || (curl -sSL https://get.livekit.io | bash >/dev/null)

# App
pnpm install --frozen-lockfile >/dev/null
pnpm --filter @vibenation/web build >/dev/null
python3 -m venv services/audio/.venv
services/audio/.venv/bin/pip install -q -r services/audio/requirements.txt

# Services (same units as the build server)
for u in vibenation-jack vibenation-audio vibenation vibenation-livekit; do
  # runs as root there (no vibe user on the show server)
  sed -e 's#/home/vibe/vibenation/vibenation#/opt/vibenation#g' -e '/^User=/d' -e '/^Group=/d' "infra/$u.service" > "/etc/systemd/system/$u.service"
done
[ -f /etc/livekit.yaml ] || echo "livekit.yaml must be pushed by the build server" >&2
systemctl daemon-reload
systemctl enable --now vibenation-jack vibenation-audio vibenation >/dev/null 2>&1 || true

# Video service ------------------------------------------------------------------------
# GStreamer compositor + encoders (services/video). VN_VIDEO_PROFILE=gpu comes from the
# pushed .env; NVENC elements (nvh264enc ...) are the nvcodec plugin in gstreamer1.0-plugins-bad.
apt-get install -y -qq -o DPkg::Lock::Timeout=300 python3-gi gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly gstreamer1.0-libav >/dev/null
# nvcodec registers its elements only if CUDA worked when the registry was scanned: rescan now.
rm -f /root/.cache/gstreamer-1.0/registry.*.bin
python3 -m venv --system-site-packages services/video/.venv
services/video/.venv/bin/pip install -q -r services/video/requirements.txt
sed -e 's#/home/vibe/vibenation/vibenation#/opt/vibenation#g' -e '/^User=/d' -e '/^Group=/d' \
  infra/vibenation-video.service > /etc/systemd/system/vibenation-video.service
systemctl daemon-reload
systemctl enable vibenation-video >/dev/null 2>&1 || true
systemctl restart vibenation-video || true
{
  echo "date: $(date -u +%FT%TZ)"
  services/video/.venv/bin/python -c 'import gi; gi.require_version("Gst", "1.0"); from gi.repository import Gst; Gst.init(None)
for f in ("nvh264enc", "nvcudah264enc", "nvautogpuh264enc", "x264enc", "compositor", "jackaudiosrc", "avenc_aac", "rtmp2sink", "flvmux"):
    print(f"gst {f}: " + ("ok" if Gst.ElementFactory.find(f) else "MISSING"))' 2>&1
  sleep 5
  curl -s --max-time 5 http://127.0.0.1:8092/state | jq -c '{profile, encoders: (.encoders | map_values(.encoder)), fps: .stats.fps, error}' 2>&1 \
    || echo "video service: not answering on :8092 (journalctl -u vibenation-video)"
} > data/video-check.txt 2>&1
cat data/video-check.txt
# --------------------------------------------------------------------------------------

# NVENC check (the reason this machine exists)
{
  echo "date: $(date -u +%FT%TZ)"
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>&1 || echo "nvidia-smi: not available"
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -E "h264_nvenc|hevc_nvenc" || echo "ffmpeg: no NVENC encoders"
  if ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=1920x1080:rate=60 -t 10 \
       -c:v h264_nvenc -preset p4 -tune ll -b:v 9M -g 120 -f null - 2>/tmp/nvenc.err; then
    echo "1080p60 NVENC test encode: OK"
  else
    echo "1080p60 NVENC test encode: FAILED: $(tail -3 /tmp/nvenc.err)"
  fi
} > data/nvenc-check.txt 2>&1
cat data/nvenc-check.txt
