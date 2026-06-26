import asyncio
from pathlib import Path

import chromadb
import tiktoken

from app.config import settings
from app.rag.embeddings import get_embedder

_DOCS_PATH = Path("./docs")
_SUPPORTED = {".md", ".txt"}


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=settings.chroma_path)
    return client.get_or_create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunks.append(enc.decode(tokens[start:end]))
        if end == len(tokens):
            break
        start += chunk_size - overlap
    return chunks


async def ingest_docs() -> int:
    embedder = get_embedder()
    collection = _get_collection()
    total = 0

    for path in _DOCS_PATH.rglob("*"):
        if path.suffix not in _SUPPORTED:
            continue

        raw = path.read_text(encoding="utf-8")
        chunks = _chunk_text(raw, settings.chunk_size, settings.chunk_overlap)

        vectors = await embedder.embed(chunks)

        ids = [f"{path.stem}__{i}" for i in range(len(chunks))]
        metas = [{"source": path.name, "chunk": i} for i in range(len(chunks))]

        collection.upsert(
            ids=ids,
            embeddings=vectors,
            documents=chunks,
            metadatas=metas,
        )
        total += len(chunks)
        print(f"  {path.name}: {len(chunks)} chunk(s)")

    return total
