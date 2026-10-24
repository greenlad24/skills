#!/bin/bash
# Records 10 s of exactly what the stream sends (a local RTMP copy of the 16:9 output, next to
# YouTube) and counts silent gaps in the sound. Run on the show server while live:
#   bash /opt/vibenation/infra/showserver/check_stream_gaps.sh
# Prints "OK 0 gaps" or "STUTTER: N gaps"; exit code 1 on stutter.
#
# WARNING: on the 24 Oct live, YouTube dropped and reconnected ~14 s after each run (a few
# seconds of outage for viewers). Until that is understood it refuses to run while a platform
# is live; pass --while-live to run anyway.
set -u
if [ "${1:-}" != "--while-live" ] && curl -s -m3 127.0.0.1:8092/state | python3 -c 'import json,sys; o=json.load(sys.stdin)["outputs"]; sys.exit(0 if any(x["name"] != "GapCheck" and x["state"] == "live" for x in o) else 1)'; then
  echo 'A platform is live: not running (it can make YouTube reconnect). Use --while-live to force.'; exit 3
fi
cd /tmp && rm -f vn_gapcheck.flv vn_gapcheck.wav
timeout 40 ffmpeg -v error -listen 1 -i rtmp://127.0.0.1:19350/live/gapcheck -c copy -t 10 -y vn_gapcheck.flv &
sleep 1
curl -s -m5 -X POST 127.0.0.1:8092/cmd -H 'content-type: application/json' \
  -d '{"start":[{"name":"GapCheck","url":"rtmp://127.0.0.1:19350/live","key":"gapcheck","profile":"16x9-9M"}]}' >/dev/null
wait
curl -s -m5 -X POST 127.0.0.1:8092/cmd -H 'content-type: application/json' -d '{"stop":["GapCheck"]}' >/dev/null
ffmpeg -v error -i vn_gapcheck.flv -vn -ac 1 -ar 48000 -f s16le -y vn_gapcheck.raw || { echo 'No stream output to check (is it live?)'; exit 2; }
python3 - <<'PY'
import array, sys
a = array.array('h'); a.frombytes(open('/tmp/vn_gapcheck.raw', 'rb').read())
x = a[24000:]                       # skip the first 0.5 s (connect)
gaps = run = 0
for v in x:                         # a gap = 2 ms or more of digital silence inside the sound
    if -1 <= v <= 1: run += 1
    else:
        if run >= 96: gaps += 1
        run = 0
print(f'OK 0 gaps in {len(x) / 48000:.1f} s' if gaps == 0 else f'STUTTER: {gaps} gaps in {len(x) / 48000:.1f} s')
sys.exit(1 if gaps else 0)
PY
