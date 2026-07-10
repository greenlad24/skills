#!/usr/bin/env bash
# Fetch the optional local audio classifier (YAMNet ONNX + class map).
# Without these files AutoDirector runs fine on pure DSP; with them you get
# singing/speech/music fusion and named background-noise identification.
set -euo pipefail

DEST="${1:-$HOME/Library/Application Support/AutoDirector/models}"
mkdir -p "$DEST"

echo "Fetching YAMNet ONNX model..."
# ONNX export of Google's YAMNet (AudioSet, 521 classes, Apache-2.0).
curl -L --fail -o "$DEST/yamnet.onnx" \
  "https://github.com/onnx/models/raw/main/validated/vision/../audio/yamnet/model/yamnet.onnx" \
  || curl -L --fail -o "$DEST/yamnet.onnx" \
  "https://huggingface.co/onnx-community/yamnet/resolve/main/onnx/model.onnx"

echo "Fetching AudioSet class map..."
curl -L --fail -o "$DEST/yamnet_class_map.csv" \
  "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv"

echo "Installing onnxruntime..."
python3 -m pip install --quiet onnxruntime

cat <<EOF

Done. Point AutoDirector at the model via config:
  "classifier": {
    "model": "$DEST/yamnet.onnx",
    "class_map": "$DEST/yamnet_class_map.csv"
  }
or environment: AUTODIRECTOR_YAMNET / AUTODIRECTOR_YAMNET_CLASSMAP
EOF
