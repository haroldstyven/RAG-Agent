from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import chromadb

from app.config import settings
from app.rag.embeddings import get_embedder

if TYPE_CHECKING:
    from app.rag.memory import Turn


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float  # distancia coseno: 0.0 = idéntico, ~1.0 = sin relación


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=settings.chroma_path)
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def _build_contextual_query(query: str, history: list[Turn] | None) -> str:
    if not history:
        return query
    recent_user = [t.content for t in history if t.role == "user"][-2:]
    if not recent_user:
        return query
    return " ".join(recent_user) + " " + query


async def retrieve(
    query: str,
    history: list[Turn] | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    k = top_k or settings.top_k
    contextual_query = _build_contextual_query(query, history)

    embedder = get_embedder()
    # RETRIEVAL_QUERY mejora la discriminación semántica en text-embedding-004
    vectors = await embedder.embed([contextual_query], task_type="RETRIEVAL_QUERY")

    collection = _get_collection()
    fetch_k = k * 2 if settings.use_reranker else k
    results = collection.query(
        query_embeddings=vectors,
        n_results=min(fetch_k, collection.count() or fetch_k),
        include=["documents", "metadatas", "distances"],
    )

    chunks = [
        RetrievedChunk(text=doc, source=meta["source"], score=dist)
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]

    if settings.use_reranker and chunks:
        chunks = await _rerank(query, chunks, k)

    return chunks[:k]


async def _rerank(
    query: str, chunks: list[RetrievedChunk], top_k: int
) -> list[RetrievedChunk]:
    from app.rag.reranker import get_reranker

    reranker = get_reranker()
    pairs = [(query, c.text) for c in chunks]
    scores = await asyncio.to_thread(reranker.predict, pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:top_k]]


import asyncio  # noqa: E402
