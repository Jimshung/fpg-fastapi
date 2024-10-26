from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from app.core.config import settings
import logging


class BrowserService:
    def __init__(self):
        self.driver = None
        self.logger = logging.getLogger(__name__)

    def init_driver(self):
        try:
            options = self.get_browser_options()
            service = Service(settings.CHROME_DRIVER_PATH)
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.implicitly_wait(10)
            self.logger.info("瀏覽器初始化成功")
            return self.driver
        except Exception as e:
            self.logger.error(f"瀏覽器初始化失敗: {str(e)}")
            raise

    def get_browser_options(self):
        options = Options()
        if settings.HEADLESS_MODE:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        return options

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("瀏覽器已關閉")
            except Exception as e:
                self.logger.error(f"關閉瀏覽器時發生錯誤: {str(e)}")
