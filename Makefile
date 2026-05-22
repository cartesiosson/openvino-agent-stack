# Quality-of-life shortcuts. Plain `docker compose` works too — these just
# bundle the most common flag combos.

SHELL := /bin/bash
COMPOSE := docker compose
OVMS_REST := http://localhost:8000

.PHONY: help models up down restart logs ps health smoke clean

help:  ## show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*##/ { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

models:  ## download + convert Qwen3-8B and Qwen2.5-VL-7B to OpenVINO INT4
	./scripts/export-models.sh

up:  ## start the full stack (OVMS, Open WebUI, Pipelines, SearXNG)
	$(COMPOSE) up -d

down:  ## stop and remove containers (volumes preserved)
	$(COMPOSE) down

restart:  ## recreate all containers (picks up config changes)
	$(COMPOSE) up -d --force-recreate

logs:  ## tail OVMS logs (most useful when debugging)
	$(COMPOSE) logs -f ovms

ps:  ## show running services and their health
	$(COMPOSE) ps

health:  ## quick health probe: OVMS readiness + model list
	@echo "→ OVMS /v2/health/ready"
	@curl -s -o /dev/null -w "  HTTP %{http_code}\n" $(OVMS_REST)/v2/health/ready
	@echo "→ OVMS /v3/models"
	@curl -s $(OVMS_REST)/v3/models | python3 -m json.tool 2>/dev/null || echo "  no JSON yet"

smoke:  ## end-to-end inference test against qwen3-8b on iGPU
	@echo "→ qwen3-8b chat completion"
	@time curl -s -m 60 $(OVMS_REST)/v3/chat/completions \
		-H 'Content-Type: application/json' \
		-d '{"model":"qwen3-8b","messages":[{"role":"user","content":"Say only: smoke ok"}],"max_tokens":20,"temperature":0}' \
		| python3 -c "import json,sys; d=json.load(sys.stdin); print('content:', d['choices'][0]['message']['content']); print('usage :', d['usage'])"

clean:  ## stop stack AND remove named volumes (model compile cache, pipelines cache)
	$(COMPOSE) down -v
