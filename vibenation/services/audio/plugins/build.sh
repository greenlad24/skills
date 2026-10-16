#!/usr/bin/env bash
# Build every VibeNation LV2 plugin (Faust DSP + common/vn_arch.cpp wrapper) and
# install the bundles to $PREFIX (default /usr/local/lib/lv2).
#
#   ./build.sh                 build + install all
#   ./build.sh vn_fet vn_opto  build + install only these
#   NO_INSTALL=1 ./build.sh    build into ./build only
#
# Needs: faust (>= 2.70), g++, lv2-dev, python3.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/usr/local/lib/lv2}"
BUILD="$HERE/build"
GEN="$HERE/.gen"
CXX="${CXX:-g++}"
# x86-64-v2 = SSE4.2: runs on the build droplet and on the show server.
CXXFLAGS="${CXXFLAGS:--O3 -march=x86-64-v2 -fno-math-errno -fomit-frame-pointer -fvisibility=hidden}"
FAUSTFLAGS="${FAUSTFLAGS:--double -lang cpp -cn mydsp}"
PLUGINS=(vn_opto vn_fet vn_vca_bus vn_pultec vn_tape vn_tape_stereo vn_console vn_deesser vn_rider)
if [ $# -gt 0 ]; then PLUGINS=("$@"); fi

mkdir -p "$BUILD"
pids=()
build_one() {
  local name="$1"
  local dsp
  dsp="$(ls "$HERE"/*/"$name.dsp" 2>/dev/null | head -1)"
  [ -n "$dsp" ] || { echo "no $name.dsp" >&2; return 1; }
  local dir; dir="$(dirname "$dsp")"
  local out="$BUILD/$name.lv2"
  rm -rf "$out"; mkdir -p "$out" "$GEN"
  faust $FAUSTFLAGS -I "$HERE/common" -I "$dir" -a "$HERE/common/vn_arch.cpp" \
        "$dsp" -o "$GEN/$name.cpp"
  faust -I "$HERE/common" -I "$dir" -json -O "$GEN" "$dsp" -o "$name.json.cpp"
  python3 "$HERE/common/gen_ttl.py" "$GEN/$name.dsp.json" "$out" "$name"
  $CXX $CXXFLAGS -std=c++17 -shared -fPIC -I "$HERE/common" \
       -DVN_URI="\"https://vibenation.app/lv2/$name\"" \
       "$GEN/$name.cpp" -o "$out/$name.so"
  echo "built $name"
}

# two builds at a time (2 vCPU box)
for p in "${PLUGINS[@]}"; do
  ( set -e; build_one "$p" ) &
  pids+=($!)
  if [ ${#pids[@]} -ge 2 ]; then wait "${pids[0]}"; pids=("${pids[@]:1}"); fi
done
for pid in "${pids[@]}"; do wait "$pid"; done
for p in "${PLUGINS[@]}"; do [ -f "$BUILD/$p.lv2/$p.so" ] || { echo "BUILD FAILED: $p" >&2; exit 1; }; done

if [ -z "${NO_INSTALL:-}" ]; then
  mkdir -p "$PREFIX"
  for p in "${PLUGINS[@]}"; do
    rm -rf "$PREFIX/$p.lv2"
    cp -r "$BUILD/$p.lv2" "$PREFIX/"
  done
  echo "installed ${#PLUGINS[@]} bundles to $PREFIX"
fi
