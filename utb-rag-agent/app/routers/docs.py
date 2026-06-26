from pathlib import Path

import chromadb
from fastapi import APIRouter, HTTPException, UploadFile, File

from app.config import settings
from app.rag.ingest import ingest_docs, _get_collection
from app.schemas import DocDeleteResponse, DocInfo, DocsListResponse, IngestResponse

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

_DOCS_PATH = Path(__file__).parent.parent.parent / "docs"
_SUPPORTED = {".md", ".txt"}


@router.get("", response_model=DocsListResponse)
async def list_docs():
    collection = _get_collection()
    result = collection.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for meta in result["metadatas"]:
        src = meta.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1
    documents = [DocInfo(name=k, chunks=v) for k, v in sorted(counts.items())]
    return DocsListResponse(documents=documents)


@router.post("/upload", response_model=IngestResponse)
async def upload_doc(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _SUPPORTED:
        raise HTTPException(
            status_code=422,
            detail=f"Formato no soportado: {suffix}. Usa .md o .txt",
        )
    dest = _DOCS_PATH / file.filename
    dest.write_bytes(await file.read())
    total = await ingest_docs()
    return IngestResponse(status="ok", chunks_indexed=total)


@router.delete("/{doc_name}", response_model=DocDeleteResponse)
async def delete_doc(doc_name: str):
    collection = _get_collection()
    result = collection.get(where={"source": doc_name}, include=["metadatas"])
    ids = result["ids"]
    if not ids:
        raise HTTPException(status_code=404, detail=f"Documento '{doc_name}' no encontrado en el índice.")

    collection.delete(ids=ids)

    # Elimina el archivo físico si existe
    file_path = _DOCS_PATH / doc_name
    if file_path.exists():
        file_path.unlink()

    return DocDeleteResponse(status="ok", doc=doc_name, chunks_removed=len(ids))
