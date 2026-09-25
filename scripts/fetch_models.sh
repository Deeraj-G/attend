#!/usr/bin/env bash
# Downloads the LFM2.5-2.6B GGUF weights for the local `lfm` docker service
# (docker-compose.yml). Not committed to git — see .gitignore's `models/` entry.
#
# LFM2.5-Audio-1.5B needs no separate fetch: the `lfm-audio` container pulls
# it from Hugging Face itself on first start.
set -euo pipefail

REPO="LiquidAI/LFM2.5-2.6B-GGUF"
FILE="${LFM_MODEL_FILE:-LFM2.5-2.6B-QAD-Q4_0.gguf}"
OUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/models/lfm"
OUT_PATH="$OUT_DIR/lfm2.5-2.6b-q4.gguf"

mkdir -p "$OUT_DIR"

if [ -f "$OUT_PATH" ]; then
  echo "Already have $OUT_PATH, skipping."
  exit 0
fi

echo "Downloading $FILE from $REPO (~1.6GB)..."
curl -L --fail -o "$OUT_PATH" "https://huggingface.co/${REPO}/resolve/main/${FILE}"
echo "Saved to $OUT_PATH"
