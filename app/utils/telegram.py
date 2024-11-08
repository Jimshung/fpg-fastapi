import aiohttp
import logging

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