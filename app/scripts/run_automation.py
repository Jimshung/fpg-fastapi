import asyncio
from datetime import date, datetime
from app.services.login_service import LoginService
from app.models.schema import SearchRequest
from app.utils.telegram import send_telegram_notification
from app.core.config import settings
import logging
from io import StringIO
import os
import psutil
import time
from app.models.metrics import ExecutionMetrics, PerformanceMetrics
from app.utils.error_analyzer import ErrorAnalyzer
import shutil

# 設定根日誌記錄器
logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()  # 獲取根日誌記錄器

async def collect_metrics():
    process = psutil.Process()
    return {
        'memory_usage': process.memory_info().rss / 1024 / 1024,  # MB
        'cpu_usage': process.cpu_percent(),
        'network_io': psutil.net_io_counters()
    }

async def main():
    try:
        # 在腳本開始時清理目錄
        for directory in ['app/utils/screenshots', 'app/metrics']:
            if os.path.exists(directory):
                shutil.rmtree(directory)
            os.makedirs(directory)
            
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
        
        metrics = ExecutionMetrics(
            start_time=datetime.now(),
            end_time=datetime.now(),  # 先設置初始值
            status="pending",  # 設置初始狀態
            search_results_count=0,  # 設置初始值
            errors=[],
            performance=PerformanceMetrics(
                login_duration=0.0,
                search_duration=0.0,
                total_duration=0.0,
                memory_usage=0.0,
                cpu_usage=0.0,
                network_requests=0,
                page_load_time=0.0
            ),
            browser_logs=[]
        )
        
        # 收集性能指標
        login_start = time.time()
        await login_service.login()
        metrics.performance.login_duration = time.time() - login_start
        
        # 搜尋開始時間
        search_start = time.time()
        result = await login_service.search_bulletins(search_params)
        metrics.performance.search_duration = time.time() - search_start
        
        # 更新狀態和結果數
        metrics.status = "success" if result['status'] == 'success' else "failure"
        metrics.search_results_count = len(result.get('data', []))
        
        # 更新總執行時間
        metrics.performance.total_duration = time.time() - login_start
        
        # 更新系統指標
        system_metrics = await collect_metrics()
        metrics.performance.memory_usage = system_metrics['memory_usage']
        metrics.performance.cpu_usage = system_metrics['cpu_usage']
        
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
        error_analyzer = ErrorAnalyzer()
        error_analyzer.capture_error(e, "主程序執行")
        error_report = error_analyzer.generate_report()
        
        # 更新 metrics 的錯誤資訊
        metrics.errors.append(str(e))
        metrics.status = "error"
        
        logger.error(f"執行過程發生錯誤: {str(e)}")
        if settings.ENABLE_TELEGRAM_NOTIFY:
            await send_telegram_notification(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                chat_id=settings.TELEGRAM_CHAT_ID,
                message=f"""❌ 執行錯誤報告:
                
{error_report}"""
            )
    finally:
        logger.info("自動化流程完成")
        root_logger.removeHandler(log_handler)
        
        # 在腳本結束時
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # 只在 GitHub Actions 環境中寫入環境變數
        if 'GITHUB_ENV' in os.environ:
            with open(os.environ['GITHUB_ENV'], 'a') as f:
                f.write(f"EXECUTION_TIME={end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"EXECUTION_DURATION={int(duration)}\n")
        else:
            logger.info(f"本地執行 - 執行時間: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"本地執行 - 執行耗時: {int(duration)} 秒")
        
        metrics.end_time = datetime.now()
        # 儲存指標
        try:
            metrics_file = metrics.save()
            logger.info(f"性能指標已儲存至: {metrics_file}")
        except Exception as e:
            logger.warning(f"儲存性能指標時發生錯誤: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())