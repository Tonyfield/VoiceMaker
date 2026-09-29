#!/bin/bash
set -e

echo "Starting vllm-omni..."

export MODEL=/app/models/tts_models/IndexTeam/IndexTTS-2.5
export MODEL_VERSION=2.5
export CUDA_LAUNCH_BLOCKING=1
export TORCH_USE_CUDA_DSA=1
export LOG_LEVEL=DEBUG

uv run vllm serve \
  /app/models/tts_models/IndexTeam/IndexTTS-2.5 \
  --omni \
  --trust-remote-code \
  --served-model-name IndexTeam/IndexTTS-2.5 \
  --deploy-config /app/indextts2_5.yaml \
  --port 20212
