from dataclasses import dataclass

import chromadb

from app.config import settings
from app.rag.embeddings import get_embedder


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float  # distancia coseno: 0.0 = idéntico, más alto = más distante


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=settings.chroma_path)
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


async def retrieve(query: str) -> list[RetrievedChunk]:
    embedder = get_embedder()
    vectors = await embedder.embed([query])

    collection = _get_collection()
    results = collection.query(
        query_embeddings=vectors,
        n_results=settings.top_k,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append(RetrievedChunk(text=doc, source=meta["source"], score=dist))

    return chunks
