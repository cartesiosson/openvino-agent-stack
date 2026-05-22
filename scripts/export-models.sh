#!/usr/bin/env bash
# Convert HF models to OpenVINO IR with INT4 weight compression.
# OVMS MediaPipe LLM pattern: weights live next to graph.pbtxt (no versioned 1/ dir).
#
# Re-runs are idempotent: if openvino_model.xml exists in the target dir, skip.
# Container runs as root (needed for apt/pip), then chowns output to the host user.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODELS_DIR="$ROOT/ovms/models"

# shellcheck disable=SC1091
[ -f "$ROOT/.env" ] && source "$ROOT/.env"

CONV_IMAGE="python:3.11-slim"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

run_convert() {
  local hf_id="$1"
  local out_name="$2"
  local extra_args="${3:-}"

  local out_dir="$MODELS_DIR/$out_name"

  if [ -f "$out_dir/openvino_model.xml" ]; then
    echo "[skip] $out_name already converted at $out_dir"
    return 0
  fi

  echo "[convert] $hf_id -> $out_dir (INT4)"
  mkdir -p "$out_dir"

  docker run --rm \
    -e DEBIAN_FRONTEND=noninteractive \
    -e PIP_ROOT_USER_ACTION=ignore \
    -e HF_HOME=/tmp/hf \
    -e HF_TOKEN="${HF_TOKEN:-}" \
    -e HOST_UID="$HOST_UID" \
    -e HOST_GID="$HOST_GID" \
    -e OUT_NAME="$out_name" \
    -e HF_ID="$hf_id" \
    -e EXTRA_ARGS="$extra_args" \
    -v "$MODELS_DIR:/models" \
    --entrypoint /bin/bash \
    "$CONV_IMAGE" \
    -lc '
      set -euo pipefail
      apt-get update -qq
      apt-get install -y -qq --no-install-recommends git >/dev/null
      pip install --quiet --no-cache-dir --upgrade pip
      pip install --quiet --no-cache-dir \
        "optimum[openvino,nncf]>=1.23" \
        "transformers>=4.55" \
        "huggingface_hub" \
        "pillow" \
        "sentencepiece" \
        "protobuf"
      if [ -n "$HF_TOKEN" ]; then
        hf auth login --token "$HF_TOKEN" || huggingface-cli login --token "$HF_TOKEN"
      fi
      mkdir -p "/tmp/export-$OUT_NAME"
      # shellcheck disable=SC2086
      optimum-cli export openvino \
        --model "$HF_ID" \
        --weight-format int4 \
        --ratio 1.0 \
        --group-size 64 \
        $EXTRA_ARGS \
        "/tmp/export-$OUT_NAME"
      cp -r "/tmp/export-$OUT_NAME/." "/models/$OUT_NAME/"
      chown -R "$HOST_UID:$HOST_GID" "/models/$OUT_NAME"
    '
}

run_convert "Qwen/Qwen3-8B" "qwen3-8b" "--task text-generation-with-past --trust-remote-code"
run_convert "Qwen/Qwen2.5-VL-7B-Instruct" "qwen25-vl-7b" "--trust-remote-code --task image-text-to-text"

echo
echo "Done."
ls -la "$MODELS_DIR/qwen3-8b" "$MODELS_DIR/qwen25-vl-7b"
