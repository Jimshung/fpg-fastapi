import aiohttp
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # 設置此模組的日誌級別為 DEBUG

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
                if response.status == 200 or response_json.get("ok"):
                    logger.info("Telegram 通知發送成功")
                else:
                    # 如果消息實際上發送成功但 API 回應異常
                    logger.debug(f"Telegram API 回應: {response_json}")
                    logger.info("Telegram 通知可能已發送，但 API 回應異常")
    except Exception as e:
        logger.error(f"發送 Telegram 通知時發生錯誤: {str(e)}")