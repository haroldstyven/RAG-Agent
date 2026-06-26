from pathlib import Path
from typing import Callable

import chromadb
import tiktoken

from app.config import settings
from app.rag.embeddings import get_embedder

_DOCS_PATH = Path(__file__).parent.parent.parent / "docs"
_SUPPORTED = {".md", ".txt", ".pdf"}


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


def _extract_pdf(path: Path) -> str | None:
    """Returns None if the PDF has no extractable text (likely a scan)."""
    import fitz  # lazy — pymupdf

    doc = fitz.open(str(path))
    pages = [page.get_text() for page in doc]
    doc.close()
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    return text if text else None


async def ingest_docs(
    progress_cb: Callable[[int, int], None] | None = None,
) -> int:
    """
    Indexa todos los documentos en _DOCS_PATH.
    progress_cb(chunks_done, chunks_total) se llama después de indexar cada archivo.
    """
    embedder = get_embedder()
    collection = _get_collection()
    total = 0

    paths = [p for p in _DOCS_PATH.rglob("*") if p.suffix.lower() in _SUPPORTED]

    # Pre-scan para calcular chunks totales (para barra de progreso)
    chunk_counts: dict[Path, list[str]] = {}
    for path in paths:
        try:
            if path.suffix.lower() == ".pdf":
                raw = _extract_pdf(path)
                if raw is None:
                    continue
            else:
                raw = path.read_text(encoding="utf-8")
            chunk_counts[path] = _chunk_text(raw, settings.chunk_size, settings.chunk_overlap)
        except Exception as exc:
            print(f"  ERROR pre-scan {path.name}: {exc}")

    chunks_total = sum(len(c) for c in chunk_counts.values())
    chunks_done = 0

    for path, chunks in chunk_counts.items():
        try:
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
            chunks_done += len(chunks)
            print(f"  {path.name}: {len(chunks)} chunk(s)")

            if progress_cb:
                progress_cb(chunks_done, chunks_total)

        except Exception as exc:
            print(f"  ERROR {path.name}: {exc}")

    return total
