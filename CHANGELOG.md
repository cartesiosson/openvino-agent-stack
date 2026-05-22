# Changelog

All notable changes to this project are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-22

### Added
- Initial public release on GitHub: <https://github.com/cartesiosson/openvino-agent-stack>.
- Docker Compose stack with **OVMS 2026.1.0** serving two models from a single
  endpoint:
  - `qwen3-8b` (`Qwen/Qwen3-8B`) on **Intel Arc 140V iGPU**, INT4, ~18 tok/s.
  - `qwen25-vl-7b` (`Qwen/Qwen2.5-VL-7B-Instruct`) on **CPU**, INT4, ~6 tok/s.
- **Open WebUI** as the chat / agent frontend, talking to OVMS via the
  OpenAI-compatible `/v3/chat/completions` endpoint.
- **Pipelines** container with a **ReAct agent** (`pipelines/react_agent.py`)
  exposing the loop Thought / Action / Observation as a regular model named
  `react-agent`.
- **SearXNG** local instance for privacy-friendly web search, wired to both
  Open WebUI's web-search and the ReAct agent's `search` tool.
- Three native Open WebUI tools (`tools/calculator.py`, `tools/web_fetch.py`,
  `tools/weather.py`) for function-calling demos.
- HuggingFace → OpenVINO INT4 export script (`scripts/export-models.sh`)
  using a throwaway `python:3.11-slim` container and `optimum-intel`.
- **WSL2 iGPU passthrough** working end-to-end via `/dev/dxg`,
  `/usr/lib/wsl` mount and the right `LD_LIBRARY_PATH` + render group GID.
- Documentation of how to use this OVMS as a **Claude Code backend** via
  `claude-code-router` or `LiteLLM`, with the limitations spelled out.
- Bilingual README (`README.md` English / `README.es.md` Spanish) with TOC,
  badge banner, two screenshots (Qwen3 on iGPU at 94%, Qwen2.5-VL on CPU
  at 98%), and a NPU / WSL2 limitation note.
- MIT license (`LICENSE`).

### Known limitations
- **NPU not accessible from WSL2** in current Windows / WSL versions —
  `/dev/accel` doesn't exist on the host, so OVMS can't reach the Intel NPU
  unless OVMS is run natively on Windows.
- **Hybrid placement is mandatory** on a 16 GB / 32 GB Lunar Lake: the Arc
  140V's USM pool can't hold both 5 GB INT4 models simultaneously, so the
  VLM stays on CPU.
- Open WebUI tools (function calling) work well with `qwen3-8b`; VLMs are
  flaky at native function calling.
