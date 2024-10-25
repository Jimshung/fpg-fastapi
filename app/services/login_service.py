"""FPG 自動化登入服務模組。"""

# Standard library imports
import logging

# Third-party imports
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Local application imports
from app.services.browser import BrowserService
from app.services.captcha_service import CaptchaService
from app.core.config import settings


class LoginService:
    """處理 FPG 網站的自動化登入流程。"""

    def __init__(self) -> None:
        """初始化登入服務。"""
        self.browser_service = BrowserService()
        self.captcha_service = CaptchaService()
        self.logger = logging.getLogger(__name__)
        self.max_retries = 5

    async def login(self) -> dict:
        """
        執行登入流程。

        Returns:
            dict: 包含登入狀態和訊息的字典。
        """
        driver = None
        try:
            self.logger.info("開始登入流程")
            driver = self.browser_service.init_driver()
            return await self.perform_login(driver)
        except WebDriverException as e:
            self.logger.error("瀏覽器操作錯誤: %s", str(e))
            return {"status": "error", "message": str(e)}
        except Exception as e:
            self.logger.error("未預期的錯誤: %s", str(e))
            return {"status": "error", "message": str(e)}
        finally:
            if driver:
                self.browser_service.close_driver()

    async def perform_login(self, driver) -> dict:
        """
        執行具體的登入操作流程。

        Args:
            driver: Selenium WebDriver 實例。

        Returns:
            dict: 包含登入狀態和訊息的字典。
        """
        try:
            self.logger.info("正在導航到登入頁面...")
            driver.get(settings.LOGIN_URL)
            await self.wait_for_page_load(driver)

            for attempt in range(self.max_retries):
                try:
                    self.logger.info("正在進行第 %d 次登入嘗試...", attempt + 1)
                    await self.fill_login_form(driver)

                    self.logger.info("開始處理驗證碼...")
                    captcha_img = driver.find_element(By.ID, "vcode")
                    captcha_buffer = await self._get_captcha_image_buffer(captcha_img)
                    captcha_text = await self.captcha_service.solve_captcha(
                        captcha_buffer
                    )

                    if captcha_text == "error":
                        self.logger.error("驗證碼解析失敗")
                        continue

                    self.logger.info("填入驗證碼: %s", captcha_text)
                    captcha_input = driver.find_element(By.NAME, "vcode")
                    captcha_input.clear()
                    captcha_input.send_keys(captcha_text)

                    success = await self.submit_form(driver)

                    if success:
                        self.logger.info("登入成功")
                        return {"status": "success", "message": "登入成功"}

                    self.logger.warning("登入失敗，準備重試")
                    driver.refresh()
                    await self.wait_for_page_load(driver)

                except Exception as e:
                    self.logger.error("登入嘗試失敗: %s", str(e))
                    if attempt == self.max_retries - 1:
                        raise

            return {
                "status": "error",
                "message": f"登入失敗，已嘗試 {self.max_retries} 次",
            }

        except TimeoutException:
            return {"status": "error", "message": "頁面載入超時"}
        except WebDriverException as e:
            self.logger.error("登入過程發生錯誤: %s", str(e))
            return {"status": "error", "message": str(e)}

    async def wait_for_page_load(self, driver) -> None:
        """
        等待頁面載入完成。

        Args:
            driver: Selenium WebDriver 實例。

        Raises:
            TimeoutException: 當頁面載入超時時拋出。
        """
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "id"))
            )
            self.logger.info("頁面載入完成")
        except TimeoutException:
            self.logger.error("頁面載入超時")
            raise

    async def fill_login_form(self, driver) -> None:
        """
        填寫登入表單。

        Args:
            driver: Selenium WebDriver 實例。

        Raises:
            WebDriverException: 當表單操作失敗時拋出。
        """
        try:
            username_field = driver.find_element(By.NAME, "id")
            password_field = driver.find_element(By.NAME, "passwd")

            username_field.clear()
            password_field.clear()

            username_field.send_keys(settings.USERNAME)
            password_field.send_keys(settings.PASSWORD)

            self.logger.info("表單填寫完成")
        except WebDriverException as e:
            self.logger.error("填寫表單時發生錯誤: %s", str(e))
            raise

    async def submit_form(self, driver) -> bool:
        """
        提交登入表單並驗證登入結果。

        Args:
            driver: Selenium WebDriver 實例。

        Returns:
            bool: 登入是否成功。
        """
        try:
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (
                        By.CSS_SELECTOR,
                        'input[type="submit"], input[type="button"][value="登入"]',
                    )
                )
            )
            submit_button.click()

            return await self.verify_login_success(driver)
        except Exception as e:
            self.logger.error("提交表單時發生錯誤: %s", str(e))
            return False

    async def verify_login_success(self, driver) -> bool:
        """
        驗證登入是否成功。

        Args:
            driver: Selenium WebDriver 實例。

        Returns:
            bool: 登入是否成功。
        """
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "menu_pos"))
            )

            menu_element = driver.find_element(By.CLASS_NAME, "menu_pos")
            menu_text = menu_element.text
            success = all(
                text in menu_text for text in ["熱訊", "標售公報", "標案管理"]
            )

            if success:
                self.logger.info("成功驗證登入狀態")
            else:
                self.logger.warning("未能找到預期的選單項目")

            return success
        except TimeoutException:
            self.logger.warning("等待選單元素超時")
            return False
        except WebDriverException as e:
            self.logger.error("驗證登入狀態時發生錯誤: %s", str(e))
            return False

    async def _get_captcha_image_buffer(self, element) -> bytes:
        """
        擷取驗證碼圖片。

        Args:
            element: Selenium WebElement 實例。

        Returns:
            bytes: 圖片的二進制數據。

        Raises:
            WebDriverException: 當擷取圖片失敗時拋出。
        """
        try:
            self.logger.info("正在擷取驗證碼圖片...")
            return element.screenshot_as_png
        except WebDriverException as e:
            self.logger.error("擷取驗證碼圖片時發生錯誤: %s", str(e))
            raise
