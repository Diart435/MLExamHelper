"""
End-to-end demo of the RAG pipeline (no Redis, no MinIO).

Run with: python -m app.demo

What it demonstrates:
1. "ingest" flow: index a local PDF (data/sample.pdf) into material 101.
2. "rag_question" flow: ask an on-topic question, get a real answer.
3. Off-topic question triggers the safe refusal (no hallucination).
4. Question for non-existent material returns a clear error.
"""

import asyncio

from app.core.logging import setup_logging
from app.parsers.pdf import extract_text
from app.services.rag import RAGService
from app.handlers.rag import process_question


async def main() -> None:
    setup_logging()
    rag = RAGService()

    # === 1. "ingest" flow (минуя MinIO — берём локальный PDF) ===
    text = extract_text("data/Лекция_№1_Модел_е_как_основной_метод_исслед_я_сложных_систем.pdf")
    chunks_n = await rag.index_material(101, text)
    print(f"\n[INGEST] Indexed {chunks_n} chunks from sample.pdf into material 101")
    print(f"Materials: {sorted(rag.indexed_materials())}\n")
    

    on_topic = "Что такое структурно-функциональная модель?"
    print(f"Q1 (on-topic, material 101): {on_topic}")
    result1 = await process_question(
        {"task_id": "demo-1", "type": "rag_question", "material_id": 101, "question": on_topic},
        rag,
    )
    print(f"A1: {result1['answer']}\n")



if __name__ == "__main__":
    asyncio.run(main())