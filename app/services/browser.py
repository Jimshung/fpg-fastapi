"""
瀏覽器服務模組。

TODO: 未來優化方向
- 加入容器化支援 (Docker + Selenium Grid)
- 改善錯誤處理機制
- 增加更多瀏覽器選項配置
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings
import logging

class BrowserService:
    def __init__(self):
        self.driver = None
        self.logger = logging.getLogger(__name__)

    def init_driver(self):
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--headless=new')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            
            if settings.ENVIRONMENT == "ci":
                # 在 GitHub Actions 中使用系統安裝的 ChromeDriver
                self.driver = webdriver.Chrome(options=options)
            else:
                # 本地開發環境使用 webdriver_manager
                driver_path = ChromeDriverManager().install()
                service = Service(executable_path=driver_path)
                self.driver = webdriver.Chrome(service=service, options=options)
                
            self.driver.implicitly_wait(10)
            self.logger.info("瀏覽器初始化成功")
            return self.driver
        except Exception as e:
            self.logger.error(f"瀏覽器初始化失敗: {str(e)}")
            raise

    def close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("瀏覽器已關閉")
            except Exception as e:
                self.logger.error(f"關閉瀏覽器時發生錯誤: {str(e)}")
