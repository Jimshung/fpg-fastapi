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
                if response.status == 200:
                    logger.info("Telegram 通知發送成功")
                else:
                    logger.error(f"Telegram 通知發送失敗: {await response.text()}")
    except Exception as e:
        logger.error(f"發送 Telegram 通知時發生錯誤: {str(e)}") 