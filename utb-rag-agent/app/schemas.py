from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class Source(BaseModel):
    doc: str
    score: float   # similitud coseno 0..1 (mayor = más relevante)
    snippet: str = ""


class ChatResponse(BaseModel):
    answer: str
    escalate: bool
    sources: list[Source]


class IngestResponse(BaseModel):
    status: str
    chunks_indexed: int


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    embed_provider: str


# ── Métricas ────────────────────────────────────────────────────────────────

class ChannelBreakdown(BaseModel):
    web: int = 0
    whatsapp: int = 0
    email: int = 0


class MetricsSummary(BaseModel):
    total_queries: int
    resolved: int
    escalated: int
    resolution_rate: float
    avg_best_score: float
    thumbs_up: int = 0
    thumbs_down: int = 0
    by_channel: ChannelBreakdown = ChannelBreakdown()


class QueryRecord(BaseModel):
    ts: str
    session_id: str | None
    message: str
    best_score: float
    escalated: bool
    latency_ms: float | None = None
    channel: str = "web"
    sources: list[Source]


class QueryHistoryResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[QueryRecord]


# ── Documentos ──────────────────────────────────────────────────────────────

class DocInfo(BaseModel):
    name: str
    chunks: int


class DocsListResponse(BaseModel):
    documents: list[DocInfo]


class DocDeleteResponse(BaseModel):
    status: str
    doc: str
    chunks_removed: int


class ChunkPreview(BaseModel):
    chunk_idx: int
    text: str


class DocChunksResponse(BaseModel):
    doc: str
    chunks: list[ChunkPreview]


# ── Sesiones ────────────────────────────────────────────────────────────────

class TurnRecord(BaseModel):
    role: str
    content: str


class SessionSummary(BaseModel):
    session_id: str
    turn_count: int
    created_at: float
    updated_at: float
    last_message: str | None = None


class SessionListResponse(BaseModel):
    total: int
    sessions: list[SessionSummary]


class SessionHistoryResponse(BaseModel):
    session_id: str
    turns: list[TurnRecord]


class SessionDeleteResponse(BaseModel):
    status: str
    session_id: str


# ── Feedback ────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    session_id: str
    message: str
    answer: str
    thumb: bool                   # True = positivo, False = negativo
    comment: str | None = None


class FeedbackResponse(BaseModel):
    status: str


# ── Tareas de ingesta en background ─────────────────────────────────────────

class IngestTaskResponse(BaseModel):
    task_id: str
    status: str
    chunks_done: int
    chunks_total: int
    progress: float
    error: str | None = None
