"""
瀏覽器服務模組。
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from app.core.config import settings
import logging
import platform

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
            
            # 根據作業系統和環境選擇適當的 ChromeDriver
            if platform.system() == 'Darwin':  # macOS
                driver_path = ChromeDriverManager().install()
                service = Service(executable_path=driver_path)
                self.driver = webdriver.Chrome(service=service, options=options)
            elif platform.system() == 'Linux':  # Linux (包括 GitHub Actions)
                # 使用系統安裝的 ChromeDriver
                service = Service(executable_path='/usr/local/bin/chromedriver')
                self.driver = webdriver.Chrome(service=service, options=options)
            else:  # Windows 或其他系統
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
