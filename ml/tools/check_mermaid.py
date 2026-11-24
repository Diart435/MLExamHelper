"""Проверить, что mermaid-блоки в .md файле реально рендерятся.

Запуск: python -m tools.check_mermaid <path-to.md>
Открывает страницу в браузере (playwright) и печатает результат по каждой диаграмме.
"""

import asyncio
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

TPL = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
</head><body>
<div id="out"></div>
<script>
const blocks = __BLOCKS__;
mermaid.initialize({startOnLoad:false});
(async () => {
  const res = [];
  for (let i = 0; i < blocks.length; i++) {
    try {
      const {svg} = await mermaid.render('m' + i, blocks[i]);
      res.push({i: i + 1, ok: true, len: svg.length});
    } catch (e) {
      res.push({i: i + 1, ok: false, err: String(e && e.message || e)});
    }
  }
  window.__RESULT__ = JSON.stringify(res);
})();
</script></body></html>"""


async def main(path: str) -> int:
    md = Path(path).read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", md, re.S)
    print(f"найдено mermaid-блоков: {len(blocks)}")
    html = TPL.replace("__BLOCKS__", repr(blocks).replace("'", '"', 0))
    # безопасно кладём JSON вместо python-литерала
    import json
    html = TPL.replace("__BLOCKS__", json.dumps(blocks, ensure_ascii=False))

    out = Path(path).with_suffix(".mermaid-check.html")
    out.write_text(html, encoding="utf-8")

    url = out.resolve().as_uri()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_function("window.__RESULT__ !== undefined", timeout=60000)
        raw = await page.evaluate("window.__RESULT__")
        await browser.close()

    out.unlink(missing_ok=True)
    res = json.loads(raw)
    bad = 0
    for r in res:
        if r["ok"]:
            print(f"  блок {r['i']}: ok ({r['len']} символов svg)")
        else:
            bad += 1
            print(f"  блок {r['i']}: ОШИБКА — {r['err'][:400]}")
    print("итог:", "все ок" if bad == 0 else f"{bad} с ошибками")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1])))
