import asyncio
from datetime import date, datetime
from app.services.login_service import LoginService
from app.models.schema import SearchRequest
from app.utils.telegram import send_telegram_notification
from app.core.config import settings
import logging
from io import StringIO

# 設定根日誌記錄器
logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()  # 獲取根日誌記錄器

async def main():
    try:
        start_time = datetime.now()
        
        # 設定日誌收集器
        log_stream = StringIO()
        log_handler = logging.StreamHandler(log_stream)
        log_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        # 將處理器添加到根日誌記錄器
        root_logger.addHandler(log_handler)
        
        logger = logging.getLogger(__name__)
        logger.info("開始執行自動化流程")
        
        login_service = LoginService()
        search_params = SearchRequest(
            case_number=None,
            start_date=date.today(),
            end_date=date.today()
        )
        
        result = await login_service.search_bulletins(search_params)
        logger.info(f"搜尋結果: {result}")
        
        # 獲取收集的日誌
        log_messages = log_stream.getvalue().splitlines()
        
        # Telegram 通知
        if settings.ENABLE_TELEGRAM_NOTIFY:
            message = f"""
*FPG 自動化流程執行報告* 🤖

📊 *執行資訊*
執行狀態: {'✅ 成功' if result['status'] == 'success' else '❌ 失敗'}
執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}
執行耗時: {(datetime.now() - start_time).seconds} 秒
搜尋結果: {result['message']}
搜尋日期: {search_params.start_date.strftime('%Y-%m-%d')}

🔍 *執行日誌*:
{chr(10).join(log_messages[-30:])}
"""
            await send_telegram_notification(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=settings.TELEGRAM_CHAT_ID,
                message=message
            )
    except Exception as e:
        logger.error(f"執行過程發生錯誤: {str(e)}")
        if settings.ENABLE_TELEGRAM_NOTIFY:
            await send_telegram_notification(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=settings.TELEGRAM_CHAT_ID,
                message=f"❌ 執行錯誤: {str(e)}"
            )
    finally:
        logger.info("自動化流程完成")
        # 從根日誌記錄器移除處理器
        root_logger.removeHandler(log_handler)

if __name__ == "__main__":
    asyncio.run(main())