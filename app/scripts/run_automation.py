import asyncio
from app.services.login_service import LoginService
from app.models.schema import SearchRequest
from datetime import date
import logging
from app.utils.notification import TelegramNotifier
import time

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('automation.log')
    ]
)

logger = logging.getLogger(__name__)

async def main():
    start_time = time.time()
    notifier = TelegramNotifier()
    
    try:
        logger.info("開始執行自動化流程")
        service = LoginService()
        today = date.today()
        params = SearchRequest(start_date=today, end_date=today)
        
        logger.info("開始執行搜尋")
        result = await service.search_bulletins(params)
        logger.info(f"搜尋結果: {result}")
        
        await service.cleanup()
        logger.info("自動化流程完成")
        
        # 執行完成後發送通知
        duration = int(time.time() - start_time)
        message = notifier.format_success_message(
            duration=duration,
            log_summary=f"搜尋結果數量: {len(result)}"
        )
        notifier.send_message(message)
        
    except Exception as e:
        logger.error(f"執行過程中發生錯誤: {str(e)}", exc_info=True)
        # 發送錯誤通知
        error_message = notifier.format_error_message(str(e))
        notifier.send_message(error_message)
        raise

if __name__ == "__main__":
    asyncio.run(main()) 