from typing import Optional
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from app.services.browser_pool import BrowserPool
from app.services.captcha_service import CaptchaService
from app.core.config import settings
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

class EnhancedLoginService:
    def __init__(self, browser_pool: Optional[BrowserPool] = None,
                 captcha_service: Optional[CaptchaService] = None):
        self.browser_pool = browser_pool or BrowserPool()
        self.captcha_service = captcha_service or CaptchaService()
        self.logger = logging.getLogger(__name__)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def login(self) -> dict:
        """
        執行登入流程，使用瀏覽器池和重試機制
        """
        async with self.browser_pool.acquire() as driver:
            try:
                return await self._perform_login(driver)
            except Exception as e:
                self.logger.error(f"Login failed: {str(e)}")
                raise

    async def _perform_login(self, driver: WebDriver) -> dict:
        try:
            await self._navigate_to_login(driver)
            await self._fill_credentials(driver)
            captcha_text = await self._handle_captcha(driver)
            
            if captcha_text == "error":
                return {"status": "error", "message": "驗證碼解析失敗"}

            success = await self._submit_and_verify(driver, captcha_text)
            return {
                "status": "success" if success else "error",
                "message": "登入成功" if success else "登入失敗"
            }

        except TimeoutException:
            return {"status": "error", "message": "頁面載入超時"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _navigate_to_login(self, driver: WebDriver):
        driver.get(settings.LOGIN_URL)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "id"))
        )

    async def _fill_credentials(self, driver: WebDriver):
        username_field = driver.find_element(By.NAME, "id")
        password_field = driver.find_element(By.NAME, "passwd")
        
        username_field.clear()
        password_field.clear()
        
        username_field.send_keys(settings.USERNAME)
        password_field.send_keys(settings.PASSWORD)

    async def _handle_captcha(self, driver: WebDriver) -> str:
        captcha_img = driver.find_element(By.ID, "vcode")
        captcha_buffer = captcha_img.screenshot_as_png
        return await self.captcha_service.solve_captcha(captcha_buffer)

    async def _submit_and_verify(self, driver: WebDriver, captcha_text: str) -> bool:
        captcha_input = driver.find_element(By.NAME, "vcode")
        captcha_input.clear()
        captcha_input.send_keys(captcha_text)

        submit_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 
                'input[type="submit"], input[type="button"][value="登入"]'))
        )
        submit_button.click()

        try:
            menu_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "menu_pos"))
            )
            return all(text in menu_element.text 
                      for text in ["熱訊", "標售公報", "標案管理"])
        except:
            return False