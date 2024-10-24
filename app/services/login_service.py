from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from app.services.browser import BrowserService
from app.core.config import settings
import logging

class LoginService:
    def __init__(self):
        self.browser_service = BrowserService()
        self.logger = logging.getLogger(__name__)
        self.max_retries = 5

    async def login(self):
        driver = None
        try:
            driver = self.browser_service.init_driver()
            return await self.perform_login(driver)  # 移除下劃線
        except Exception as e:
            self.logger.error(f"登入過程發生錯誤: {str(e)}")
            return {"status": "error", "message": str(e)}
        finally:
            if driver:
                self.browser_service.close_driver()

    async def perform_login(self, driver):  # 移除下劃線
        try:
            # 導航到登入頁面
            self.logger.info("正在導航到登入頁面...")
            driver.get(settings.LOGIN_URL)
            await self.wait_for_page_load(driver)

            # 填寫表單
            self.logger.info("正在填寫登入表單...")
            await self.fill_login_form(driver)
            
            # 驗證碼處理
            self.logger.warning("驗證碼處理功能尚未實作")
            captcha_input = driver.find_element(By.NAME, "vcode")
            captcha_input.send_keys("1234")  # 暫時填入假的驗證碼
            
            # 提交表單
            self.logger.info("正在提交表單...")
            success = await self.submit_form(driver)
            
            if not success:
                return {"status": "error", "message": "登入失敗：驗證碼可能不正確"}
            
            return {"status": "success", "message": "登入成功"}

        except Exception as e:
            self.logger.error(f"登入過程發生錯誤: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def wait_for_page_load(self, driver):  # 移除下劃線
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "id"))
            )
        except TimeoutException:
            self.logger.error("頁面加載超時")
            raise

    async def fill_login_form(self, driver):  # 移除下劃線
        try:
            username_field = driver.find_element(By.NAME, "id")
            password_field = driver.find_element(By.NAME, "passwd")
            
            username_field.send_keys(settings.USERNAME)
            password_field.send_keys(settings.PASSWORD)
            
            self.logger.info("表單填寫完成")
        except Exception as e:
            self.logger.error(f"填寫表單時發生錯誤: {str(e)}")
            raise

    async def submit_form(self, driver):  # 移除下劃線
        try:
            submit_button = driver.find_element(
                By.CSS_SELECTOR, 
                'input[type="submit"], input[type="button"][value="登入"]'
            )
            submit_button.click()
            
            return await self.verify_login_success(driver)
        except Exception as e:
            self.logger.error(f"提交表單時發生錯誤: {str(e)}")
            return False

    async def verify_login_success(self, driver):  # 移除下劃線
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "menu_pos"))
            )
            
            menu_element = driver.find_element(By.CLASS_NAME, "menu_pos")
            menu_text = menu_element.text
            return all(text in menu_text for text in ["熱訊", "標售公報", "標案管理"])
        except Exception:
            return False