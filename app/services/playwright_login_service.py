from playwright.async_api import async_playwright
from app.core.config import settings
import logging
import os
from datetime import datetime

class PlaywrightLoginService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.browser = None
        self.page = None
        self.playwright = None
        
        # 確保 screenshots 目錄存在
        os.makedirs("screenshots", exist_ok=True)

    async def init_browser(self):
        """初始化瀏覽器"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.page = await self.browser.new_page()
            self.logger.info("Playwright 瀏覽器初始化成功")
        except Exception as e:
            self.logger.error(f"Playwright 瀏覽器初始化失敗: {str(e)}")
            raise

    async def check_maintenance(self):
        """檢查系統是否在維護中"""
        try:
            maintenance_box = await self.page.query_selector('#infoBox')
            if maintenance_box:
                maintenance_text = await maintenance_box.inner_text()
                if "進行主機維護與更新" in maintenance_text:
                    self.logger.warning("系統目前正在維護中")
                    await self.page.screenshot(path="screenshots/maintenance.png")
                    return True
            return False
        except Exception as e:
            self.logger.error(f"檢查維護狀態時發生錯誤: {str(e)}")
            return False

    async def login(self) -> dict:
        """執行登入流程"""
        try:
            if not self.page:
                await self.init_browser()
                
            # 訪問登入頁面
            self.logger.info(f"正在訪問登入頁面: {settings.LOGIN_URL}")
            await self.page.goto(settings.LOGIN_URL)
            
            # 檢查維護狀態
            if await self.check_maintenance():
                return {"status": "error", "message": "系統維護中"}
            
            # 等待頁面加載
            await self.page.wait_for_load_state('networkidle')
            
            # 截圖保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            await self.page.screenshot(path=f"screenshots/login_page_{timestamp}.png")
            
            # 填寫表單
            await self.page.fill('input[name="id"]', settings.USERNAME)
            await self.page.fill('input[name="passwd"]', settings.PASSWORD)
            self.logger.info("已填寫登入表單")
            
            # 獲取驗證碼圖片
            captcha_element = await self.page.query_selector('#vcode')
            if captcha_element:
                await captcha_element.screenshot(path=f"screenshots/captcha_{timestamp}.png")
                self.logger.info("已保存驗證碼圖片")
                # TODO: 處理驗證碼
            
            return {"status": "success", "message": "登入表單填寫完成"}
            
        except Exception as e:
            self.logger.error(f"登入失敗: {str(e)}")
            if self.page:
                await self.page.screenshot(path=f"screenshots/login_error_{timestamp}.png")
            return {"status": "error", "message": str(e)}
        
    async def cleanup(self):
        """清理資源"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.logger.info("Playwright 資源已清理")
        except Exception as e:
            self.logger.error(f"清理資源時發生錯誤: {str(e)}")

    async def __aenter__(self):
        """異步上下文管理器進入"""
        await self.init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """異步上下文管理器退出"""
        await self.cleanup()