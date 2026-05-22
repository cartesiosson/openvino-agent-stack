# Intel Ultra 7(R) Series 2: Qwen 3-8B en local e Integracion Claude Code

> 🌍 **Versión en español**: [README.es.md](README.es.md)

A local AI agent stack on **Intel Core Ultra (Lunar Lake)** — Qwen3-8B + Qwen2.5-VL-7B in INT4, zero token cost:

- **OVMS** (OpenVINO Model Server) serving INT4 models on the Arc 140V iGPU.
- **Open WebUI** as the chat / agent frontend.
- **Pipelines** running a **ReAct agent** (Thought / Action / Observation loop) with search, fetch and arithmetic tools.
- **SearXNG** locally for web search without leaking queries to third parties.
- A single OVMS backend exposed to Open WebUI and to Claude Code via an OpenAI-compatible API.

Measured throughput: **~18-20 tokens/s** generating with Qwen3-8B INT4 on the Arc 140V iGPU of a Core Ultra 7 258V.

## Table of Contents

- [Why local? No tokens, no network, no strings](#why-local-no-tokens-no-network-no-strings)
- [Models](#models)
- [Requirements](#requirements)
- [Setup](#setup)
  - [1. Convert the models](#1-convert-the-models-one-shot)
  - [2. Start the stack](#2-start-the-stack)
  - [3. Hit OVMS directly](#3-hit-ovms-directly-no-open-webui)
  - [4. Use it from Open WebUI](#4-use-it-from-open-webui)
  - [5. Configure the agent](#5-configure-the-agent)
  - [6. ReAct agent](#6-react-agent-thought--action--observation-loop)
- [OVMS as a Claude Code backend](#ovms-as-a-claude-code-backend)
- [Memory and performance](#memory-and-performance)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Author](#author)

## Why local? No tokens, no network, no strings

Almost the entire "LLM agent" ecosystem is built on burning tokens against paid APIs (OpenAI, Anthropic, Google) or on cloud infrastructure billed per use. This project shows that, on a **laptop-class Core Ultra** (Lunar Lake, Arc 140V iGPU), you can:

- **Zero external token cost**. Every word the model generates costs exactly the same as having the laptop on. Whether you chat all day or leave it sleeping in a drawer, the marginal cost of inference is **zero**. No more bill shock from a runaway loop.
- **Total privacy**. Prompts never leave the machine. For environments with sensitive data (clinical, legal, IP) or companies with DLP policies, this changes the game: the agent can read documents you would never be allowed to send to an external API.
- **Real offline**. Works without network. Travel, booth demos, air-gapped environments, or when the client's wifi is a nightmare — you still have an assistant. The only time you need internet is for the initial weight download.
- **Local latency**. ~18-20 tokens/s on iGPU INT4 is enough for a fluid conversation and for agent tasks that don't require frontier reasoning. First token < 1 s.
- **Bill-free sandbox**. Iterate on prompts, tools, ReAct pipelines, function calling, RAG… without the experiment costing you a cent. Ideal for learning, prototyping, teaching, and for the projects you'd never try "in case it gets expensive".
- **Hardware you already own**. Lunar Lake / Arrow Lake / Meteor Lake ship with a **competent NPU + iGPU** that most people don't use for anything. This stack puts them to work.

**What this is NOT for**: tasks that demand Sonnet / Opus / GPT-5 — complex refactors over large codebases, high-level multi-step reasoning, non-trivial code. An 8B-INT4 is ~50× smaller than a frontier model; you'll feel it. But for chat, RAG, simple function calling, assisted search and agent prototypes, **it's enough**.

## Models

| Model                          | Type            | Precision | Device   | OpenAI `model` endpoint |
|--------------------------------|-----------------|-----------|----------|--------------------------|
| `Qwen/Qwen3-8B`                | text-generation | INT4      | **iGPU** | `qwen3-8b`               |
| `Qwen/Qwen2.5-VL-7B-Instruct`  | image-text      | INT4      | **CPU**  | `qwen25-vl-7b`           |

> **Why not both on iGPU**: the Arc 140V shares RAM with the system and its USM pool can't hold two 5 GB INT4 models + their KV caches + their compile blobs at once. Hybrid placement (LLM on GPU, VLM on CPU) is the sweet spot for this class of hardware: chat is fast (18-20 tok/s) and the VLM runs at 3-8 tok/s only when you drop in an image, where the vision encoder's cost dominates latency anyway.

## Requirements

- Windows with WSL2 + Docker Desktop, **WSL integration enabled** for this distro.
  - Docker Desktop → Settings → Resources → WSL Integration → enable your distro.
- iGPU exposed to WSL: `ls /dev/dri` must show `card0` / `renderD128`.
- RAM: 32 GB physical on Windows, **at least 24 GB allocated to WSL** (WSL defaults to ~50% of host). If `free -h` inside WSL shows less, create `%USERPROFILE%\.wslconfig` with:
  ```ini
  [wsl2]
  memory=26GB
  swap=8GB
  ```
  Then restart with `wsl --shutdown`.
- ~80 GB free for the HuggingFace cache + converted IR.
- Internet access for the weight download.

> **Intel iGPU + WSL2**: requires up-to-date host (Windows) drivers and the `openvino/model_server:latest-gpu` image (which already ships `intel-opencl-icd` and `libze-intel-gpu`). This `docker-compose.yml` already mounts `/dev/dxg` and `/usr/lib/wsl` with the correct `LD_LIBRARY_PATH` so the host driver is visible from inside the container.

> ⚠️ **NPU (Intel AI Boost) is not accessible from WSL2 in this version**. The NPU on Lunar Lake / Meteor Lake / Arrow Lake is exposed on native Linux via `/dev/accel/accel0` with the `intel_vpu` kernel module, but WSL2 does not route that device into the Linux kernel as of today. Verify on the host with `ls /dev/accel` — it will be empty. If you want to use the NPU for inference (~10-20 tok/s on small LLMs without touching the iGPU), you have two paths:
> - Leave WSL2 and run OVMS directly on Windows (PowerShell + native binary), breaking this Docker stack.
> - Wait for Microsoft/Intel to enable NPU passthrough in WSL2 (on roadmap, no confirmed date).
>
> That's why this stack uses **iGPU for the LLM and CPU for the VLM**, leaving the NPU untouched.

## Setup

### 1. Convert the models (one-shot)

```bash
./scripts/export-models.sh
```

This spawns a throwaway container with `optimum-intel`, downloads the models from HuggingFace and exports them to OpenVINO IR with INT4 compression. Output lands at:

```
ovms/models/
├── qwen3-8b/
│   └── (openvino_model.xml, tokenizer, etc. + graph.pbtxt)
└── qwen25-vl-7b/
    └── (vision + LM models + tokenizer + graph.pbtxt)
```

If a model is *gated* (none of these are, but in case it changes later), drop your token in `.env` → `HF_TOKEN=hf_...` and re-run.

### 2. Start the stack

```bash
docker compose up -d
docker compose logs -f ovms        # first model load can take a while
```

OVMS exposes:
- REST: `http://localhost:8000/v3/chat/completions` (OpenAI-compatible)
- gRPC: `localhost:9000`
- Health: `http://localhost:8000/v2/health/ready`

Open WebUI: `http://localhost:3000`

### 3. Hit OVMS directly (no Open WebUI)

```bash
curl -s http://localhost:8000/v3/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role":"user","content":"Hi, who are you?"}],
    "max_tokens": 128
  }'
```

For the VLM (Qwen2.5-VL) with an image:

```bash
curl -s http://localhost:8000/v3/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen25-vl-7b",
    "messages": [{
      "role":"user",
      "content":[
        {"type":"text","text":"What do you see?"},
        {"type":"image_url","image_url":{"url":"https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png"}}
      ]
    }],
    "max_tokens": 256
  }'
```

### 4. Use it from Open WebUI

1. Open `http://localhost:3000`.
2. If `OPENWEBUI_AUTH=False`, you're in. If you flip it to `True`, the first account created becomes admin.
3. Settings → Models: you should see `qwen3-8b` and `qwen25-vl-7b` (Open WebUI pulls them from OVMS via `/v3/models`).

### 5. Configure the agent

The stack already launches **SearXNG** and has **function calling** + **RAG** enabled via env vars. All that's left is loading the tools.

**Tools (function calling, in `./tools/`)**

Open WebUI loads tools from its DB, not from disk. The three `.py` files in `tools/` (`calculator.py`, `web_fetch.py`, `weather.py`) are imported like this:

1. Open WebUI → **Workspace → Tools → "+"**.
2. Copy/paste the contents of the `.py` and save.
3. In each chat, click the tools icon and enable the ones you want.
4. Make sure **"Native function calling"** is checked under Settings → Interface (uses OpenAI's `tools` format, not prompting). Only `qwen3-8b` works well with tools; VLMs tend to be flaky at function calling.

> The tools are also mounted inside the container at `/app/backend/data/tools-staging/` (read-only) in case a future Open WebUI version adds auto-import from disk.

**Web search (SearXNG)**

Already wired up via `SEARXNG_QUERY_URL`. In any chat, flip the **"Web Search"** switch under the input and the model will query SearXNG → read the top-5 results → answer with citations.

Verify SearXNG directly:
```bash
curl 'http://localhost:8888/search?q=openvino&format=json' | head -c 500
```
(SearXNG is not exposed on the host by default. If you want host access, add `ports: ["8888:8080"]` to the service.)

**RAG with documents**

Workspace → Knowledge → create a collection → upload PDFs / MD / TXT. In chat, prefix with `#collection-name` or attach the document directly. Embeddings: `all-MiniLM-L6-v2` (CPU, downloaded on first use).

**Images with Qwen2.5-VL**

Switch the model to `qwen25-vl-7b`, drag an image into the input, ask. The image goes as `image_url` in the OpenAI payload, OVMS routes it to the VLM.

### 6. ReAct agent (Thought / Action / Observation loop)

Beyond Open WebUI's native tools (step 5), the stack ships a **ReAct agent** running as a Pipeline. It appears in Open WebUI as another model, named `react-agent`.

**How it works**:
- The pipe ([pipelines/react_agent.py](pipelines/react_agent.py)) receives the user's message.
- Runs a loop up to `MAX_ITERATIONS` (default 6): asks the LLM (`qwen3-8b` via OVMS) for a `Thought + Action + Action Input`, executes the tool, injects the `Observation` back, and repeats until the model emits `Final Answer:`.
- Streams the full trace to the chat (disable it by setting `SHOW_TRACE=False` in the valves).

**Internal agent tools** (different from step 5's — these live inside the pipeline):
- `search(query)` → SearXNG
- `fetch(url)` → GET + HTML cleanup
- `calc(expression)` → safe arithmetic

**Usage**:
1. Open WebUI → model selector at the top → pick `react-agent`.
2. Ask something that requires searching/calculating, e.g. *"How old is Nvidia's CEO right now? Compute his age assuming he was born on Feb 17, 1963."*
3. You'll see each `Thought / Action / Observation` in the chat, with the final answer at the end.

**Tuning the agent**:

Open WebUI → Admin Panel → Pipelines → `react-agent` → Valves. You can tune:
- `MAX_ITERATIONS`, `TEMPERATURE`, `MAX_TOKENS_PER_STEP`
- `MODEL` (point at a different OVMS model)
- `SHOW_TRACE` (hide the trace if you only want the final answer)

**Pipelines vs native Tools — when to use which**:
- *Native tools* (step 5): the LLM decides when to call them via `tools=[...]` in the API. Faster, less transparent.
- *ReAct pipeline*: explicit loop in Python, you control iterations and prompt, you see every step. More robust when the model is shaky on native function calling.

## OVMS as a Claude Code backend

[Claude Code](https://docs.claude.com/en/docs/claude-code) is Anthropic's official CLI. By default it talks to `api.anthropic.com` using the **Anthropic Messages API** format. OVMS speaks **OpenAI Chat Completions**. They aren't the same: you need a proxy / router that translates between them.

> **Honesty first**: using Qwen3-8B INT4 inside Claude Code instead of Sonnet / Opus **significantly degrades** quality. Claude Code is tuned and validated against real Claude models (precise tool calling, prompt caching, extended thinking, surgical file editing). A local 8B model does not replicate that. Use it for:
> - Learning how Claude Code works internally.
> - Iterating without burning credits on trivial tasks.
> - Working offline or in air-gapped environments.
> - Demos, workshops and teaching.
>
> **Don't** use it to ship critical production code.

Two paths depending on how fine you want to weave it.

### Option A — `claude-code-router` (short path)

A router built exactly for plugging Claude Code into OpenAI-compatible backends. It replaces the `claude` binary with `ccr code`.

```bash
npm install -g @musistudio/claude-code-router
```

Create `~/.claude-code-router/config.json`:

```json
{
  "Providers": [
    {
      "name": "local-ovms",
      "api_base_url": "http://localhost:8000/v3/chat/completions",
      "api_key": "sk-not-checked",
      "models": ["qwen3-8b"]
    }
  ],
  "Router": {
    "default":     "local-ovms,qwen3-8b",
    "background":  "local-ovms,qwen3-8b",
    "think":       "local-ovms,qwen3-8b",
    "longContext": "local-ovms,qwen3-8b"
  }
}
```

Start the router (leave it running in another terminal):

```bash
ccr start
```

And, instead of `claude`, run:

```bash
ccr code
```

Claude Code hits your local OVMS without realizing it isn't Anthropic.

### Option B — `LiteLLM` proxy (versatile path)

LiteLLM is a proxy that exposes an Anthropic-compatible API on one side and speaks any backend (OpenAI, OVMS, Ollama, vLLM, etc.) on the other. More flexible if you're juggling several models / providers.

```bash
pip install 'litellm[proxy]'
```

`litellm.config.yaml`:

```yaml
model_list:
  - model_name: claude-sonnet-4-5
    litellm_params:
      model: openai/qwen3-8b
      api_base: http://localhost:8000/v3
      api_key: sk-not-checked
  - model_name: claude-haiku-4-5
    litellm_params:
      model: openai/qwen3-8b
      api_base: http://localhost:8000/v3
      api_key: sk-not-checked
```

Launch the proxy:

```bash
litellm --config litellm.config.yaml --port 4000
```

And point Claude Code at it:

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=sk-anything
claude   # now uses your local OVMS
```

> The `model_name` you set must match the one Claude Code tries to call (usually the alias of the current Sonnet / Haiku model). If Claude Code asks for a model LiteLLM doesn't know, it will fail — add it to the `model_list` with the same `litellm_params`.

### Limitations you'll hit

- **Tool calling**: Qwen3-8B supports tools, but its format can drift from what Claude Code expects. The internal tools (`Bash`, `Edit`, `Read`) may need an adapted prompt template or fail silently (badly serialized params, calls the model "invents" in plain text instead of the `tools` field).
- **Prompt caching**: Anthropic optimizes with cache breakpoints. OVMS ignores them — every request re-processes the whole context.
- **Context window**: Qwen3-8B supports ~32k tokens; Claude Code assumes up to 200k. Long conversations will truncate and the model will "forget" the beginning.
- **Extended thinking**: Qwen3 has its own `<think>` mode (you'll see it in responses). It's not Claude's "extended thinking" but Claude Code can get confused with the tags.
- **Speed**: ~18-20 tok/s on iGPU. Fine for short tasks, frustrating for `claude` doing long refactors.

Sweet spot: "explain this file", "write a test for this function", "what does this snippet do", "rename this variable across the directory". For architectural refactors, go back to Sonnet / Opus.

## Memory and performance

**Default placement** (see Models table). Numbers measured on Core Ultra 7 258V, 32 GB RAM, INT4:
- `qwen3-8b` → **Arc 140V iGPU**: **~18 tok/s** sustained decoding, first-token < 1 s. Measured: 145 tokens in 7.9 s.
- `qwen25-vl-7b` → **CPU**: **~6 tok/s** sustained decoding. Measured: 191 tokens in 31.6 s. With an image, the first token adds 3-8 s for the vision encoder.

**Why we didn't try NPU**: as explained in *Requirements*, Intel's NPU **is not accessible from WSL2 in this version**. If we had access, it would be the ideal target for the VLM (frees the iGPU without penalizing as much as CPU).

**If you really want both on GPU** (not recommended, runs at the edge):
- Drop `cache_size` in both `graph.pbtxt` (KV cache in GB, default 0 = dynamic).
- Reduce `max_num_seqs` to 4-8 and `max_num_batched_tokens` to 2048.
- Add `"KV_CACHE_PRECISION":"u8"` to `plugin_config` — halves the KV cache footprint.
- Drop `enable_prefix_caching: true`.
- Even then, any long prompt can knock the iGPU out with `USM Host allocation failed`.

**The first generation after `docker compose up` will be slow** (30-90 s): OVMS compiles the model for the iGPU and stores the compiled blob in `/tmp/.ov_cache/` inside the container. Subsequent ones are immediate while the container is alive. If you recreate the container, it recompiles.

## Project structure

```
.
├── docker-compose.yml
├── .env.example
├── scripts/
│   └── export-models.sh         # HF → OpenVINO INT4 conversion
├── ovms/
│   ├── config.json              # model list for OVMS
│   └── models/
│       ├── qwen3-8b/graph.pbtxt
│       └── qwen25-vl-7b/graph.pbtxt
├── searxng/
│   └── settings.yml             # SearXNG with JSON format enabled
├── tools/                       # Open WebUI native tools (step 5)
│   ├── calculator.py
│   ├── web_fetch.py
│   └── weather.py
├── pipelines/                   # ReAct agent (step 6)
│   └── react_agent.py
└── openwebui-data/              # persistent Open WebUI state (gitignored)
```

## Troubleshooting

- **`/dev/dri` doesn't exist in WSL**: update Windows + Intel Arc drivers. Restart WSL: `wsl --shutdown`.
- **OVMS doesn't detect GPU**: from inside the container `clinfo` should list the iGPU. If not, check `/dev/dri` permissions (the `group_add` 992/44 covers WSL2; if your render device has a different GID, adjust it).
- **Open WebUI doesn't see the models**: check `docker compose logs openwebui` and that `curl http://localhost:8000/v3/models` from the host returns both models.
- **OOM when loading the second model**: see the "Memory and performance" section.
- **Tools don't fire**: enable "Native function calling" in Open WebUI → Settings → Interface. If they still don't, the model may not handle `tools` well via OVMS — try `qwen3-8b`.
- **SearXNG returns 0 results**: the JSON format must be enabled in `searxng/settings.yml` (it already is). If SearXNG starts before reading the config, restart: `docker compose restart searxng`.
- **`react-agent` doesn't appear**: check `docker compose logs pipelines` — should show "Loaded react-agent". If not, check the `.py` syntax. After editing `pipelines/react_agent.py`, restart: `docker compose restart pipelines`.
- **ReAct stuck in a loop**: the model isn't following the format. Drop `TEMPERATURE` to 0.0–0.1 in the valves; if it persists, tweak `SYSTEM_PROMPT` in the `.py` with few-shot examples.
- **Inference hangs silently** (request accepted, no response): the `graph.pbtxt` is missing the `input_stream_handler { SyncSetInputStreamHandler ... }` block needed by OVMS 2026.1.0+ to sync the LOOPBACK back-edge. The graphs in this repo already include it; if you write your own, copy the structure from `ovms/models/qwen3-8b/graph.pbtxt` or regenerate with `ovms --pull --task text_generation --source_model <HF_ID>`.

---

## License

[MIT](LICENSE) — free for personal, commercial and private use, no warranty.

## Author

**Mariano Ortega** · 2026

If this project helps you, a ⭐ on GitHub keeps me motivated to open more things. PRs and issues welcome.
