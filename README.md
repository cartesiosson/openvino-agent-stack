# OVMS + Open WebUI sobre Intel Core Ultra (Lunar Lake)

Stack de agente local con:
- **OVMS** (OpenVINO Model Server) sirviendo dos modelos en INT4 sobre iGPU Arc 140V.
- **Open WebUI** como frontend de chat / agente.
- Backend único de OVMS expuesto a Open WebUI vía API compatible con OpenAI.

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
