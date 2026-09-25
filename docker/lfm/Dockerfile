# Local server for LFM2.5-2.6B (Q4 GGUF), via llama.cpp's built-in HTTP API
# (POST /completion, /v1/chat/completions). Weights are mounted at runtime
# (see docker-compose.yml), never baked into the image.
#
# Get GGUF weights from https://huggingface.co/LiquidAI (search "LFM2.5-2.6B GGUF").
FROM ghcr.io/ggml-org/llama.cpp:server

EXPOSE 8080
