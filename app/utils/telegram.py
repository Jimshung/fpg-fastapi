import aiohttp
import logging
import asyncio
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

logger = logging.getLogger(__name__)

async def send_telegram_notification(bot_token: str, chat_id: str, message: str):
    """發送 Telegram 通知"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }) as response:
                response_json = await response.json()
                if response_json.get("ok"):
                    logger.info("Telegram 通知發送成功")
                    return True
                else:
                    error_code = response_json.get("error_code")
                    description = response_json.get("description")
                    logger.error(f"Telegram 發送失敗: {error_code} - {description}")
                    return False
    except Exception as e:
        logger.error(f"發送 Telegram 通知時發生錯誤: {str(e)}")
        return False

async def press_esc(driver, logger):
    """處理彈出視窗和 ESC 按鍵"""
    try:
        # 先嘗試按 ESC
        try:
            logger.info("嘗試按下 ESC 鍵...")
            actions = ActionChains(driver)
            actions.send_keys(Keys.ESCAPE).perform()
            logger.info("已按下 ESC 鍵")
            await asyncio.sleep(0.5)
        except:
            pass

        # 如果還有 Alert，則處理 Alert
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            logger.info(f"檢測到系統提示視窗: {alert_text}")
            alert.accept()
            logger.info("已確認系統提示")
            await asyncio.sleep(0.5)
        except:
            pass
            
    except Exception as e:
        logger.error(f"處理彈出視窗時發生錯誤: {str(e)}")
        # 不要在這裡 raise，讓程式可以繼續執行
        pass