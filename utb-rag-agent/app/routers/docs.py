import asyncio
from pathlib import Path

import chromadb
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File

from app.config import settings
from app.rag.ingest import _get_collection, ingest_docs
from app.rag.tasks import IngestTask, TaskStatus, create_task, get_task
from app.schemas import (
    DocDeleteResponse,
    DocInfo,
    DocsListResponse,
    IngestResponse,
    IngestTaskResponse,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

_DOCS_PATH = Path(__file__).parent.parent.parent / "docs"
_SUPPORTED = {".md", ".txt", ".pdf"}


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


async def _run_ingest(task: IngestTask) -> None:
    task.status = TaskStatus.RUNNING

    def on_progress(done: int, total: int) -> None:
        task.chunks_done = done
        task.chunks_total = total

    try:
        total = await ingest_docs(progress_cb=on_progress)
        task.chunks_done = total
        task.status = TaskStatus.DONE
    except Exception as exc:
        task.error = str(exc)
        task.status = TaskStatus.FAILED


@router.post("/upload", response_model=IngestTaskResponse)
async def upload_doc(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _SUPPORTED:
        raise HTTPException(
            status_code=422,
            detail=f"Formato no soportado: {suffix}. Usa .md, .txt o .pdf",
        )
    dest = _DOCS_PATH / file.filename
    dest.write_bytes(await file.read())

    task = create_task()
    background_tasks.add_task(_run_ingest, task)

    return IngestTaskResponse(
        task_id=task.id,
        status=task.status,
        chunks_done=task.chunks_done,
        chunks_total=task.chunks_total,
        progress=task.progress,
    )


@router.get("/task/{task_id}", response_model=IngestTaskResponse)
async def task_status(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tarea no encontrada.")
    return IngestTaskResponse(
        task_id=task.id,
        status=task.status,
        chunks_done=task.chunks_done,
        chunks_total=task.chunks_total,
        progress=task.progress,
        error=task.error,
    )


@router.delete("/{doc_name}", response_model=DocDeleteResponse)
async def delete_doc(doc_name: str):
    collection = _get_collection()
    result = collection.get(where={"source": doc_name}, include=["metadatas"])
    ids = result["ids"]
    if not ids:
        raise HTTPException(status_code=404, detail=f"Documento '{doc_name}' no encontrado en el índice.")

    collection.delete(ids=ids)

    file_path = _DOCS_PATH / doc_name
    if file_path.exists():
        file_path.unlink()

    return DocDeleteResponse(status="ok", doc=doc_name, chunks_removed=len(ids))
