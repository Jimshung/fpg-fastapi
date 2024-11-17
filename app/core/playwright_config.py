from playwright.async_api import async_playwright
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

async def get_playwright_context(headless: bool = True):
    """獲取 Playwright 上下文"""
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        return context, browser, playwright
    except Exception as e:
        logger.error(f"初始化 Playwright 失敗: {str(e)}")
        raise

async def cleanup_playwright(context=None, browser=None, playwright=None):
    """清理 Playwright 資源"""
    try:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()
    except Exception as e:
        logger.error(f"清理 Playwright 資源時發生錯誤: {str(e)}") 