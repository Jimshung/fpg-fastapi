"""
瀏覽器服務模組。
"""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from app.core.config import settings
import logging
import platform
import os
import json

class BrowserService:
    def __init__(self):
        self.driver = None
        self.logger = logging.getLogger(__name__)

    def init_driver(self, headless: bool = None):
        """
        初始化 Chrome WebDriver
        Args:
            headless: 可選參數，覆蓋配置文件中的設定
        """
        try:
            # 記錄環境信息
            is_github_actions = bool(os.getenv('GITHUB_ACTIONS'))
            self.logger.info(f"運行環境: {'GitHub Actions' if is_github_actions else 'Local'}")
            self.logger.info(f"操作系統: {platform.system()} {platform.version()}")
            self.logger.info(f"Python 版本: {platform.python_version()}")
            
            options = Options()
            
            # 基本設置
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            
            # 效能優化
            options.add_argument('--disable-gpu')  # 在無頭模式下禁用 GPU
            options.add_argument('--disable-software-rasterizer')
            options.add_argument('--disable-extensions')  # 禁用擴展
            options.add_argument('--disable-infobars')   # 禁用信息欄
            options.add_argument('--disable-notifications')  # 禁用通知
            options.add_argument('--disable-popup-blocking')  # 禁用彈窗阻擋
            
            # 記憶體優化
            options.add_argument('--disable-dev-tools')
            options.add_argument('--disable-logging')
            options.add_argument('--silent')
            options.add_argument('--log-level=3')
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            # 記錄 Chrome 選項
            self.logger.info("Chrome 選項配置:")
            for arg in options.arguments:
                self.logger.info(f"  - {arg}")
            
            # 根據環境和設定決定是否使用 headless 模式
            use_headless = headless if headless is not None else (settings.HEADLESS_MODE or is_github_actions)
            if use_headless:
                self.logger.info(f"使用無頭模式運行瀏覽器 (原因: {'CI 環境' if is_github_actions else '配置設定'})")
                options.add_argument('--headless=new')
            else:
                self.logger.info("使用有頭模式運行瀏覽器")
            
            # 使用系統安裝的 ChromeDriver
            if platform.system() == 'Darwin':  # macOS
                driver_path = '/opt/homebrew/bin/chromedriver'  # Mac 的 Homebrew 安裝路徑
                self.logger.info("檢測到 macOS 系統")
            else:  # Linux (包括 GitHub Actions)
                driver_path = '/usr/local/bin/chromedriver'  # Linux 的預設路徑
                self.logger.info("檢測到 Linux 系統")
                
            self.logger.info(f"使用系統 ChromeDriver: {driver_path}")
            
            # 檢查 ChromeDriver 是否存在
            if not os.path.exists(driver_path):
                self.logger.warning(f"ChromeDriver 不存在於路徑: {driver_path}")
                self.logger.info("嘗試在系統 PATH 中查找 ChromeDriver")
                import shutil
                chromedriver_path = shutil.which('chromedriver')
                if chromedriver_path:
                    driver_path = chromedriver_path
                    self.logger.info(f"在系統中找到 ChromeDriver: {driver_path}")
                else:
                    self.logger.error("在系統中找不到 ChromeDriver")
                    raise FileNotFoundError("ChromeDriver not found in system")

            # 確保 ChromeDriver 有執行權限
            if not os.access(driver_path, os.X_OK):
                self.logger.warning(f"ChromeDriver ({driver_path}) 沒有執行權限，正在嘗試設定...")
                try:
                    os.chmod(driver_path, 0o755)
                    self.logger.info("成功設定 ChromeDriver 執行權限")
                except Exception as e:
                    self.logger.error(f"設定 ChromeDriver 權限失敗: {e}")
                    raise
            
            service = Service(executable_path=driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.implicitly_wait(10)
            self.driver.set_page_load_timeout(30)  # 設置頁面加載超時
            
            # 設錄瀏覽器信息
            browser_info = {
                "瀏覽器版本": self.driver.capabilities['browserVersion'],
                "ChromeDriver版本": self.driver.capabilities['chrome']['chromedriverVersion'].split()[0],
                "用戶數據目錄": self.driver.capabilities['chrome']['userDataDir'],
                "平台": self.driver.capabilities['platformName']
            }
            self.logger.info(f"瀏覽器信息: {json.dumps(browser_info, ensure_ascii=False, indent=2)}")
            
            self.logger.info(f"瀏覽器初始化成功 (Headless: {settings.HEADLESS_MODE})")
            return self.driver
            
        except Exception as e:
            self.logger.error(f"瀏覽器初始化失敗: {str(e)}")
            # 記錄更詳細的錯誤信息
            import traceback
            self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
            raise

    def close_driver(self):
        """關閉 WebDriver"""
        if self.driver:
            try:
                session_id = self.driver.session_id
                self.driver.quit()
                self.logger.info(f"瀏覽器已關閉 (Session ID: {session_id})")
            except Exception as e:
                self.logger.error(f"關閉瀏覽器時發生錯誤: {str(e)}")
                import traceback
                self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
