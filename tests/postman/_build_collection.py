"""Сборка Postman Collection v2.1 из YAML-коллекции Postman Desktop.

Запуск:  python tests/postman/_build_collection.py
Источник: tests/postman/Exam Stand — ML ↔ backend (контракт v4.1)/
Результат: tests/postman/exam-stand.postman_collection.json
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    raise SystemExit("Нужна pyyaml: pip install pyyaml")

BASE = Path(__file__).resolve().parent
SRC = BASE / "Exam Stand — ML ↔ backend (контракт v4.1)"
OUT = BASE / "exam-stand.postman_collection.json"


def load_yaml(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def split_script(code: str) -> list[str]:
    """Строка кода -> массив строк. Сохраняем пустые строки, убираем хвостовые пробелы."""
    lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # YAML block scalar |- не даёт лишнего завершающего \n, но подстрахуемся
    if lines and lines[-1] == "":
        lines.pop()
    return [line.rstrip() for line in lines]


def split_url(raw: str) -> dict:
    """Разбираем raw URL на host/path для Postman."""
    out = {"raw": raw}
    if not raw:
        return out
    without_scheme = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", raw)
    host_part, _, path_part = without_scheme.partition("/")
    out["host"] = [host_part] if host_part else []
    out["path"] = [seg for seg in path_part.split("/") if seg != ""] if path_part else []
    if "?" in raw:
        out["path"] = out["path"][:-1] if out["path"] and raw.endswith("?") else out["path"]
    return out


def is_json_body(content: str) -> bool:
    stripped = content.strip()
    if not stripped:
        return False
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return False
    try:
        json.loads(stripped)
    except Exception:
        # тело с плейсхолдерами ({{answersJson}}) не парсится — считаем json
        return "{{" in stripped
    return True


def build_body(body: dict | None) -> dict | None:
    if not body:
        return None
    btype = body.get("type")
    if btype == "text":
        content = body.get("content") or ""
        language = "json" if is_json_body(content) else "text"
        return {
            "mode": "raw",
            "raw": content,
            "options": {"raw": {"language": language}},
        }
    if btype == "formdata":
        entries = []
        for entry in body.get("content") or []:
            etype = entry.get("type", "text")
            if etype == "file":
                entries.append({
                    "key": entry.get("key", ""),
                    "type": "file",
                    "src": entry.get("src", ""),
                })
            else:
                entries.append({
                    "key": entry.get("key", ""),
                    "value": str(entry.get("value", "")),
                    "type": "text",
                })
        return {"mode": "formdata", "formdata": entries}
    raise SystemExit(f"Неизвестный тип body: {btype!r}")


def build_headers(headers: dict | None) -> list[dict]:
    out = []
    for key, value in (headers or {}).items():
        if value is None:
            continue
        value = str(value)
        if value.strip() == "":
            continue
        out.append({"key": key, "value": value})
    return out


def build_events(scripts: list[dict] | None) -> list[dict]:
    events = []
    for script in scripts or []:
        stype = script.get("type")
        listen = {"beforeRequest": "prerequest", "afterResponse": "test"}.get(stype)
        if listen is None:
            raise SystemExit(f"Неизвестный тип скрипта: {stype!r}")
        events.append({
            "listen": listen,
            "script": {
                "type": script.get("language", "text/javascript"),
                "exec": split_script(script.get("code", "")),
            },
        })
    return events


def main() -> None:
    definition = load_yaml(SRC / ".resources" / "definition.yaml")
    collection_name = "Exam Stand — ML ↔ backend (контракт v4.1)"

    requests = []
    for path in sorted(SRC.glob("*.request.yaml")):
        data = load_yaml(path)
        data["__file__"] = path.name[: -len(".request.yaml")]
        requests.append(data)

    requests.sort(key=lambda r: r.get("order", 0))

    items = []
    for data in requests:
        name = data.get("name") or data["__file__"]
        raw_url = data.get("url", "")
        if isinstance(raw_url, dict):  # на всякий случай
            raw_url = raw_url.get("raw", "")
        request = {
            "method": data.get("method", "GET"),
            "header": build_headers(data.get("headers")),
        }
        body = build_body(data.get("body"))
        if body is not None:
            request["body"] = body
        request["url"] = split_url(raw_url)
        if data.get("description") is not None:
            request["description"] = data["description"]

        item = {"name": name, "request": request}
        events = build_events(data.get("scripts"))
        if events:
            item["event"] = events
        items.append(item)

    variables = [
        {"key": key, "value": str(value), "type": "string"}
        for key, value in (definition.get("variables") or {}).items()
    ]

    collection = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": collection_name,
            "description": definition.get("description", ""),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "variable": variables,
        "auth": {"type": "noauth"},
    }

    # newline="\n" — LF-only, без BOM (Postman не переваривает BOM)
    with OUT.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(collection, ensure_ascii=False, indent=2) + "\n")
    print(f"Записано: {OUT}")
    print(f"Пунктов: {len(items)}")
    for i in items:
        print("  -", i["name"])


def path_name_of(data: dict) -> str:
    return data.get("__file__", "")




if __name__ == "__main__":
    main()
