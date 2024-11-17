import pytest
from playwright.async_api import async_playwright
from app.core.config import settings

async def test_login_with_playwright():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # 檢查維護狀態
            await page.goto(settings.LOGIN_URL)
            maintenance = await page.query_selector('#infoBox')
            if maintenance:
                pytest.skip("系統維護中")
            
            # 測試登入流程
            await page.fill('input[name="id"]', settings.USERNAME)
            await page.fill('input[name="passwd"]', settings.PASSWORD)
            
            # 驗證碼處理
            captcha = await page.query_selector('#vcode')
            assert captcha is not None, "驗證碼元素未找到"
            
            # 其他驗證...
            
        finally:
            await browser.close() 