import asyncio
from playwright.async_api import async_playwright
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_login():
    """測試登入功能"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # 訪問登入頁面
            logger.info("正在訪問登入頁面...")
            await page.goto('https://www.e-fpg.com.tw/j202/cus/prt/cus_prt_srh.jsp?logonstate=Big5')
            
            # 等待頁面加載
            await page.wait_for_load_state('networkidle')
            
            # 檢查維護狀態
            maintenance_box = await page.query_selector('#infoBox')
            if maintenance_box:
                maintenance_text = await maintenance_box.inner_text()
                if "進行主機維護與更新" in maintenance_text:
                    logger.warning("系統目前正在維護中")
                    logger.info(f"維護訊息: {maintenance_text.strip()}")
                    return None
            
            return True
            
        except Exception as e:
            logger.error(f"測試過程發生錯誤: {str(e)}")
            return False
            
        finally:
            await browser.close()

async def test_search():
    """測試搜尋功能"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            logger.info("正在訪問搜尋頁面...")
            await page.goto('https://www.e-fpg.com.tw/j202/cus/prt/cus_prt_srh.jsp?logonstate=Big5')
            
            # 檢查維護狀態
            maintenance_box = await page.query_selector('#infoBox')
            if maintenance_box:
                maintenance_text = await maintenance_box.inner_text()
                if "進行主機維護與更新" in maintenance_text:
                    logger.warning("系統目前正在維護中")
                    logger.info(f"維護訊息: {maintenance_text.strip()}")
                    return None
            
            return True
            
        except Exception as e:
            logger.error(f"搜尋測試過程發生錯誤: {str(e)}")
            return False
            
        finally:
            await browser.close()

async def run_all_tests():
    """執行所有測試"""
    logger.info("開始執行 Playwright 測試...")
    
    tests = [
        ("登入測試", test_login()),
        ("搜尋測試", test_search())
    ]
    
    results = []
    for test_name, test_coro in tests:
        logger.info(f"\n執行 {test_name}...")
        try:
            result = await test_coro
            if result is None:
                status = "系統維護中"
            else:
                status = "成功" if result else "失敗"
            results.append((test_name, status))
        except Exception as e:
            logger.error(f"測試執行出錯: {str(e)}")
            results.append((test_name, "失敗"))
    
    logger.info("\n測試結果摘要:")
    for test_name, status in results:
        logger.info(f"{test_name}: {status}")

if __name__ == "__main__":
    asyncio.run(run_all_tests()) 