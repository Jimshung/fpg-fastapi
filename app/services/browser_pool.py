from contextlib import asynccontextmanager
from typing import List, Optional
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import asyncio
import logging
from app.core.config import settings

class BrowserPool:
    def __init__(self, max_size: int = 3):
        self.max_size = max_size
        self.pool: List[webdriver.Chrome] = []
        self.semaphore = asyncio.Semaphore(max_size)
        self.logger = logging.getLogger(__name__)
        
    async def get_driver(self) -> Optional[webdriver.Chrome]:
        async with self.semaphore:
            try:
                if len(self.pool) < self.max_size:
                    driver = self._create_driver()
                    self.pool.append(driver)
                    self.logger.info(f"Created new driver. Pool size: {len(self.pool)}")
                    return driver
                
                for driver in self.pool:
                    if self._is_driver_available(driver):
                        self.logger.info("Reusing existing driver")
                        return driver
                        
                # 如果沒有可用的driver，創建新的
                self._cleanup_inactive_drivers()
                driver = self._create_driver()
                self.pool.append(driver)
                return driver
                
            except Exception as e:
                self.logger.error(f"Error getting driver: {str(e)}")
                raise

    def _create_driver(self) -> webdriver.Chrome:
        options = self._get_browser_options()
        service = Service(settings.CHROME_DRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(10)
        return driver

    def _get_browser_options(self) -> Options:
        options = Options()
        if settings.HEADLESS_MODE:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        return options

    def _is_driver_available(self, driver: webdriver.Chrome) -> bool:
        try:
            # 檢查driver是否響應
            driver.current_url
            return True
        except:
            return False

    def _cleanup_inactive_drivers(self):
        active_drivers = []
        for driver in self.pool:
            if self._is_driver_available(driver):
                active_drivers.append(driver)
            else:
                try:
                    driver.quit()
                except:
                    pass
        self.pool = active_drivers

    @asynccontextmanager
    async def acquire(self):
        driver = await self.get_driver()
        try:
            yield driver
        finally:
            # 這裡可以選擇是否要關閉瀏覽器，或是保留供下次使用
            pass

    async def cleanup(self):
        for driver in self.pool:
            try:
                driver.quit()
            except:
                pass
        self.pool.clear()