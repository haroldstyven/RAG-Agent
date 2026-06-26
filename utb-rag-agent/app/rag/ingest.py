from pathlib import Path
from typing import Callable

import chromadb

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
    try:
        import tiktoken
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
    except ImportError:
        words = text.split()
        chunks, start = [], 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunks.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start += chunk_size - overlap
        return chunks


def _extract_pdf(path: Path) -> str | None:
    import fitz  # lazy — pymupdf
    doc = fitz.open(str(path))
    pages = [page.get_text() for page in doc]
    doc.close()
    text = "\n\n".join(p.strip() for p in pages if p.strip())
    return text if text else None


def _extract_title(path: Path, text: str) -> str:
    if path.suffix.lower() == ".md":
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    return path.stem.replace("-", " ").replace("_", " ").title()


def _enrich_for_embedding(title: str, chunk: str) -> str:
    """Antepone el título al chunk solo para el embedding; el texto en ChromaDB permanece limpio."""
    return f"Documento: {title}\n\n{chunk}"


async def ingest_docs(
    progress_cb: Callable[[int, int], None] | None = None,
) -> int:
    embedder = get_embedder()
    collection = _get_collection()
    total = 0

    paths = [p for p in _DOCS_PATH.rglob("*") if p.suffix.lower() in _SUPPORTED]

    chunk_map: dict[Path, tuple[str, list[str]]] = {}
    for path in paths:
        try:
            if path.suffix.lower() == ".pdf":
                raw = _extract_pdf(path)
                if raw is None:
                    continue
            else:
                raw = path.read_text(encoding="utf-8")
            title = _extract_title(path, raw)
            chunks = _chunk_text(raw, settings.chunk_size, settings.chunk_overlap)
            chunk_map[path] = (title, chunks)
        except Exception as exc:
            print(f"  ERROR pre-scan {path.name}: {exc}")

    chunks_total = sum(len(c) for _, c in chunk_map.values())
    chunks_done = 0

    for path, (title, chunks) in chunk_map.items():
        try:
            enriched = [_enrich_for_embedding(title, c) for c in chunks]
            vectors = await embedder.embed(enriched, task_type="RETRIEVAL_DOCUMENT")

            ids = [f"{path.stem}__{i}" for i in range(len(chunks))]
            metas = [
                {"source": path.name, "title": title, "chunk": i}
                for i in range(len(chunks))
            ]

            collection.upsert(
                ids=ids,
                embeddings=vectors,
                documents=chunks,
                metadatas=metas,
            )
            total += len(chunks)
            chunks_done += len(chunks)
            print(f"  {path.name} [{title}]: {len(chunks)} chunk(s)")

            if progress_cb:
                progress_cb(chunks_done, chunks_total)

        except Exception as exc:
            print(f"  ERROR {path.name}: {exc}")

    return total
