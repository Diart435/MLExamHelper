"""
End-to-end demo of the RAG pipeline — без Redis, без MinIO.

Самый простой сценарий «правишь в коде → запускаешь»:

  1. Открой этот файл и найди блок JOBS ниже.
  2. Поправь `question` в нужной записи (или добавь свою).
  3. Поставь ACTIVE_MODE = "pptx" (или что хочешь).
  4. Запусти:
       python -m app.demo                 # возьмёт ACTIVE_MODE из кода
       python -m app.demo pptx             # то же, но без правки кода
       python -m app.demo pptx,mp3,url     # несколько подряд
       python -m app.demo all              # весь auto-discovery по data/

CLI-флаги (`--file`, `--url`, `--question`, ...) сохранены для ad-hoc прогонов.

Что делает в режиме JOBS:
1. По `ACTIVE_MODE`/`mode` берёт одну запись из JOBS.
2. Для `path`: download_and_extract (по расширению — PDF/PPTX/MP3/...) → chunk → embed.
   Для `url`  : http → trafilatura → chunk → embed.
3. material_id из JOBS либо сгенерированный (1..N в auto-режиме).
4. Задаёт заданный вопрос, печатает ответ.

Без внешних сервисов: чтение из `data/` идёт напрямую (см. fetch_bytes).
URL — реальный HTTP (нужен интернет).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.core.logging import setup_logging
from app.handlers.rag import process_question
from app.parsers import registry as parser_registry
from app.parsers.base import UnsupportedFormatError, download_and_extract
from app.services.rag import RAGService

DEFAULT_DATA_DIR = "data"

# Ключи — material_id (int как строка); можно править под себя.
DEFAULT_QUESTIONS: dict[str, str] = {
    "1": "Сформулируй кратко, о чём этот материал (1-2 предложения).",
    "2": "Перечисли 2-3 ключевые мысли.",
    "3": "Какой главный тезис?",
    "4": "Что важно запомнить из этого материала?",
    "5": "Сделай краткое резюме.",
    "6": "О чём это?",
    "7": "О чём это?",
    "8": "О чём это?",
    "9": "О чём это?",
    "10": "О чём это?",
}


def _normalize_ext(x: str) -> str:
    """'pdf' / '.pdf' / ' PDF ' → '.pdf'. Пустая строка = пропуск."""
    x = x.strip().lower().lstrip(".")
    return "." + x if x else ""


def _stable_id(*keys: str) -> int:
    """Стабильный int material_id из набора строк. Одинаковый вход → одинаковый id,
    разный → с большой вероятностью разный. Диапазон 0..99999.
    """
    h = hashlib.md5("|".join(keys).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100000


# ============================================================================
#  JOBS — конфиг «правишь тут → запускаешь через --mode <имя>»
# ============================================================================
#  Каждый ключ — это имя режима. Запись содержит либо `path` (локальный файл
#  в data/), либо `url` (http(s)://...), плюс вопрос. `material_id` опц.
#
#  Ключ "all" зарезервирован для auto-discovery по data/ и в JOBS не входит.
# ============================================================================
JOBS: dict[str, dict] = {
    "pdf-small": {
        "path": "data/sample.pdf",
        "question": "О чём этот документ? Сформулируй одной фразой.",
    },
    "pdf-lecture": {
        "path": "data/Лекция_№1_Модел_е_как_основной_метод_исслед_я_сложных_систем.pdf",
        "question": "Что такое структурно-функциональная модель?",
    },
    "pptx": {
        "path": "data/lomonosov.pptx",
        "question": "Расскажи про детство и юность Ломносова",
    },
    "mp3": {
        "path": "data/Магия транзисторов как мы научили компьютеры думать с помощью кусочков кремния.mp3",
        "question": "Для чего нам алюминий и для фосфор в полупроводнике?",
    },
    "mp4": {
        "path": "data/Лекция 1. Введение в машинное обучение..mp4",
        "question": "О чём эта лекция? Какие темы затронуты?",
    },
    "url": {
        "url": "https://habr.com/ru/articles/486358/",
        "question": "О чём статья? Какие ключевые идеи?",
    },
    "url-2": {
        "url": "https://educon.by/index.php/pozn/biologia/111-virus-drug-ili-vrag",
        "question": "О чём статья? Какие ключевые идеи?",
    },
    
}

ACTIVE_MODE = "auto"   # ← "auto" (= all — auto-discovery) или одно из JOBS.keys()


def discover(data_dir: Path, allowed_exts: set[str] | None = None) -> dict[int, Path]:
    """Map material_id (1..N) → путь, для файлов с поддерживаемым расширением.

    `allowed_exts` (опц.) — фильтр по расширениям в нижнем регистре с точкой:
    {".pdf", ".pptx", ...}. Если None — берём всё, что регистр знает.
    """
    files: list[Path] = []
    for p in sorted(data_dir.iterdir()):
        if not p.is_file():
            continue
        try:
            parser_registry.get_parser(p.name)
        except UnsupportedFormatError:
            continue
        if allowed_exts is not None and p.suffix.lower() not in allowed_exts:
            continue
        files.append(p)
    return {i + 1: p for i, p in enumerate(files)}


async def ingest_one(rag: RAGService, mid: int, path: Path) -> int:
    text = await download_and_extract(str(path))
    return await rag.index_material(mid, text)


async def ask_one(rag: RAGService, mid: int, question: str, task_id: str,
                  retrieve_n: int | None = None, rerank: bool = False) -> dict:
    task: dict = {
        "task_id": task_id,
        "type": "rag_question",
        "material_id": mid,
        "question": question,
    }
    if retrieve_n is not None:
        task["retrieve_n"] = retrieve_n
    if rerank:
        task["rerank"] = True
    return await process_question(task, rag)


def truncate(s: str, n: int = 4000) -> str:
    """Печатает первые `n` символов ответа. Лимит — чисто визуальный в demo;
    модель отдаёт полный ответ в `result['answer']`, см. ниже.
    """
    return s if len(s) <= n else s[:n] + "..."


async def run_auto(args: argparse.Namespace) -> None:
    """Режим по умолчанию: discover + ingest + question по каждому материалу."""
    data_dir = Path(args.data_dir)
    if not data_dir.is_dir():
        print(f"[ERROR] --data-dir={data_dir} не существует или не директория")
        return

    files = discover(data_dir, allowed_exts=args.extensions)
    if not files:
        print(
            f"В {data_dir} нет файлов с поддерживаемыми расширениями "
            f"(фильтр: {sorted(args.extensions) if args.extensions else 'все'}).\n"
            f"Поддерживаемые: {parser_registry.supported_extensions()}"
        )
        return

    print(f"Найдено {len(files)} файл(ов) в {data_dir}:")
    for mid, p in files.items():
        print(f"  material_id={mid:<3}  →  {p.name}")
    print()

    rag = RAGService()

    print("=== INGEST ===")
    ingested: dict[int, Path] = {}
    for mid, path in files.items():
        if await rag.has_material(mid):
            print(f"  [CACHED] material={mid:<3}  {path.name:<45}  → already in store, skip")
            ingested[mid] = path
            continue
        try:
            n = await ingest_one(rag, mid, path)
            print(f"  [OK]   material={mid:<3}  {path.name:<45}  → {n} чанков")
            ingested[mid] = path
        except UnsupportedFormatError as e:
            print(f"  [SKIP] material={mid:<3}  {path.name:<45}  → {e}")
        except FileNotFoundError as e:
            print(f"  [404]  material={mid:<3}  {path.name:<45}  → {e}")
        except Exception as e:
            print(f"  [FAIL] material={mid:<3}  {path.name:<45}  → {type(e).__name__}: {e}")

    materials = sorted(ingested)
    if args.material is not None:
        if args.material not in materials:
            print(f"\n[ERROR] --material={args.material} нет среди проиндексированных: {materials}")
            return
        materials = [args.material]

    print("\n=== QUESTION ===")
    for mid in materials:
        question = args.question or DEFAULT_QUESTIONS.get(str(mid), "О чём этот материал?")
        print(f"\n— material {mid} ({ingested[mid].name})")
        print(f"  Q: {question}")
        result = await ask_one(
            rag, mid, question, task_id=f"q-{mid}",
            retrieve_n=args.retrieve_n, rerank=args.rerank,
        )
        if result["status"] == "ok":
            print(f"  A: {truncate(result['answer'])}")
            print(f"  sources: {result['sources']}")
        else:
            print(f"  ERROR: {result['error']}")


async def run_single(args: argparse.Namespace) -> None:
    """Back-compat: один файл, один material_id, один вопрос."""
    if not args.file:
        print("[ERROR] нужен --file или оставь пустым для auto-discovery")
        return
    if args.material_id is None:
        print("[ERROR] нужен --material-id в режиме --file")
        return

    rag = RAGService()
    text = await download_and_extract(args.file)
    chunks_n = await rag.index_material(args.material_id, text)
    print(
        f"[INGEST] Проиндексировано {chunks_n} чанков из {args.file} "
        f"в material {args.material_id}"
    )

    question = args.question or DEFAULT_QUESTIONS["1"]
    result = await ask_one(
        rag, args.material_id, question, task_id="demo-single",
        retrieve_n=args.retrieve_n, rerank=args.rerank,
    )
    print(f"Q: {question}")
    if result["status"] == "ok":
        print(f"A: {truncate(result['answer'])}")
        print(f"sources: {result['sources']}")
    else:
        print(f"ERROR: {result['error']}")


async def run_url(args: argparse.Namespace) -> None:
    """--url URL → fetch HTML → extract article → index → спросить."""
    url = args.url
    mid = args.url_material_id if args.url_material_id is not None else 99
    print(f"[URL] {url}  →  material {mid}")

    rag = RAGService()
    try:
        text = await download_and_extract(url)
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {e}")
        return

    if not text.strip():
        print("  [FAIL] пустой текст после extract — trafilatura не нашёл статью")
        return

    chunks_n = await rag.index_material(mid, text)
    print(f"  [INGEST] {chunks_n} чанков ({len(text)} символов)")

    question = args.question or "О чём эта статья? Сформулируй кратко."
    print(f"  Q: {question}")
    result = await ask_one(
        rag, mid, question, task_id="demo-url",
        retrieve_n=args.retrieve_n, rerank=args.rerank,
    )
    if result["status"] == "ok":
        print(f"  A: {truncate(result['answer'])}")
        print(f"  sources: {result['sources']}")
    else:
        print(f"  ERROR: {result['error']}")


async def run_job(name: str, job: dict, args: argparse.Namespace) -> None:
    """Прогон одной записи из JOBS (см. блок конфига в начале файла)."""
    question = job.get("question") or "О чём этот материал?"

    if "url" in job:
        url = job["url"]
        mid = int(job["material_id"]) if "material_id" in job else _stable_id("url", url)
        print(f"[JOB:{name}] {url}  →  material {mid}")
        rag = RAGService()
        if await rag.has_material(mid):
            print(f"  [CACHED] уже в store, пропускаем ingest")
        else:
            try:
                text = await download_and_extract(url)
            except Exception as e:
                print(f"  [FAIL] {type(e).__name__}: {e}")
                return
            if not text.strip():
                print("  [FAIL] пустой текст после extract")
                return
            chunks = await rag.index_material(mid, text)
            print(f"  [INGEST] {chunks} чанков ({len(text)} символов)")
    else:
        path = Path(job["path"])
        if not path.is_file():
            print(f"[JOB:{name}] файл не найден: {path}")
            return
        mid = int(job["material_id"]) if "material_id" in job else _stable_id("path", str(path))
        print(f"[JOB:{name}] {path.name}  →  material {mid}")
        rag = RAGService()
        if await rag.has_material(mid):
            print(f"  [CACHED] уже в store, пропускаем ingest")
        else:
            text = await download_and_extract(str(path))
            chunks = await rag.index_material(mid, text)
            print(f"  [INGEST] {chunks} чанков ({len(text)} символов)")

    print(f"  Q: {question}")
    result = await ask_one(
        rag, mid, question, task_id=f"job-{name}",
        retrieve_n=args.retrieve_n, rerank=args.rerank,
    )
    if result["status"] == "ok":
        print(f"  A: {truncate(result['answer'])}")
        print(f"  sources: {result['sources']}")
    else:
        print(f"  ERROR: {result['error']}")


async def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="RAG end-to-end demo")
    parser.add_argument(
        "mode",
        nargs="?",
        default=None,
        help=(
            "режим: один ключ из JOBS (см. начало этого файла), "
            "через запятую для нескольких, либо 'all' (= auto-discovery по data/). "
            "Если не передан — берётся ACTIVE_MODE из кода."
        ),
    )
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, type=str)
    parser.add_argument(
        "--extensions",
        type=lambda s: {_normalize_ext(x) for x in s.split(",")} - {""},
        default=None,
        help="фильтр расширений через запятую: --extensions pdf,pptx,mp3",
    )
    parser.add_argument("--question", default=None, help="ad-hoc: один вопрос на все материалы")
    parser.add_argument(
        "--material",
        type=int,
        default=None,
        help="ad-hoc: спросить только у этого material_id",
    )
    parser.add_argument("--file", default=None, help="ad-hoc: один файл (single-file режим)")
    parser.add_argument("--material-id", type=int, default=None, help="ad-hoc: material_id для --file")
    parser.add_argument(
        "--url",
        default=None,
        help="ad-hoc: URL статьи (http://... или https://...)",
    )
    parser.add_argument(
        "--url-material-id",
        type=int,
        default=None,
        help="ad-hoc: material_id для --url (по умолчанию 99)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=4,
        help="сколько чанков отдать в LLM (default 4)",
    )
    parser.add_argument(
        "--retrieve-n",
        type=int,
        default=None,
        help="сколько кандидатов взять из retriever'а (default = top_k); "
             "имеет смысл вместе с --rerank",
    )
    parser.add_argument(
        "--rerank",
        action="store_true",
        help="включить LLM-reranker поверх top-N (требует --retrieve-n > --top-k)",
    )
    args = parser.parse_args()

    # Сначала — ad-hoc флаги (если переданы, прогоняем именно их)
    if args.url:
        await run_url(args)
        return
    if args.file:
        await run_single(args)
        return

    # Режим из JOBS / ACTIVE_MODE
    mode_str = args.mode or ACTIVE_MODE
    modes = [m.strip() for m in mode_str.split(",") if m.strip()]

    # "all" / "auto" → весь auto-discovery
    if any(m in ("all", "auto") for m in modes):
        await run_auto(args)
        return

    bad = [m for m in modes if m not in JOBS]
    if bad:
        print(
            f"[ERROR] неизвестные режимы: {bad}. "
            f"Допустимо: {sorted(JOBS)} + 'all' (= auto-discovery)."
        )
        return

    for name in modes:
        await run_job(name, JOBS[name], args)


if __name__ == "__main__":
    asyncio.run(main())
