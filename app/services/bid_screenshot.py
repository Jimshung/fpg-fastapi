"""把 FPG 報價單 HTML 轉成截圖（Playwright）；瀏覽器只在用到時才載入。"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

JPEG_QUALITY = 80
VIEWPORT = {"width": 1100, "height": 900}


class BidScreenshotter:
    """async with 進入後可重複 capture；cookies 來自已登入的 HTTP session。"""

    def __init__(self, *, base_url: str, cookies: list[dict]) -> None:
        self._base_url = base_url.rstrip("/")
        self._cookies = cookies
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self) -> "BidScreenshotter":
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        try:
            # 優先用機器內建的 Chrome（Actions 的 ubuntu 映像檔已預裝，免下載）
            self._browser = await self._playwright.chromium.launch(channel="chrome")
        except Exception:  # pylint: disable=broad-exception-caught
            # 沒有 Chrome 時退回 Playwright 自帶的 Chromium（需先 playwright install chromium）
            self._browser = await self._playwright.chromium.launch()
        self._context = await self._browser.new_context(viewport=VIEWPORT)
        await self._context.add_cookies(self._cookies)
        return self

    async def __aexit__(self, *exc) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def capture(self, html: str, out_path: Path, *, page_dir: str = "/j202/his/") -> Path:
        """html 內相對路徑（CSS／圖）以 page_dir 為基準載入。"""
        base = f'<base href="{self._base_url}{page_dir}">'
        lowered = html.lower()
        idx = lowered.find("<head>")
        if idx >= 0:
            html = html[: idx + 6] + base + html[idx + 6 :]
        else:
            html = base + html
        page = await self._context.new_page()
        try:
            await page.set_content(html, wait_until="networkidle")
            await page.screenshot(
                path=str(out_path), full_page=True, type="jpeg", quality=JPEG_QUALITY
            )
        finally:
            await page.close()
        return out_path


def cookies_from_jar(jar, base_url: str) -> list[dict]:
    host = urlsplit(base_url).hostname or ""
    return [
        {"name": m.key, "value": m.value, "domain": host, "path": "/"} for m in jar
    ]
