"""本機 ddddocr 驗證碼辨識。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional


class CaptchaService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._ocr: Optional[Any] = None

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            import ddddocr

            # show_ad=False：關閉啟動廣告輸出
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    async def solve_captcha(self, image_buffer: bytes) -> str:
        try:
            raw = await asyncio.to_thread(self._classify, image_buffer)
            return self._process_captcha_text(raw or "")
        except Exception as exc:
            self.logger.error("驗證碼解析錯誤: %s", exc)
            return "error"

    def _classify(self, image_buffer: bytes) -> str:
        return self._get_ocr().classification(image_buffer)

    def _process_captcha_text(self, text: str) -> str:
        cleaned_text = "".join(ch for ch in text if ch.isdigit())
        return cleaned_text if self._is_valid_captcha(cleaned_text) else "error"

    def _is_valid_captcha(self, text: str) -> bool:
        return len(text) == 4 and text.isdigit()
