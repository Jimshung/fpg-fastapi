# app/utils/selenium_utils.py
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
import os
from datetime import datetime
import re
import asyncio
import logging
from .utils import take_screenshot

logger = logging.getLogger(__name__)

SEARCH_RESULT_SELECTORS = {
    'SUCCESS_TITLE': 'div[align="center"] font[color="#FFFFFF"] b',
    'ERROR_MESSAGE': 'td[bgcolor="#FF9933"] font[color="#FFFFFF"]'
}

MESSAGES = {
    'SUCCESS_TITLE': '標售公報查詢清單',
    'NOT_FOUND': '找不到您輸入的案號'
}

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

async def wait_for_element(driver, selector: str, timeout: int = 10, logger = None):
    """
    等待並返回元素
    """
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return element
    except TimeoutException:
        if logger:
            logger.error(f"等待元素 {selector} 超時")
            await take_screenshot(driver, f"wait_timeout_{selector}", logger)
        raise TimeoutException(f"等待元素 {selector} 超時")

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

async def clear_screenshots_folder(logger):
    """清理 screenshots 資料夾"""
    try:
        screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        if os.path.exists(screenshots_dir):
            logger.info("正在清理 Screenshots 資料夾...")
            for file in os.listdir(screenshots_dir):
                if file.endswith(".png"):
                    os.remove(os.path.join(screenshots_dir, file))
            logger.info("Screenshots 資料夾清理完成")
        else:
            logger.info("Screenshots 資料夾不存在，無需清理")
    except Exception as e:
        logger.error(f"清理 Screenshots 資料夾時發生錯誤: {str(e)}")

async def ensure_screenshots_dir(logger):
    """確保 screenshots 資料夾存在"""
    try:
        screenshots_dir = os.path.join(os.path.dirname(__file__), "screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)
        logger.info("Screenshots 資料夾已準備就緒")
    except Exception as e:
        logger.error(f"創建 Screenshots 資料夾時發生錯誤: {str(e)}")

async def press_esc(driver, logger):
    """模擬按下 ESC 鍵"""
    try:
        logger.info("模擬按下 ESC 鍵...")
        actions = ActionChains(driver)
        actions.send_keys(Keys.ESCAPE).perform()
        logger.info("已按下 ESC 鍵")
    except Exception as e:
        logger.error(f"按下 ESC 鍵時發生錯誤: {str(e)}")
        raise

async def verify_search_result(driver) -> dict:
    """驗證搜尋結果"""
    logger.info("確認搜尋結果...")
    try:
        # 檢查成功標題
        success_title = await get_element_text(
            driver,
            SEARCH_RESULT_SELECTORS['SUCCESS_TITLE']
        )
        if success_title == MESSAGES['SUCCESS_TITLE']:
            logger.info("成功找到標售公報查詢清單頁面")
            return {"success": True, "message": "查詢成功"}

        # 檢查錯誤訊息
        error_message = await get_element_text(
            driver,
            SEARCH_RESULT_SELECTORS['ERROR_MESSAGE']
        )
        if error_message:
            if MESSAGES['NOT_FOUND'] in error_message:
                logger.info(f"查詢未找到結果：{error_message}")
            else:
                logger.warning(f"搜尋結果異常：{error_message}")
            return {"success": False, "message": error_message}

        raise Exception("頁面內容不符合預期")
        
    except Exception as e:
        logger.error(f"驗證搜尋結果時發生錯誤: {str(e)}")
        await take_screenshot(driver, "搜尋結果驗證失敗", logger)
        raise

async def get_element_text(driver, selector: str) -> str:
    """獲取元素文字內容"""
    try:
        element = driver.find_element(By.CSS_SELECTOR, selector)
        return element.text.strip()
    except:
        return ""

async def wait_for_page_load(driver, timeout: int = 10) -> None:
    """等待頁面載入完成"""
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete'
    )

