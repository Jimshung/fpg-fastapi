import aiohttp
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

async def verify_bot_token(bot_token: str) -> bool:
    """驗證 Bot Token"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                result = await response.json()
                logger.debug(f"Bot 驗證結果: {result}")
                return result.get("ok", False)
    except Exception as e:
        logger.error(f"驗證 Bot Token 時發生錯誤: {str(e)}")
        return False

async def send_telegram_notification(bot_token: str, chat_id: str, message: str):
    """發送 Telegram 通知"""
    try:
        # 先驗證 Bot Token
        if not await verify_bot_token(bot_token):
            logger.error("Bot Token 驗證失敗")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }) as response:
                response_json = await response.json()
                logger.debug(f"Telegram API 回應: {response_json}")
                
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