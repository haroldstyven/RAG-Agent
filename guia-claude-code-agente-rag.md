# Guía — Construir el agente RAG real con Claude Code

Servicio backend que respalda el demo del navegador: el **agente de atención de primer nivel** de la UTB, la capa "build" de la arquitectura omnicanal. Pensado para tu stack (FastAPI · `uv` · ChromaDB · Gemini 2.5 Flash con Ollama como respaldo offline).

Objetivo del piloto: tener un endpoint `/chat` que recupere sobre procedimientos institucionales y responda fundamentado, con guardrail de escalamiento. El canal (WhatsApp/telefonía) se conecta después vía webhook — se deja el stub para mostrar que la arquitectura es la misma.

---

## 1. Cómo usar esta guía

1. Crea una carpeta vacía y abre Claude Code dentro: `claude`
2. Pega el **prompt maestro** de la sección 3 como primer mensaje.
3. Deja que cree la estructura, luego itera pidiendo un módulo a la vez (ingesta → retrieval → endpoint → guardrail → webhook).
4. Corre y prueba con las preguntas de la sección 6.

> Regla práctica con Claude Code: pídele que **no instale ni ejecute nada destructivo** y que use `uv`. Revisa cada diff antes de aceptar.

---

## 2. Decisiones de stack (ya tomadas, para que no te pregunte)

| Pieza | Elección | Respaldo / nota |
|---|---|---|
| Entorno | `uv` | `uv venv` + `uv add` |
| API | FastAPI + Uvicorn | endpoints async |
| Vector DB | ChromaDB (persistente local) | cero infra, archivo en disco |
| Embeddings | Gemini `text-embedding-004` | respaldo local: `nomic-embed-text` vía Ollama |
| LLM | Gemini 2.5 Flash | respaldo offline en sala: Ollama (`gemma3:4b`) |
| Config | `pydantic-settings` + `.env` | nunca hardcodear claves |

La doble vía LLM es a propósito: **Gemini para calidad, Ollama como red de seguridad si la sala no tiene buena red** — el mismo principio del demo en navegador.

---

## 3. Prompt maestro para Claude Code

Pega esto tal cual:

```
Quiero construir un microservicio de RAG en Python con FastAPI. Es el agente de
atención de primer nivel de una universidad (UTB). Usa uv para el entorno y
dependencias. No ejecutes comandos destructivos; muéstrame los diffs.

Stack:
- FastAPI + Uvicorn (async)
- ChromaDB persistente en ./data/chroma
- Embeddings: Gemini text-embedding-004, con interfaz intercambiable para usar
  Ollama (nomic-embed-text) si no hay red. Selección por variable de entorno.
- LLM: Gemini 2.5 Flash, con la misma interfaz intercambiable a Ollama
  (modelo local) por variable de entorno.
- Config con pydantic-settings leyendo un .env. Claves nunca hardcodeadas.

Estructura que quiero:
  app/
    main.py            # FastAPI, rutas
    config.py          # settings (.env)
    rag/
      ingest.py        # carga docs de ./docs (.md/.txt), chunking, embeddings, upsert a Chroma
      retriever.py     # query -> top_k chunks con score
      llm.py           # interfaz LLM (gemini | ollama)
      embeddings.py    # interfaz embeddings (gemini | ollama)
      agent.py         # orquesta: retrieve -> arma prompt -> LLM -> guardrail
    schemas.py         # modelos pydantic (ChatRequest, ChatResponse, Source)
    channels/
      whatsapp.py      # stub de webhook (recibe mensaje, llama agent, responde)
  docs/                # procedimientos institucionales de ejemplo (.md)
  scripts/ingest.py    # CLI para indexar ./docs
  .env.example
  pyproject.toml

Comportamiento del agente (agent.py):
- Recupera top_k=4 chunks. Calcula un score de relevancia.
- Si el mejor score está por debajo de un umbral, NO llama al LLM: devuelve
  escalate=true (la respuesta del API indica que se escala a un humano).
- Si hay contexto suficiente, arma un system prompt que obligue a responder SOLO
  con el contexto, en español, tono institucional, 2-4 frases, sin inventar. Si
  el contexto no alcanza, el modelo debe devolver el token ESCALAR y el servicio
  lo convierte en escalate=true.
- La respuesta incluye: answer, escalate (bool), sources (lista de {doc, score}).

Endpoints:
- POST /chat            {message} -> {answer, escalate, sources}
- POST /ingest          reindexar ./docs
- GET  /health
- POST /webhook/whatsapp stub: recibe payload tipo BSP, extrae el texto, llama al
  agente y responde en el formato del proveedor (deja TODO comentado dónde
  enchufar Atom / Twilio / Meta Cloud API).

Empieza por crear pyproject.toml con uv, la estructura de carpetas y main.py con
/health. Luego paramos y seguimos módulo por módulo.
```

---

## 4. Orden de construcción sugerido (un mensaje por paso)

1. **Esqueleto** — estructura + `/health` (lo hace el prompt maestro).
2. **Config** — `config.py` + `.env.example` (claves Gemini, flags `LLM_PROVIDER`, `EMBED_PROVIDER`).
3. **Embeddings + LLM** — las dos interfaces intercambiables (`gemini` | `ollama`).
4. **Ingesta** — `ingest.py`: leer `./docs`, chunking (~500 tokens, solape 50), embeddings, upsert a Chroma. Más `scripts/ingest.py`.
5. **Retriever** — `query -> top_k + score`.
6. **Agente + guardrail** — la lógica de la sección 3 (umbral → escala; token ESCALAR).
7. **`/chat`** — conecta todo.
8. **Webhook WhatsApp** — el stub que mapea a la arquitectura.

Pídele a Claude Code que después de cada paso te muestre cómo probarlo con `curl`.

---

## 5. Documentos de ejemplo (`./docs`)

Crea estos archivos (o pídele a Claude Code que los genere). Son los mismos temas del demo del navegador, para que ambos pilotos cuenten la misma historia:

- `matricula.md` · pasos de matrícula, paz y salvo, portal, pago
- `certificados.md` · certificado de notas (costo en UVT, 3-5 días, PDF firmado)
- `admision-posgrado.md` · requisitos de maestría, inscripción en línea
- `pagos.md` · medios (PSE/tarjeta/banco), fechas ordinaria/extraordinaria, financiación
- `carne.md` · trámite del carné, duplicado
- `reingreso.md` · solicitud de reingreso/reintegro

> En la entrevista puedes decir: "el corpus de muestra es sintético; en producción se ingieren los procedimientos reales que hoy viven en la mesa de servicio y en los PDF institucionales".

---

## 6. Pruebas para la demo

```bash
# indexar
uv run python scripts/ingest.py

# levantar
uv run uvicorn app.main:app --reload

# consultas que SÍ responde (fundamentado)
curl -s localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"¿Cuáles son los pasos para matricularme?"}'

# consulta que DEBE escalar (no está en el corpus)
curl -s localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"Un profesor me puso una nota injusta, ¿qué hago?"}'
```

Lo que demuestras: respuesta fundamentada **con fuente y score**, y el **escalamiento** cuando no hay base. Es exactamente lo que muestra el demo del navegador, pero con tu backend real.

---

## 7. Cómo hilarlo en la entrevista

- El **demo del navegador** lo abres si la red falla o para que Ricardo lo toque sin fricción.
- El **servicio FastAPI** es tu carta de CTO: "así se ve la capa build en mi stack; el canal de WhatsApp entra por este webhook, el retrieval usa embeddings reales sobre los procedimientos de la UTB, y el guardrail garantiza que no inventa — escala a la mesa de servicio".
- Cierra con la tesis build vs buy: **esta capa es la que la universidad no puede comprar**, y por eso vale construirla in-house.

---

## 8. Si quieres subir el nivel (solo si sobra tiempo)

- Reemplaza el retrieval léxico por **reranking** simple (orden por score de embeddings).
- Añade **memoria de conversación** corta (últimos N turnos) — encaja con tu experiencia en el agente Keren.
- Loguea cada consulta con su `score` y si escaló → eso es el insumo de las **métricas de ROI** (% resuelto en primer nivel) que prometes en la propuesta.
