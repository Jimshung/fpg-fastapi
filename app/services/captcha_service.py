# app/services/captcha_service.py
import os
import aiohttp
import logging
from PIL import Image
from io import BytesIO
import asyncio
from app.core.config import settings


class CaptchaService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.azure_vision_url = f"{settings.AZURE_ENDPOINT}vision/v3.2/read/analyze"
        self.captcha_analysis_delay = 2.0
        self.captcha_dimensions = (200, 100)
        self.temp_dir = os.path.join(os.path.dirname(__file__), "temp")

    async def solve_captcha(self, image_buffer: bytes) -> str:
        try:
            # 確保臨時目錄存在
            os.makedirs(self.temp_dir, exist_ok=True)

            # 記錄原始圖片
            await self._save_original_image(image_buffer)

            # 調整圖片大小
            resized_image = await self._resize_image(image_buffer)

            # 初始化分析
            operation_location = await self._initiate_analysis(resized_image)

            # 等待分析完成
            await asyncio.sleep(self.captcha_analysis_delay)

            # 獲取分析結果
            result = await self._get_analysis_result(operation_location)

            # 提取文字
            extracted_text = self._extract_text_from_result(result)

            return self._process_captcha_text(extracted_text)
        except Exception as e:
            self.logger.error(f"驗證碼解析錯誤: {str(e)}")
            return "error"
        finally:
            await self._cleanup_temp_files()

    async def _save_original_image(self, image_buffer: bytes):
        original_path = os.path.join(self.temp_dir, "captcha_original.png")
        with open(original_path, "wb") as f:
            f.write(image_buffer)

    async def _resize_image(self, image_buffer: bytes) -> bytes:
        image = Image.open(BytesIO(image_buffer))
        resized_image = image.resize(self.captcha_dimensions)

        output_buffer = BytesIO()
        resized_image.save(output_buffer, format="PNG")

        resized_path = os.path.join(self.temp_dir, "captcha_resized.png")
        with open(resized_path, "wb") as f:
            f.write(output_buffer.getvalue())

        return output_buffer.getvalue()

    async def _initiate_analysis(self, image_buffer: bytes) -> str:
        headers = {
            "Ocp-Apim-Subscription-Key": settings.AZURE_API_KEY,
            "Content-Type": "application/octet-stream",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.azure_vision_url, headers=headers, data=image_buffer
            ) as response:
                if response.status != 202:
                    raise Exception(f"未預期的響應狀態: {response.status}")

                operation_location = response.headers.get("operation-location")
                if not operation_location:
                    raise Exception("未收到 operation-location 標頭")

                return operation_location

    async def _get_analysis_result(self, operation_location: str):
        headers = {"Ocp-Apim-Subscription-Key": settings.AZURE_API_KEY}

        async with aiohttp.ClientSession() as session:
            async with session.get(operation_location, headers=headers) as response:
                return await response.json()

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

    async def _cleanup_temp_files(self):
        temp_files = ["captcha_original.png", "captcha_resized.png"]
        for filename in temp_files:
            try:
                filepath = os.path.join(self.temp_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                self.logger.error(f"清理臨時文件時發生錯誤 {filename}: {str(e)}")
