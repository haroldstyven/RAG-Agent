# Ruta de Implementación — UTB Agente Omnicanal RAG

> **Modo:** Goal-driven · Cada fase tiene un objetivo de negocio concreto  
> **Stack base:** FastAPI · ChromaDB · Gemini · Next.js 16 · Tailwind v4  
> **Repositorios:** `utb-rag-agent/` (backend) · `utb-rag-frontend/` (frontend)

---

## Estado actual (línea base)

| Componente | Estado |
|---|---|
| Backend RAG con guardrail 2 capas | ✅ |
| Dual-provider Gemini / Ollama | ✅ |
| Endpoints: /chat /ingest /metrics /kb /sessions /webhook | ✅ |
| Memoria de sesión (in-process) | ✅ |
| Métricas JSONL | ✅ |
| Frontend: Chat · Métricas · KB · Sesiones | ✅ |
| Design system institucional UTB | ✅ |

---

## Fase 1 — Listo para demo en vivo

> **Goal:** El agente responde en tiempo real, acepta documentos PDF y el frontend  
> muestra los tokens mientras el LLM genera. Demo sin fricciones técnicas.

### 1.1 Streaming de respuestas ✅
- [x] Añadir endpoint `POST /chat/stream` con `StreamingResponse` SSE en FastAPI
- [x] Implementar `GeminiLLM.stream()` usando `generate_content_stream` de google-genai
- [x] Implementar `OllamaLLM.stream()` con `"stream": true` en la API de Ollama
- [x] Actualizar `agent.py` para orquestar el streaming (guardrail antes de abrir el stream)
- [x] Consumir SSE en `src/app/chat/page.tsx` con `fetch` + `ReadableStream`
- [x] Mostrar tokens en tiempo real en `MessageBubble` mientras llegan
- [x] Mantener `/chat` (sin stream) como fallback para el webhook WhatsApp

### 1.2 Ingesta de PDFs ✅
- [x] Agregar dependencia `pymupdf` al `pyproject.toml` con `uv add pymupdf`
- [x] Extender `app/rag/ingest.py` para detectar `.pdf` y extraer texto con `fitz`
- [x] Manejar PDFs con texto embebido vs. PDFs escaneados (advertir si es imagen)
- [x] Actualizar `app/routers/docs.py` para aceptar `.pdf` en `/kb/upload`
- [x] Actualizar la zona de drag & drop en `src/app/kb/page.tsx` para mostrar `.pdf`
- [ ] Probar con un PDF real de reglamentación UTB

### 1.3 Ingesta en background con progreso ✅
- [x] Crear store de tareas en `app/rag/tasks.py` (`dict[str, TaskStatus]`)
- [x] Modificar `POST /kb/upload` para usar `BackgroundTasks` de FastAPI
- [x] Añadir `GET /kb/task/{task_id}` que devuelve `{status, chunks_done, chunks_total}`
- [x] Mostrar barra de progreso en el frontend durante el upload de documentos
- [x] Manejar el caso de error en la tarea background (status = "failed" con mensaje)

### 1.4 Variable de entorno `.env` para el frontend ✅
- [x] Documentar en `utb-rag-frontend/.env.local.example` las variables necesarias
- [x] Confirmar que `NEXT_PUBLIC_API_URL` apunta al backend en todos los entornos
- [x] Manejo de error cuando el backend no responde (indicador Wifi/WifiOff en header)

---

## Fase 2 — Calidad del RAG

> **Goal:** Las respuestas son más precisas, el agente entiende el hilo conversacional  
> completo y los escalamientos son solo los necesarios — no falsos positivos.

### 2.1 Retrieval conversacional
- [ ] Modificar `app/rag/retriever.py` para aceptar `history: list[Turn] | None`
- [ ] Componer el query de ChromaDB con los últimos 2 turnos + pregunta actual
- [ ] Actualizar `agent.py` para pasar el historial de sesión al retriever
- [ ] Probar el caso "¿y cuánto cuesta?" (seguimiento sin contexto explícito)
- [ ] Ajustar `ESCALATE_THRESHOLD` si el retrieval conversacional cambia la distribución de scores

### 2.2 Reranking con cross-encoder
- [ ] Agregar `sentence-transformers` al `pyproject.toml` con `uv add sentence-transformers`
- [ ] Crear `app/rag/reranker.py` con `CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")`
- [ ] Integrar reranker en `retriever.py`: recuperar top_k × 2 → rerankar → devolver top_k
- [ ] Hacer el reranker configurable (activar/desactivar por variable de entorno `USE_RERANKER`)
- [ ] Medir mejora en precision@k con las queries de prueba del corpus UTB

### 2.3 Embedding batch para ingesta rápida
- [ ] Investigar si `gemini-embedding-2` soporta batch nativo en la versión actual de la API
- [ ] Si está disponible: reemplazar el loop de una llamada por `embed_content(contents=[...lista])`
- [ ] Si no: paralelizar con `asyncio.gather()` para N chunks simultáneos (con rate limit)
- [ ] Medir tiempo de ingesta antes/después con el corpus de 6 documentos y con 20

### 2.4 Métricas en base de datos
- [ ] Agregar dependencia `aiosqlite` y `sqlalchemy[asyncio]` al `pyproject.toml`
- [ ] Crear `app/db/models.py` con tabla `queries` (id, ts, session_id, message, best_score, escalated, latency_ms)
- [ ] Crear `app/db/models.py` con tabla `feedback` (id, ts, session_id, message, answer, thumb, comment)
- [ ] Reemplazar `app/rag/metrics.py` (JSONL) por inserts a SQLite
- [ ] Migrar `app/routers/metrics.py` para leer desde SQLite con queries reales
- [ ] Añadir filtros por fecha en `GET /metrics/queries?desde=&hasta=`
- [ ] Mantener compatibilidad con el JSONL existente (importar histórico)

### 2.5 Endpoint de feedback
- [ ] Implementar `POST /feedback` en `app/main.py` usando el schema `FeedbackRequest` existente
- [ ] Persistir feedback en la tabla `feedback` de SQLite
- [ ] Agregar botones 👍 / 👎 en `MessageBubble.tsx` para las respuestas del agente
- [ ] Mostrar contador de thumbs en la vista de Métricas

---

## Fase 3 — Canales reales

> **Goal:** El mismo agente atiende por WhatsApp y email con la misma lógica RAG.  
> La arquitectura omnicanal es demostrable, no solo un stub.

### 3.1 WhatsApp con Meta Cloud API
- [ ] Registrar número de prueba en Meta for Developers (cuenta sandbox)
- [ ] Implementar verificación del webhook `GET /webhook/whatsapp?hub.mode=subscribe`
- [ ] Implementar validación de firma HMAC `X-Hub-Signature-256` en el middleware
- [ ] Completar `send_whatsapp_message()` con POST a `graph.facebook.com/v19.0/{phone_id}/messages`
- [ ] Manejar tipos de mensaje: texto, imagen (ignorar), audio (advertir que no soportado aún)
- [ ] Configurar `WHATSAPP_TOKEN` y `WHATSAPP_PHONE_NUMBER_ID` en `.env`
- [ ] Probar flujo completo: mensaje de WhatsApp → agente → respuesta en WhatsApp

### 3.2 Canal email (SendGrid Inbound Parse)
- [ ] Crear `app/channels/email.py` con webhook para SendGrid Inbound Parse
- [ ] Extraer asunto + cuerpo del email, llamar `agent.chat()`
- [ ] Responder vía SendGrid API con la respuesta del agente
- [ ] Si `escalate=true`, redirigir a la mesa de servicio (CC al correo de soporte UTB)
- [ ] Agregar `POST /webhook/email` a `app/main.py`

### 3.3 Frontend multicanal en Métricas
- [ ] Añadir campo `channel` (web / whatsapp / email) al schema de query y a la DB
- [ ] Mostrar desglose por canal en el dashboard de métricas
- [ ] Filtrar el historial de queries por canal en `GET /metrics/queries?channel=`

---

## Fase 4 — Producción y observabilidad

> **Goal:** El servicio puede desplegarse, monitorearse y escalarse.  
> El equipo de operaciones tiene visibilidad completa del agente en producción.

### 4.1 Autenticación
- [ ] Añadir `X-API-Key` header authentication en FastAPI con `APIKeyHeader`
- [ ] Configurar `API_KEY` en `.env` y en el frontend `.env.local`
- [ ] Proteger todos los endpoints excepto `/health` y `/webhook/*`
- [ ] Crear pantalla de login simple en el frontend (API key + localStorage)
- [ ] Documentar cómo rotar la clave sin downtime

### 4.2 Sesiones persistentes con Redis
- [ ] Agregar `redis[asyncio]` al `pyproject.toml` con `uv add redis`
- [ ] Crear `app/rag/session_store.py` con `RedisSessionStore` (get / save / delete / TTL 24h)
- [ ] Mantener `InMemorySessionStore` como fallback cuando Redis no está disponible
- [ ] Configurar `SESSION_BACKEND=redis` y `REDIS_URL` en `.env`
- [ ] Probar que las sesiones sobreviven un `uvicorn --reload`

### 4.3 Rate limiting
- [ ] Agregar `slowapi` al `pyproject.toml` con `uv add slowapi`
- [ ] Limitar `POST /chat` a 20 req/min por IP
- [ ] Limitar `POST /ingest` a 5 req/min por IP
- [ ] Devolver `429 Too Many Requests` con header `Retry-After`

### 4.4 Dockerización
- [ ] Crear `utb-rag-agent/Dockerfile` (Python 3.11-slim, uv, COPY app + docs)
- [ ] Crear `utb-rag-frontend/Dockerfile` (node:22-alpine, npm build, next start)
- [ ] Crear `docker-compose.yml` en `Dev/` con servicios: backend · frontend · redis
- [ ] Añadir volumen persistente para `data/chroma/` y `data/metrics.jsonl`
- [ ] Documentar `docker compose up --build` como comando de despliegue

### 4.5 Trazabilidad con OpenTelemetry
- [ ] Agregar `opentelemetry-sdk` y `opentelemetry-instrumentation-fastapi` con uv
- [ ] Instrumentar `agent.chat()` con spans: `rag.retrieve`, `rag.rerank`, `rag.generate`
- [ ] Añadir atributos: `session_id`, `best_score`, `escalated`, `latency_ms`
- [ ] Exportar trazas a Jaeger (local) o Grafana Cloud OTLP (producción)
- [ ] Crear dashboard de latencia P50/P95/P99 por endpoint

### 4.6 CI básico con GitHub Actions
- [ ] Crear `.github/workflows/ci.yml` que corra en cada PR
- [ ] Paso 1: `uv run python -m pytest tests/` (backend)
- [ ] Paso 2: `npm run build` (frontend)
- [ ] Paso 3: smoke test `curl /health` con el servidor levantado
- [ ] Crear `tests/test_agent.py` con al menos 3 casos: responde, escala, sesión multi-turno

---

## Fase 5 — Evaluación continua del RAG

> **Goal:** La calidad del agente es medible, comparable entre versiones  
> y mejorable sin intervención manual constante.

### 5.1 Dataset de evaluación UTB
- [ ] Crear `tests/eval_dataset.jsonl` con 30+ pares `{pregunta, respuesta_esperada, fuente}`
- [ ] Incluir casos: in-corpus (debe responder), out-of-corpus (debe escalar), ambiguos
- [ ] Cubrir los 6 documentos del corpus con al menos 4 preguntas cada uno
- [ ] Etiquetar cada caso con dificultad: fácil / media / difícil

### 5.2 Evaluación automática con RAGAS
- [ ] Agregar `ragas` al `pyproject.toml` con `uv add ragas`
- [ ] Crear `scripts/eval.py` que corre el dataset contra el endpoint `/chat`
- [ ] Medir: `faithfulness`, `answer_relevancy`, `context_recall`
- [ ] Guardar resultados en `data/eval_results/YYYY-MM-DD.json`
- [ ] Añadir paso de evaluación al CI que falla si `faithfulness < 0.80`

### 5.3 Versionado del corpus
- [ ] Crear estructura `docs/v1/`, `docs/v2/` para aislar versiones del corpus
- [ ] Parametrizar `COLLECTION_NAME` por versión en `.env` (`utb_docs_v2`)
- [ ] Crear script `scripts/promote_corpus.py` que indexa una versión nueva y valida scores
- [ ] Documentar el proceso de rollback: cambiar `COLLECTION_NAME` en `.env` y reiniciar

---

## Fase 6 — Agente con herramientas

> **Goal:** El agente puede consultar sistemas reales de la UTB — no solo el corpus.  
> Esto es lo que ningún SaaS puede ofrecer: integración con el sistema académico propio.

### 6.1 Arquitectura de herramientas (Tools)
- [ ] Definir interfaz `Tool` en `app/rag/tools.py` (nombre, descripción, parámetros, ejecutar)
- [ ] Migrar el agente a un loop tool-calling con Gemini function calling
- [ ] Implementar herramienta `buscar_en_corpus` (wraper del retriever actual)
- [ ] Implementar herramienta `escalar_a_asesor` (crea ticket en sistema de soporte)

### 6.2 Integración con portal académico UTB
- [ ] Crear `app/tools/portal_utb.py` con cliente HTTP al API del sistema académico
- [ ] Herramienta `consultar_estado_matricula(codigo_estudiante)` → estado real
- [ ] Herramienta `verificar_paz_y_salvo(codigo_estudiante)` → deudas pendientes
- [ ] Herramienta `consultar_notas(codigo_estudiante, periodo)` → historial académico
- [ ] Autenticar con el sistema académico vía OAuth2 o API key institucional

### 6.3 Creación de tickets en mesa de servicio
- [ ] Investigar el sistema de tickets actual de UTB (ServiceNow / Zendesk / otro)
- [ ] Implementar herramienta `crear_ticket(motivo, prioridad, datos_estudiante)`
- [ ] Notificar al asesor asignado por email o WhatsApp al escalar
- [ ] Registrar el ticket_id en la DB de métricas para seguimiento

### 6.4 Memoria a largo plazo por estudiante
- [ ] Crear tabla `student_profiles` en la DB con preferencias y historial de consultas
- [ ] Al recibir un `student_id` en el request, cargar su perfil como contexto adicional
- [ ] Detectar consultas recurrentes del mismo estudiante (posible gap en el corpus)

---

## Métricas de éxito por fase

| Fase | KPI objetivo |
|------|-------------|
| 1 — Demo en vivo | TTFT (time-to-first-token) < 800ms · PDFs ingestados correctamente |
| 2 — Calidad RAG | Escalamientos falsos positivos < 10% · `faithfulness` > 0.85 |
| 3 — Canales reales | WhatsApp end-to-end funcional · Email respondido en < 30s |
| 4 — Producción | Uptime > 99.5% · P95 latencia < 3s · 0 datos perdidos en reinicio |
| 5 — Evaluación | CI verde en cada PR · Score RAGAS registrado por versión |
| 6 — Herramientas | 60%+ consultas resueltas sin buscar en corpus (datos en tiempo real) |

---

## Deuda técnica conocida

- [ ] `GeminiEmbedder.embed()` hace una llamada HTTP por chunk (no batch) — ver Fase 2.3
- [ ] `_store` de sesiones muere al reiniciar uvicorn — ver Fase 4.2
- [ ] `JSONL` de métricas no consultable por fecha — ver Fase 2.4
- [ ] Threshold `ESCALATE_THRESHOLD=0.50` sin calibración formal — ver Fase 2.1
- [ ] Ingest bloquea el request thread con corpus grandes — ver Fase 1.3
- [ ] Sin autenticación en ningún endpoint — ver Fase 4.1
- [x] Sin soporte PDF — ✅ resuelto en Fase 1.2
- [ ] `tailwind.config.ts` vacío (solo content paths) — acceptable para v4

---

> Última actualización: 2026-06-25  
> Responsable técnico: Harold Lagares  
> Repositorio: `Dev/utb-rag-agent` + `Dev/utb-rag-frontend`
