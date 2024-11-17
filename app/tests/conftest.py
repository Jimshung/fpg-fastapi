import pytest
from playwright.async_api import async_playwright
from app.core.playwright_config import get_playwright_context, cleanup_playwright

@pytest.fixture(scope="function")
async def playwright_context():
    """Playwright 上下文 fixture"""
    context, browser, playwright = await get_playwright_context()
    yield context
    await cleanup_playwright(context, browser, playwright)

@pytest.fixture(scope="function")
async def playwright_page(playwright_context):
    """Playwright 頁面 fixture"""
    page = await playwright_context.new_page()
    yield page
    await page.close() 