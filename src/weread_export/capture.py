from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CANVAS_HOOK = r"""
(() => {
  window.__wr_chars = [];
  const originalFillText = CanvasRenderingContext2D.prototype.fillText;
  CanvasRenderingContext2D.prototype.fillText = function(text, x, y) {
    if (text && String(text).trim()) {
      const rect = this.canvas.getBoundingClientRect();
      const side = rect.left < (window.innerWidth / 2) ? "left" : "right";
      window.__wr_chars.push({
        canvas: this.canvas,
        text: String(text),
        x: Math.round(Number(x) * 10) / 10,
        y: Math.round(Number(y) * 10) / 10,
        side,
        canvasLeft: Math.round(rect.left),
        canvasTop: Math.round(rect.top)
      });
    }
    return originalFillText.apply(this, arguments);
  };
  window.__wr_reset = () => { window.__wr_chars = []; };
  window.__wr_count = () => window.__wr_chars.length;
})();
"""

VISIBLE_IMAGES_JS = r"""
() => {
  const output = [];
  const width = window.innerWidth;
  const height = window.innerHeight;
  document.querySelectorAll('img[class*="wr_readerImage"], img[src*="res.weread.qq.com/wrepub"]').forEach((img) => {
    const src = img.currentSrc || img.src || img.getAttribute("data-src") || "";
    if (!src.includes("res.weread.qq.com/wrepub")) return;
    const rect = img.getBoundingClientRect();
    const style = getComputedStyle(img);
    if (rect.width < 20 || rect.height < 20) return;
    if (rect.bottom <= 0 || rect.top >= height || rect.right <= 0 || rect.left >= width) return;
    if (style.display === "none" || style.visibility === "hidden") return;
    output.push({
      src,
      top: Math.round(rect.top),
      left: Math.round(rect.left),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    });
  });
  return output;
}
"""


@dataclass(frozen=True)
class CanvasChar:
    text: str
    x: float
    y: float
    side: str = "left"

    @classmethod
    def from_js(cls, item: dict[str, Any]) -> "CanvasChar":
        return cls(
            text=str(item.get("text") or item.get("t") or ""),
            x=float(item.get("x", 0)),
            y=float(item.get("y", 0)),
            side=str(item.get("side") or "left"),
        )


async def read_canvas_chars(page: Any) -> list[CanvasChar]:
    raw = await page.evaluate(r"""
() => (window.__wr_chars || []).flatMap(({canvas, ...item}) => {
  if (!canvas) return [item];
  const rect = canvas.getBoundingClientRect();
  const style = getComputedStyle(canvas);
  if (!canvas.isConnected || rect.width <= 0 || rect.height <= 0
      || rect.right <= 0 || rect.left >= innerWidth
      || rect.bottom <= 0 || rect.top >= innerHeight
      || style.display === 'none' || style.visibility === 'hidden') return [];
  return [{...item, side: rect.left < innerWidth / 2 ? 'left' : 'right'}];
})
""")
    return [CanvasChar.from_js(item) for item in raw if item.get("text") or item.get("t")]


async def reset_canvas_chars(page: Any) -> None:
    await page.evaluate("() => window.__wr_reset && window.__wr_reset()")


async def read_visible_images(page: Any) -> list[dict[str, Any]]:
    return list(await page.evaluate(VISIBLE_IMAGES_JS))

