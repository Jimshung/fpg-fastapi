from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import logging
import os
from datetime import datetime
import re
import asyncio

async def click_element_by_text(driver, selector: str, text: str, logger):
    """
    通過文字內容點擊元素
    """
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        for element in elements:
            if text in element.text:
                element.click()
                logger.info(f"成功點擊文字為 '{text}' 的元素")
                return True
        raise Exception(f"未找到包含文字 '{text}' 的元素")
    except Exception as e:
        logger.error(f"點擊元素失敗: {str(e)}")
        raise

async def take_screenshot(driver, name: str, logger):
    """
    截取頁面截圖
    """
    try:
        screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        
        filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        filepath = os.path.join(screenshots_dir, filename)
        
        driver.save_screenshot(filepath)
        logger.info(f"截圖已保存: {filepath}")
    except Exception as e:
        logger.error(f"截圖失敗: {str(e)}")

async def wait_for_element(driver, selector: str, timeout: int = 10, logger = None) -> bool:
    """
    等待元素出現
    """
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return True
    except TimeoutException:
        if logger:
            logger.error(f"等待元素 {selector} 超時")
            await take_screenshot(driver, f"wait_timeout_{selector}", logger)
        return False

def get_today_date() -> str:
    """
    獲取今天日期，格式：YYYY/MM/DD
    """
    return datetime.now().strftime("%Y/%m/%d")

def validate_case_number(case_number: str) -> bool:
    """
    驗證案號格式
    """
    if not case_number:
        return True
    pattern = r'^[A-Z0-9]{2}-[A-Z0-9]{5}$'
    return bool(re.match(pattern, case_number))

async def retry_operation(operation, max_retries: int = 3, delay: int = 1, logger = None):
    """
    重試機制
    """
    for attempt in range(max_retries):
        try:
            return await operation()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            if logger:
                logger.warning(f"操作失敗，重試次數：{attempt + 1}，錯誤：{str(e)}")
            await asyncio.sleep(delay * (attempt + 1))

async def handle_error(driver, operation: str, error: Exception, logger):
    """
    錯誤處理
    """
    logger.error(f"執行 {operation} 時發生錯誤: {str(error)}")
    await take_screenshot(driver, f"error_{operation}", logger)
    raise error