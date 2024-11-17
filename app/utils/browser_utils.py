from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from playwright.async_api import Page, ElementHandle
import logging
import os
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class BrowserUtils:
    """通用瀏覽器工具類"""
    
    @staticmethod
    async def wait_for_element(driver_or_page, selector: str, timeout: int = 10):
        """等待元素出現（支援 Selenium 和 Playwright）"""
        try:
            if isinstance(driver_or_page, Page):
                # Playwright
                element = await driver_or_page.wait_for_selector(
                    selector, 
                    timeout=timeout * 1000,
                    state='visible'
                )
                return element
            else:
                # Selenium
                element = WebDriverWait(driver_or_page, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return element
        except Exception as e:
            logger.error(f"等待元素 {selector} 超時: {str(e)}")
            return None

    @staticmethod
    async def click_element(driver_or_page, selector: str):
        """點擊元素（支援 Selenium 和 Playwright）"""
        try:
            if isinstance(driver_or_page, Page):
                # Playwright
                element = await driver_or_page.query_selector(selector)
                if element:
                    await element.click()
                    return True
            else:
                # Selenium
                element = driver_or_page.find_element(By.CSS_SELECTOR, selector)
                element.click()
                return True
            return False
        except Exception as e:
            logger.error(f"點擊元素失敗 {selector}: {str(e)}")
            return False

    @staticmethod
    async def fill_input(driver_or_page, selector: str, value: str):
        """填寫輸入框（支援 Selenium 和 Playwright）"""
        try:
            if isinstance(driver_or_page, Page):
                # Playwright
                await driver_or_page.fill(selector, value)
            else:
                # Selenium
                element = driver_or_page.find_element(By.CSS_SELECTOR, selector)
                element.clear()
                element.send_keys(value)
            return True
        except Exception as e:
            logger.error(f"填寫輸入框失敗 {selector}: {str(e)}")
            return False

    @staticmethod
    async def take_screenshot(driver_or_page, name: str):
        """截圖（支援 Selenium 和 Playwright）"""
        try:
            screenshots_dir = "screenshots"
            os.makedirs(screenshots_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = os.path.join(screenshots_dir, filename)
            
            if isinstance(driver_or_page, Page):
                # Playwright
                await driver_or_page.screenshot(path=filepath)
            else:
                # Selenium
                driver_or_page.save_screenshot(filepath)
            
            logger.info(f"截圖已保存: {filepath}")
            return True
        except Exception as e:
            logger.error(f"截圖失敗: {str(e)}")
            return False

    @staticmethod
    async def handle_alert(driver_or_page):
        """處理彈窗（支援 Selenium 和 Playwright）"""
        try:
            if isinstance(driver_or_page, Page):
                # Playwright
                dialog_handler = lambda dialog: asyncio.create_task(dialog.accept())
                driver_or_page.on('dialog', dialog_handler)
            else:
                # Selenium
                try:
                    alert = driver_or_page.switch_to.alert
                    alert.accept()
                except:
                    pass
            return True
        except Exception as e:
            logger.error(f"處理彈窗失敗: {str(e)}")
            return False

    @staticmethod
    async def press_key(driver_or_page, key: str):
        """按鍵盤按鍵（支援 Selenium 和 Playwright）"""
        try:
            if isinstance(driver_or_page, Page):
                # Playwright
                await driver_or_page.keyboard.press(key)
            else:
                # Selenium
                actions = ActionChains(driver_or_page)
                actions.send_keys(getattr(Keys, key.upper())).perform()
            return True
        except Exception as e:
            logger.error(f"按鍵失敗 {key}: {str(e)}")
            return False

    @staticmethod
    async def get_element_text(driver_or_page, selector: str) -> str:
        """獲取元素文字（支援 Selenium 和 Playwright）"""
        try:
            if isinstance(driver_or_page, Page):
                # Playwright
                element = await driver_or_page.query_selector(selector)
                if element:
                    return await element.text_content() or ""
            else:
                # Selenium
                element = driver_or_page.find_element(By.CSS_SELECTOR, selector)
                return element.text
            return ""
        except Exception as e:
            logger.error(f"獲取元素文字失敗 {selector}: {str(e)}")
            return "" 