from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.channels.whatsapp import router as whatsapp_router
from app.config import settings
from app.rag.agent import chat
from app.rag.ingest import ingest_docs
from app.routers.docs import router as docs_router
from app.routers.metrics import router as metrics_router
from app.routers.sessions import router as sessions_router
from app.schemas import ChatRequest, ChatResponse, HealthResponse, IngestResponse

app = FastAPI(
    title="UTB RAG Agent",
    description="Agente de atención de primer nivel — Universidad Tecnológica de Bolívar",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(whatsapp_router)
app.include_router(metrics_router)
app.include_router(docs_router)
app.include_router(sessions_router)


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider,
        embed_provider=settings.embed_provider,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="El mensaje no puede estar vacío.")
    return await chat(body.message, session_id=body.session_id)


@app.post("/ingest", response_model=IngestResponse)
async def ingest_endpoint():
    total = await ingest_docs()
    return IngestResponse(status="ok", chunks_indexed=total)
