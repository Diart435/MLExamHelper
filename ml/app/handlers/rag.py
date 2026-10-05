"""
Task handlers for the RAG worker.

=== КОНТРАКТ СООБЩЕНИЙ (для backend-команды) ===

Backend публикует в Redis Stream 'ml-tasks':
    XADD ml-tasks * payload '<JSON ниже>'

Worker публикует в Redis Stream 'ml-results':
    XADD ml-results * payload '<JSON ниже>'

Поле 'payload' — JSON-строка.

=== INPUT: type="ingest" ===
    {
        "task_id":     "<uuid>",
        "type":        "ingest",                  # ОБЯЗАТЕЛЬНО
        "material_id": "<int или uuid-string>",  # ОБЯЗАТЕЛЬНО
        "storage_key": "<path внутри MINIO_BUCKET>"  # ОБЯЗАТЕЛЬНО
        # "course_id": 42  # опционально, ml не использует, для логов backend'а
    }

OUTPUT (ok):
    {"task_id":"...","status":"ok","material_id":101,"chunks_indexed":42}

OUTPUT (error):
    {"task_id":"...","status":"error","error":"<сообщение>"}

=== INPUT: type="rag_question" ===
    {
        "task_id":     "<uuid>",
        "type":        "rag_question",            # ОБЯЗАТЕЛЬНО
        "material_id": "<int или uuid-string>",  # ОБЯЗАТЕЛЬНО
        "question":    "<text>",                  # ОБЯЗАТЕЛЬНО
        "top_k":       4                          # опционально, default 4
    }

OUTPUT (ok):
    {"task_id":"...","status":"ok","answer":"...","sources":["mat-101:abc","mat-101:def"]}

OUTPUT (error):
    {"task_id":"...","status":"error","error":"<сообщение>"}

=== КТО ЧТО ДЕЛАЕТ ===
- app/handlers/rag.py  — process_ingest() + process_question() (чистые функции,
                          НЕ знают про Redis, вызываются из workers/ и из demo)
- app/workers/rag.py   — RAGWorker: Redis consumer loop, роутит по type, XADD + XACK
"""

from loguru import logger

from app.parsers.pdf import download_and_extract
from app.services.rag import RAGService


async def process_ingest(task: dict, rag: RAGService) -> dict:
    """Handle type='ingest': download PDF from MinIO and index it."""
    task_id = task.get("task_id", "")
    material_id = task.get("material_id")
    storage_key = task.get("storage_key")

    if not (task_id and material_id is not None and storage_key):
        return {
            "task_id": task_id,
            "status": "error",
            "error": "missing required fields: task_id, material_id, storage_key",
        }

    try:
        text = await download_and_extract(storage_key)
        chunks_indexed = await rag.index_material(material_id, text)
        return {
            "task_id": task_id,
            "status": "ok",
            "material_id": material_id,
            "chunks_indexed": chunks_indexed,
        }
    except FileNotFoundError as e:
        logger.error(f"Ingest failed for {storage_key}: {e}")
        return {"task_id": task_id, "status": "error", "error": str(e)}
    except Exception as e:
        logger.exception(f"Ingest failed for {storage_key}")
        return {"task_id": task_id, "status": "error", "error": f"{type(e).__name__}: {e}"}


async def process_question(task: dict, rag: RAGService) -> dict:
    """Handle type='rag_question': answer using indexed material."""
    task_id = task.get("task_id", "")
    material_id = task.get("material_id")
    question = task.get("question", "")
    top_k = int(task.get("top_k", 4))

    if not (task_id and material_id is not None and question):
        return {
            "task_id": task_id,
            "status": "error",
            "error": "missing required fields: task_id, material_id, question",
        }

    if not rag.has_material(material_id):
        return {
            "task_id": task_id,
            "status": "error",
            "error": f"material {material_id} not indexed yet",
        }

    try:
        result = await rag.answer(material_id, question, top_k=top_k)
        return {
            "task_id": task_id,
            "status": "ok",
            "answer": result.answer,
            "sources": [h.chunk_id for h in result.sources],
        }
    except Exception as e:
        logger.exception(f"Question failed for task {task_id}")
        return {"task_id": task_id, "status": "error", "error": f"{type(e).__name__}: {e}"}
