# OVMS + Open WebUI sobre Intel Core Ultra (Lunar Lake)

Stack de agente local con:
- **OVMS** (OpenVINO Model Server) sirviendo modelos en INT4 sobre iGPU Arc 140V.
- **Open WebUI** como frontend de chat / agente.
- **Pipelines** con un agente **ReAct** (loop Thought / Action / Observation) + tools de búsqueda, fetch y aritmética.
- **SearXNG** local para búsqueda web sin enviar queries a terceros.
- Backend único de OVMS expuesto a Open WebUI y a Claude Code vía API compatible con OpenAI.

Rendimiento medido: **~18-20 tokens/s** generando con Qwen3-8B INT4 sobre la iGPU Arc 140V de un Core Ultra 7 258V.

## ¿Por qué local? Sin tokens, sin red, sin compromisos

Casi todo el ecosistema de "agentes con LLM" se basa en consumir tokens contra APIs de pago (OpenAI, Anthropic, Google) o en infraestructura cloud que se factura por uso. Este proyecto demuestra que, con un **Core Ultra de portátil** (Lunar Lake, integrada Arc 140V), puedes:

- **Cero consumo de tokens externos**. Cada palabra que genera el modelo cuesta exactamente lo mismo que tener el portátil encendido. Si chateas todo el día o si lo dejas dormido en el cajón, el coste marginal de inferencia es **cero**. Adiós a las sorpresas en la factura por dejarse un loop suelto.
- **Privacidad total**. Los prompts no salen de la máquina. Para entornos con datos sensibles (clínicos, jurídicos, propiedad intelectual) o para empresas con políticas DLP, esto cambia las reglas: el agente puede leer documentos que jamás podrías mandar a una API externa.
- **Offline real**. Funciona sin red. En viajes, demos en estand, entornos air-gapped, o cuando la wifi del cliente es un drama, sigues teniendo asistente. La única vez que necesitas internet es para la descarga inicial de los pesos.
- **Latencia local**. ~18-20 tokens/s en iGPU INT4 son suficientes para una conversación fluida y para tareas de agente que no requieren razonamiento de frontera. Primer token < 1 s.
- **Sandbox sin facturas**. Iteras prompts, herramientas, pipelines ReAct, function calling, RAG… sin que el experimento te cueste un céntimo. Ideal para aprender, prototipar, enseñar, y para los proyectos que nunca harías "por si quedan caros".
- **Hardware que ya tienes**. Lunar Lake / Arrow Lake / Meteor Lake llevan **NPU + iGPU competentes** que la mayoría de la gente no usa para nada. Este stack los pone a trabajar.

**¿Para qué NO es esto?** Para tareas que exigen Sonnet / Opus / GPT-5: refactors complejos sobre bases grandes, razonamiento multi-paso de alto nivel, código no trivial. Un 8B-INT4 es ~50× más pequeño que un modelo frontera; eso se nota. Pero para chat, RAG, function calling sencillo, búsqueda asistida y prototipos de agentes, **te llega**.

## Modelos

| Modelo                       | Tipo            | Precisión | Endpoint OpenAI `model` |
|------------------------------|-----------------|-----------|--------------------------|
| `Qwen/Qwen3-8B`              | text-generation | INT4      | `qwen3-8b`               |
| `Qwen/Qwen2.5-VL-7B-Instruct`| image-text      | INT4      | `qwen25-vl-7b`           |

## Requisitos

- Windows con WSL2 + Docker Desktop, **integración WSL activada** para esta distro.
  - Docker Desktop → Settings → Resources → WSL Integration → habilita tu distro.
- iGPU expuesta a WSL: `ls /dev/dri` debe mostrar `card0` / `renderD128`.
- ~80 GB libres para el cache de HuggingFace + IR convertidos.
- Acceso a internet para descargar pesos.

> **Nota**: el iGPU Intel en WSL2 requiere drivers del host (Windows) actualizados y la imagen `openvino/model_server:latest-gpu` (que ya incluye `intel-opencl-icd`).

## Pasos

### 1. Convertir modelos (one-shot)

```bash
./scripts/export-models.sh
```

Esto lanza un contenedor temporal con `optimum-intel`, descarga los modelos de HuggingFace y los exporta a IR de OpenVINO con compresión INT4. Los resultados quedan en:

```
ovms/models/
├── qwen3-8b/
│   ├── 1/                # openvino_model.xml, tokenizer, etc.
│   └── graph.pbtxt
└── qwen25-vl-7b/
    ├── 1/
    └── graph.pbtxt
```

Si algún modelo es *gated* (no es el caso de éstos, pero por si cambia), pon tu token en `.env` → `HF_TOKEN=hf_...` y vuelve a ejecutar.

### 2. Levantar el stack

```bash
docker compose up -d
docker compose logs -f ovms        # primera carga del modelo puede tardar
```

OVMS expone:
- REST: `http://localhost:8000/v3/chat/completions` (compatible OpenAI)
- gRPC: `localhost:9000`
- Health: `http://localhost:8000/v2/health/ready`

Open WebUI: `http://localhost:3000`

### 3. Verificar OVMS directo (sin Open WebUI)

```bash
curl -s http://localhost:8000/v3/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role":"user","content":"Hola, ¿quién eres?"}],
    "max_tokens": 128
  }'
```

Para el VLM (Qwen2.5-VL) con imagen:

```bash
curl -s http://localhost:8000/v3/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen25-vl-7b",
    "messages": [{
      "role":"user",
      "content":[
        {"type":"text","text":"¿Qué ves?"},
        {"type":"image_url","image_url":{"url":"https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png"}}
      ]
    }],
    "max_tokens": 256
  }'
```

### 4. Usar desde Open WebUI

1. Abre `http://localhost:3000`.
2. Si `OPENWEBUI_AUTH=False`, entras directo. Si lo cambias a `True`, crea cuenta (la primera = admin).
3. Settings → Models: deberías ver `qwen3-8b` y `qwen25-vl-7b` listados (los obtiene de OVMS vía `/v3/models`).

### 5. Configurar el agente

El stack ya levanta **SearXNG** + tiene **function calling** y **RAG** activados por env vars. Sólo queda cargar las tools:

**Tools (función-calling, en `./tools/`)**

Open WebUI carga las tools desde su BBDD, no desde disco. Las tres `.py` que dejé en `tools/` (`calculator.py`, `web_fetch.py`, `weather.py`) se importan así:

1. Open WebUI → **Workspace → Tools → "+"**.
2. Copia/pega el contenido del `.py` y guarda.
3. En cada conversación, clic en el icono de tools y activa las que quieras.
4. Asegúrate de marcar **"Native function calling"** en Settings → Interface (usa el formato `tools` de OpenAI, no prompting). Sólo `qwen3-8b` funcionará bien con tools; los VLMs suelen flojear en function calling.

> Las tools también están montadas dentro del contenedor en `/app/backend/data/tools-staging/` (read-only) por si en el futuro Open WebUI añade auto-import desde disco.

**Búsqueda web (SearXNG)**

Ya está conectado vía `SEARXNG_QUERY_URL`. En cualquier chat, activa el switch **"Web Search"** debajo del input y el modelo consultará SearXNG → leerá los top-5 resultados → contestará con citas.

Verifica SearXNG directamente:
```bash
curl 'http://localhost:8888/search?q=openvino&format=json' | head -c 500
```
(No exponemos SearXNG en host por defecto. Si quieres acceso desde host, añade `ports: ["8888:8080"]` al servicio.)

**RAG con documentos**

Workspace → Knowledge → crea una colección → sube PDFs/MD/TXT. En el chat, prefija con `#nombre-coleccion` o adjunta el documento directamente. Embeddings: `all-MiniLM-L6-v2` (CPU, se descarga al primer uso).

**Imágenes con Qwen2.5-VL**

Cambia el modelo a `qwen25-vl-7b`, arrastra una imagen al input, pregunta. La imagen va como `image_url` en el payload OpenAI, OVMS la enruta al modelo VLM.

### 6. Agente ReAct (loop Thought / Action / Observation)

Además de las tools nativas de Open WebUI (paso 5), el stack incluye un **agente ReAct** corriendo como Pipeline. Aparece en Open WebUI como un modelo más, llamado `react-agent`.

**Cómo funciona**:
- El pipe ([pipelines/react_agent.py](pipelines/react_agent.py)) recibe el mensaje del usuario.
- Lanza un loop hasta `MAX_ITERATIONS` (default 6): pide al LLM (`qwen3-8b` vía OVMS) una `Thought + Action + Action Input`, ejecuta la tool, inyecta la `Observation` de vuelta, y repite hasta que el modelo emita `Final Answer:`.
- Streams el trace completo al chat (puedes desactivarlo poniendo `SHOW_TRACE=False` en las valves).

**Tools internas del agente** (no son las mismas que las del paso 5 — éstas viven dentro del pipeline):
- `search(query)` → SearXNG
- `fetch(url)` → GET + limpieza HTML
- `calc(expression)` → aritmética segura

**Uso**:
1. Open WebUI → selector de modelo arriba → elige `react-agent`.
2. Pregunta algo que requiera buscar/calcular, p.ej. *"¿Cuántos años tiene actualmente el CEO de Nvidia? Calcula su edad si nació el 17 de febrero de 1963."*
3. Verás cada `Thought / Action / Observation` en el chat, y al final la respuesta.

**Tunear el agente**:

Open WebUI → Admin Panel → Pipelines → `react-agent` → Valves. Puedes ajustar:
- `MAX_ITERATIONS`, `TEMPERATURE`, `MAX_TOKENS_PER_STEP`
- `MODEL` (cambiar a otro modelo de OVMS)
- `SHOW_TRACE` (oculta el trace si quieres sólo la respuesta final)

**Pipelines vs Tools nativas — cuándo usar qué**:
- *Tools nativas* (paso 5): el LLM elige cuándo llamarlas vía `tools=[...]` en la API. Más rápido, menos transparente.
- *ReAct pipeline*: loop explícito en Python, controlas iteraciones y prompt, ves todos los pasos. Más robusto cuando el modelo flojea en function calling nativo.

## OVMS como backend de Claude Code

[Claude Code](https://docs.claude.com/en/docs/claude-code) es la CLI oficial de Anthropic. Por defecto habla con `api.anthropic.com` usando el formato **Anthropic Messages API**. OVMS habla **OpenAI Chat Completions**. No son lo mismo: necesitas un proxy/router que traduzca entre ambos.

> **Honestidad primero**: usar Qwen3-8B INT4 en lugar de Sonnet/Opus dentro de Claude Code **degrada significativamente** la calidad. Claude Code está afinado y validado contra modelos Claude reales (tool calling preciso, prompt caching, extended thinking, edición quirúrgica de ficheros). Un modelo local de 8B no replica eso. Úsalo para:
> - Aprender cómo funciona Claude Code por dentro.
> - Iterar sin gastar créditos en tareas triviales.
> - Trabajar offline o en entornos air-gapped.
> - Demos, talleres y educación.
>
> **No** lo uses para producir código de producción crítico.

Dos caminos según cómo de fino quieras hilar.

### Opción A — `claude-code-router` (camino corto)

Es un router pensado exactamente para enchufar Claude Code a backends compatibles con OpenAI. Sustituye al binario `claude` por `ccr code`.

```bash
npm install -g @musistudio/claude-code-router
```

Crea `~/.claude-code-router/config.json`:

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

Arranca el router (déjalo en una terminal aparte):

```bash
ccr start
```

Y, en lugar de `claude`, ejecuta:

```bash
ccr code
```

Claude Code pega contra tu OVMS local sin enterarse de que no es Anthropic.

### Opción B — `LiteLLM` proxy (camino versátil)

LiteLLM es un proxy que expone una API Anthropic-compatible por delante y habla cualquier backend (OpenAI, OVMS, Ollama, vLLM, etc.) por detrás. Más flexible si vas a juntar varios modelos / proveedores.

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

Lanza el proxy:

```bash
litellm --config litellm.config.yaml --port 4000
```

Y dile a Claude Code que apunte ahí:

```bash
export ANTHROPIC_BASE_URL=http://localhost:4000
export ANTHROPIC_AUTH_TOKEN=sk-anything
claude   # ahora usa tu OVMS local
```

> El nombre que pongas en `model_name` debe coincidir con el que Claude Code intenta llamar (suele ser el alias del modelo Sonnet / Haiku del momento). Si Claude Code pide un modelo que LiteLLM no conoce, fallará — añádelo al `model_list` con el mismo `litellm_params`.

### Limitaciones que vas a notar

- **Tool calling**: Qwen3-8B soporta tools, pero su formato puede diverger del que espera Claude Code. Las herramientas internas (`Bash`, `Edit`, `Read`) pueden necesitar un prompt template adaptado o fallar de forma sutil (parámetros mal serializados, llamadas que el modelo "inventa" en texto en vez de en el campo `tools`).
- **Prompt caching**: Anthropic optimiza con cache breakpoints. OVMS los ignora — cada petición re-procesa todo el contexto.
- **Ventana de contexto**: Qwen3-8B soporta ~32k tokens; Claude Code asume hasta 200k. Conversaciones largas se truncarán y el modelo "olvidará" el inicio.
- **Extended thinking**: Qwen3 tiene su propio modo `<think>` (lo verás en las respuestas). No es el "extended thinking" de Claude, pero Claude Code puede confundirse con los tags.
- **Velocidad**: ~18-20 tok/s en iGPU. Suficiente para tareas cortas, frustrante para `claude` corriendo refactors largos.

Sweet spot: pedirle "explica este fichero", "genera un test para esta función", "qué hace este snippet", "renombra esta variable en todo el directorio". Para refactors arquitectónicos, vuelve a Sonnet/Opus.

## Memoria y rendimiento

- 32 GB unificados es ajustado con ambos modelos a la vez en iGPU. Si OVMS falla al cargar el segundo:
  - Baja `cache_size` en los `graph.pbtxt` (KV cache en GB).
  - Reduce `max_num_seqs` y `max_num_batched_tokens`.
  - Como último recurso, cambia `device: "GPU"` por `"NPU"` o `"CPU"` en uno de los dos `graph.pbtxt`.
- La primera generación tras `up` será lenta: OVMS compila el modelo para el iGPU y cachea en el volumen `ovms-cache`.

## Estructura

```
.
├── docker-compose.yml
├── .env
├── scripts/
│   └── export-models.sh         # conversión HF → OpenVINO INT4
├── ovms/
│   ├── config.json              # lista modelos para OVMS
│   └── models/
│       ├── qwen3-8b/graph.pbtxt
│       └── qwen25-vl-7b/graph.pbtxt
├── searxng/
│   └── settings.yml             # SearXNG con formato JSON habilitado
├── tools/                       # tools nativas Open WebUI (paso 5)
│   ├── calculator.py
│   ├── web_fetch.py
│   └── weather.py
├── pipelines/                   # agente ReAct (paso 6)
│   └── react_agent.py
└── openwebui-data/              # estado persistente de Open WebUI
```

## Troubleshooting

- **`/dev/dri` no existe en WSL**: actualiza Windows + drivers Intel Arc. Reinicia WSL: `wsl --shutdown`.
- **OVMS no detecta GPU**: dentro del contenedor `clinfo` debería listar el iGPU. Si no, revisa permisos de `/dev/dri` (los `group_add` 109/44 cubren los casos comunes; si tu render group tiene otro GID en tu distro, ajústalo).
- **Open WebUI no ve modelos**: comprueba `docker compose logs openwebui` y que `curl http://localhost:8000/v3/models` desde el host devuelve los dos modelos.
- **OOM al cargar el segundo modelo**: ver sección "Memoria y rendimiento".
- **Tools no se ejecutan**: activa "Native function calling" en Open WebUI → Settings → Interface. Si sigue sin llamar tools, el modelo puede no soportar bien `tools` por OVMS — prueba con `qwen3-8b`.
- **SearXNG devuelve 0 resultados**: el formato JSON necesita estar habilitado en `searxng/settings.yml` (ya lo está). Si SearXNG arranca antes de leer la config, reinicia: `docker compose restart searxng`.
- **`react-agent` no aparece**: comprueba `docker compose logs pipelines` — debe mostrar "Loaded react-agent". Si no, revisa sintaxis del `.py`. Tras editar `pipelines/react_agent.py`, reinicia: `docker compose restart pipelines`.
- **ReAct se queda en loop**: el modelo no sigue el formato. Baja `TEMPERATURE` a 0.0–0.1 en las valves; si persiste, ajusta `SYSTEM_PROMPT` en el `.py` con ejemplos few-shot.

---

## Licencia

[MIT](LICENSE) — uso libre, comercial y privado, sin garantías.

## Autor

**Mariano Ortega** · 2026

Si este proyecto te resulta útil, una estrella ⭐ en GitHub anima a seguir abriendo cosas. PRs y issues bienvenidos.
