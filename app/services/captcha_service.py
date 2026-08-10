"""Azure OCR 驗證碼辨識（含 429 退避）。"""
from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO

import aiohttp
from PIL import Image

from app.core.config import settings


class AzureRateLimitError(Exception):
    """Azure OCR 速率限制；呼叫端應長冷卻後再試，勿立即連打。"""

    def __init__(self, retry_after: float, message: str = "Azure OCR 429") -> None:
        self.retry_after = float(retry_after)
        super().__init__(message)


def retry_after_seconds(
    headers: dict | None,
    *,
    attempt: int,
    minimum: float = 5.0,
) -> float:
    """從 Retry-After 計算等待秒數，並隨 attempt 拉高下限。"""
    raw = "5"
    if headers:
        raw = str(headers.get("Retry-After") or headers.get("retry-after") or "5")
    try:
        retry_after = float(raw)
    except ValueError:
        retry_after = minimum
    return max(retry_after, minimum * max(attempt, 1))


class CaptchaService:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        endpoint = (settings.AZURE_ENDPOINT or "").rstrip("/") + "/"
        self.azure_vision_url = f"{endpoint}vision/v3.2/read/analyze"
        self.captcha_analysis_delay = 2.0
        self.captcha_dimensions = (200, 100)
        self.temp_dir = os.path.join(os.path.dirname(__file__), "temp")
        self.max_rate_limit_retries = 6

    async def solve_captcha(self, image_buffer: bytes) -> str:
        try:
            os.makedirs(self.temp_dir, exist_ok=True)
            await self._save_original_image(image_buffer)
            resized_image = await self._resize_image(image_buffer)
            operation_location = await self._initiate_analysis(resized_image)
            result = await self._poll_analysis_result(operation_location)
            extracted_text = self._extract_text_from_result(result)
            return self._process_captcha_text(extracted_text)
        except AzureRateLimitError:
            raise
        except Exception as exc:
            self.logger.error("驗證碼解析錯誤: %s", exc)
            return "error"
        finally:
            await self._cleanup_temp_files()

    async def _save_original_image(self, image_buffer: bytes) -> None:
        original_path = os.path.join(self.temp_dir, "captcha_original.png")
        with open(original_path, "wb") as handle:
            handle.write(image_buffer)

    async def _resize_image(self, image_buffer: bytes) -> bytes:
        image = Image.open(BytesIO(image_buffer))
        resized_image = image.resize(self.captcha_dimensions)
        output_buffer = BytesIO()
        resized_image.save(output_buffer, format="PNG")
        resized_path = os.path.join(self.temp_dir, "captcha_resized.png")
        with open(resized_path, "wb") as handle:
            handle.write(output_buffer.getvalue())
        return output_buffer.getvalue()

    async def _initiate_analysis(self, image_buffer: bytes) -> str:
        headers = {
            "Ocp-Apim-Subscription-Key": settings.AZURE_API_KEY,
            "Content-Type": "application/octet-stream",
        }
        last_status = None
        last_retry_after = 5.0
        async with aiohttp.ClientSession() as session:
            for attempt in range(1, self.max_rate_limit_retries + 1):
                async with session.post(
                    self.azure_vision_url, headers=headers, data=image_buffer
                ) as response:
                    last_status = response.status
                    if response.status == 202:
                        operation_location = response.headers.get("operation-location")
                        if not operation_location:
                            raise Exception("未收到 operation-location 標頭")
                        return operation_location
                    if response.status == 429:
                        last_retry_after = retry_after_seconds(
                            response.headers, attempt=attempt
                        )
                        self.logger.warning(
                            "Azure OCR 429，等待 %.1fs 後重試（%s/%s）",
                            last_retry_after,
                            attempt,
                            self.max_rate_limit_retries,
                        )
                        await asyncio.sleep(last_retry_after)
                        continue
                    body = await response.text()
                    raise Exception(
                        f"未預期的響應狀態: {response.status} body={body[:200]}"
                    )
        if last_status == 429:
            raise AzureRateLimitError(last_retry_after)
        raise Exception(f"未預期的響應狀態: {last_status}")

    async def _poll_analysis_result(self, operation_location: str):
        headers = {"Ocp-Apim-Subscription-Key": settings.AZURE_API_KEY}
        last_retry_after = 5.0
        rate_hits = 0
        async with aiohttp.ClientSession() as session:
            for _ in range(20):
                await asyncio.sleep(self.captcha_analysis_delay)
                async with session.get(operation_location, headers=headers) as response:
                    if response.status == 429:
                        rate_hits += 1
                        last_retry_after = retry_after_seconds(
                            response.headers, attempt=rate_hits
                        )
                        self.logger.warning(
                            "Azure OCR poll 429，等待 %.1fs", last_retry_after
                        )
                        await asyncio.sleep(last_retry_after)
                        if rate_hits >= self.max_rate_limit_retries:
                            raise AzureRateLimitError(last_retry_after)
                        continue
                    result = await response.json()
                status = (result or {}).get("status")
                if status == "succeeded":
                    return result
                if status in {"failed", "error"}:
                    raise Exception(f"分析失敗。狀態: {status}")
            raise Exception("分析逾時：仍未完成")

    def _extract_text_from_result(self, result: dict) -> str:
        if not result or result.get("status") != "succeeded":
            raise Exception(f"分析失敗或未完成。狀態: {result.get('status', '未知')}")
        read_results = result.get("analyzeResult", {}).get("readResults", [])
        if not read_results:
            raise Exception("分析結果中未找到文字行")
        lines = read_results[0].get("lines", [])
        return " ".join(line.get("text", "") for line in lines)

    def _process_captcha_text(self, text: str) -> str:
        cleaned_text = "".join(filter(str.isdigit, text))
        return cleaned_text if self._is_valid_captcha(cleaned_text) else "error"

    def _is_valid_captcha(self, text: str) -> bool:
        return len(text) == 4 and text.isdigit()

    async def _cleanup_temp_files(self) -> None:
        for filename in ("captcha_original.png", "captcha_resized.png"):
            try:
                filepath = os.path.join(self.temp_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as exc:
                self.logger.error("清理臨時文件時發生錯誤 %s: %s", filename, exc)
