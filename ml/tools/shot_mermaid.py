"""Отрендерить mermaid-блоки из .md в PNG (по одному файлу на диаграмму).

Запуск: python -m tools.shot_mermaid <path-to.md> <out-dir>
"""

import asyncio
import json
import re
import sys
from pathlib import Path

from playwright.async_api import async_playwright

TPL = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>body{background:#fff;margin:0;padding:16px;font-family:sans-serif}</style>
</head><body><div id="host"></div>
<script>
mermaid.initialize({startOnLoad:false});
(async () => {
  const blocks = __BLOCKS__;
  const host = document.getElementById('host');
  for (let i = 0; i < blocks.length; i++) {
    const {svg} = await mermaid.render('m' + i, blocks[i]);
    const d = document.createElement('div');
    d.id = 'diagram-' + i;
    d.style.marginBottom = '24px';
    d.innerHTML = svg;
    host.appendChild(d);
  }
  window.__DONE__ = true;
})();
</script></body></html>"""


async def main(path: str, out_dir: str) -> None:
    md = Path(path).read_text(encoding="utf-8")
    blocks = re.findall(r"```mermaid\n(.*?)```", md, re.S)
    html = TPL.replace("__BLOCKS__", json.dumps(blocks, ensure_ascii=False))
    tmp = Path(path).with_suffix(".shot.html")
    tmp.write_text(html, encoding="utf-8")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1400, "height": 1000})
        await page.goto(tmp.resolve().as_uri())
        await page.wait_for_function("window.__DONE__ === true", timeout=60000)
        for i in range(len(blocks)):
            el = await page.query_selector(f"#diagram-{i}")
            await el.screenshot(path=str(out / f"diagram-{i + 1}.png"))
            print(f"сохранено: {out / f'diagram-{i + 1}.png'}")
        await browser.close()
    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2]))
