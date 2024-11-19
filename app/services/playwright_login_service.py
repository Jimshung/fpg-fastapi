from playwright.async_api import async_playwright, Page, ElementHandle
from app.core.config import settings
from app.models.schema import SearchRequest
import logging
import os
from datetime import datetime

class PlaywrightLoginService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.browser = None
        self.page = None
        self.playwright = None
        
        # 確保 screenshots 目錄存在
        os.makedirs("screenshots", exist_ok=True)

    async def init_browser(self):
        """初始化瀏覽器"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.page = await self.browser.new_page()
            self.logger.info("Playwright 瀏覽器初始化成功")
        except Exception as e:
            self.logger.error(f"Playwright 瀏覽器初始化失敗: {str(e)}")
            raise

    async def check_maintenance(self):
        """檢查系統是否在維護中"""
        try:
            maintenance_box = await self.page.query_selector('#infoBox')
            if maintenance_box:
                # 使用進階解析分析維護訊息
                element_info = await self.analyze_element(maintenance_box)
                maintenance_text = await maintenance_box.inner_text()
                
                if "進行主機維護與更新" in maintenance_text:
                    self.logger.warning("系統目前正在維護中")
                    self.logger.info(f"維護訊息元素分析: {element_info}")
                    return True
            return False
        except Exception as e:
            self.logger.error(f"檢查維護狀態時發生錯誤: {str(e)}")
            return False

    async def login(self) -> dict:
        """執行登入流程"""
        try:
            if not self.page:
                await self.init_browser()
                
            # 訪問登入頁面
            self.logger.info(f"正在訪問登入頁面: {settings.LOGIN_URL}")
            await self.page.goto(settings.LOGIN_URL)
            
            # 檢查維護狀態
            if await self.check_maintenance():
                return {"status": "error", "message": "系統維護中"}
            
            # 使用智能填寫功能填寫表單
            if not await self.smart_fill(self.page, 'input[name="id"]', settings.USERNAME):
                return {"status": "error", "message": "無法填寫用戶名"}
                
            if not await self.smart_fill(self.page, 'input[name="passwd"]', settings.PASSWORD):
                return {"status": "error", "message": "無法填寫密碼"}
            
            # 處理驗證碼
            captcha_element = await self.page.query_selector('#vcode')
            if captcha_element:
                element_info = await self.analyze_element(captcha_element)
                self.logger.info(f"驗證碼元素分析: {element_info}")
            
            return {"status": "success", "message": "登入表單填寫完成"}
            
        except Exception as e:
            self.logger.error(f"登入失敗: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def search_bulletins(self, search_params: SearchRequest = None) -> dict:
        """使用 Playwright 執行標售公報搜尋"""
        try:
            if not self.page:
                await self.init_browser()
                
            # 檢查維護狀態
            if await self.check_maintenance():
                return {"status": "error", "message": "系統維護中"}
            
            # 如果沒有提供任何搜尋參數，使用今天日期
            if search_params is None:
                search_params = SearchRequest.with_defaults()
            
            # 確保結束日期存在
            if search_params.start_date and not search_params.end_date:
                search_params.end_date = search_params.start_date
                
            # 使用智能點擊導航到標售公報
            if not await self.smart_click(self.page, 'text=標售公報'):
                return {"status": "error", "message": "無法導航到標售公報頁面"}
            
            # 根據搜尋參數執行搜尋
            if search_params.case_number:
                await self.search_by_case_number(search_params.case_number)
            else:
                await self.search_by_date_range(
                    search_params.start_date,
                    search_params.end_date
                )
                
            return {"status": "success", "message": "搜尋完成"}
            
        except Exception as e:
            self.logger.error(f"搜尋失敗: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def search_by_case_number(self, case_number: str):
        """使用案號搜尋"""
        # 使用智能點擊選擇案號搜尋選項
        await self.smart_click(self.page, 'input[type="radio"][value="radio1"]')
        # 使用智能填寫輸入案號
        await self.smart_fill(self.page, 'input[name="tndsalno"]', case_number)
        # 使用智能點擊搜尋按鈕
        await self.smart_click(self.page, 'input[type="button"][value="開始搜尋"]')
        await self.page.wait_for_load_state('networkidle')

    async def search_by_date_range(self, start_date, end_date):
        """使用日期範圍搜尋"""
        try:
            # 選擇日期搜尋選項
            await self.smart_click(self.page, 'input[type="radio"][value="radio2"]')
            
            # 等待日期輸入欄位和按鈕出現
            await self.page.wait_for_selector('#date_f')
            await self.page.wait_for_selector('#button3')
            await self.page.wait_for_selector('#button4')
            
            # 選擇開始日期
            await self.select_date_in_popup('button3', start_date)
            
            # 選擇結束日期
            await self.select_date_in_popup('button4', end_date)
            
            # 選擇公告日期選項
            await self.smart_click(self.page, 'input[type="radio"][value="ntidat"]')
            
            # 點擊搜尋按鈕
            await self.smart_click(self.page, 'input[type="button"][value="開始搜尋"]')
            await self.page.wait_for_load_state('networkidle')
            
        except Exception as e:
            self.logger.error(f"日期範圍搜尋失敗: {str(e)}")
            raise

    async def select_date_in_popup(self, button_id: str, target_date: str):
        """在彈出視窗中選擇日期"""
        try:
            # 點擊日期選擇按鈕
            await self.page.click(f'#{button_id}')
            
            # 等待新視窗打開
            popup_page = await self.page.wait_for_event('popup')
            
            # 等待表格載入
            await popup_page.wait_for_selector('table')
            
            # 將目標日期轉換為正確的格式 (YYYY/MM/DD)
            formatted_date = target_date.strftime('%Y/%m/%d') if hasattr(target_date, 'strftime') else target_date.replace('-', '/')
            
            # 使用與 Selenium 相似的 JavaScript 邏輯，但針對 Playwright 優化
            success = await popup_page.evaluate('''
                (targetDate) => {
                    // 找到所有日期連結
                    const links = Array.from(document.querySelectorAll('table tr td a'));
                    
                    // 構建預期的 onclick 值（支援兩種可能的格式）
                    const expectedValues = [
                        `self.opener.document.FJ202C1PA01.date_f.value='${targetDate}'`,
                        `self.opener.document.FJ202C1PA01.date_e.value='${targetDate}'`
                    ];
                    
                    // 查找匹配的連結
                    const targetLink = links.find(link => {
                        const onclick = link.getAttribute('onclick');
                        return onclick && expectedValues.some(value => onclick.includes(value));
                    });
                    
                    if (targetLink) {
                        // 使用 dispatchEvent 來觸發點擊事件
                        const clickEvent = new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        });
                        targetLink.dispatchEvent(clickEvent);
                        
                        // 同時也執行 onclick 事件中的代碼
                        const onclickCode = targetLink.getAttribute('onclick');
                        if (onclickCode) {
                            try {
                                eval(onclickCode);
                            } catch (e) {
                                console.error('Error executing onclick:', e);
                            }
                        }
                        
                        return true;
                    }
                    
                    // 如果沒找到，返回可用的日期資訊供調試
                    return {
                        success: false,
                        availableDates: links.map(link => ({
                            text: link.textContent.trim(),
                            onclick: link.getAttribute('onclick')
                        }))
                    };
                }
            ''', formatted_date)
            
            # 處理結果
            if isinstance(success, dict):  # 如果返回調試信息
                self.logger.error(f"可用的日期: {success['availableDates']}")
                raise Exception(f"在日期選擇器中未找到日期: {formatted_date}")
            elif not success:
                raise Exception(f"日期選擇失敗: {formatted_date}")
            
            # 等待彈出視窗關閉（增加超時時間和錯誤處理）
            try:
                await popup_page.wait_for_event('close', timeout=5000)
            except Exception as e:
                self.logger.warning(f"等待視窗關閉超時: {str(e)}")
                # 嘗試手動關閉視窗
                await popup_page.close()
            
            self.logger.info(f"成功選擇日期: {formatted_date}")
            
        except Exception as e:
            self.logger.error(f"選擇日期時發生錯誤: {str(e)}")
            # 保存錯誤截圖和更多診斷信息
            if 'popup_page' in locals():
                await popup_page.screenshot(path=f"screenshots/error_popup_{formatted_date}.png")
                html = await popup_page.content()
                self.logger.error(f"彈出視窗 HTML: {html[:500]}...")  # 只記錄前500字符
            await self.page.screenshot(path=f"screenshots/error_main_{formatted_date}.png")
            raise

    async def cleanup(self):
        """清理資源"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            self.logger.info("Playwright 資源已清理")
        except Exception as e:
            self.logger.error(f"清理資源時發生錯誤: {str(e)}")

    async def __aenter__(self):
        """異步上下文管理器進入"""
        await self.init_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """異步上下文管理器退出"""
        await self.cleanup()

    async def analyze_element(self, element: ElementHandle) -> dict:
        """使用進階解析功能分析元素"""
        info = {
            'tag': await element.evaluate('el => el.tagName.toLowerCase()'),
            'parent': await element.evaluate('''el => {
                const parent = el.parentElement;
                return parent ? parent.outerHTML : null;
            }'''),
            'children': await element.evaluate('''el => 
                Array.from(el.children).map(child => ({
                    data: child.outerHTML,
                    parent: el.outerHTML
                }))
            '''),
            'siblings': await element.evaluate('''el => 
                Array.from(el.parentElement.children)
                    .filter(sibling => sibling !== el)
                    .map(sibling => ({
                        data: sibling.outerHTML,
                        parent: el.parentElement.outerHTML
                    }))
            ''')
        }
        
        # 智能選擇器生成
        info['css_selector'] = await element.evaluate('''el => {
            const path = [];
            while (el && el.nodeType === Node.ELEMENT_NODE) {
                let selector = el.tagName.toLowerCase();
                if (el.id) {
                    selector += '#' + el.id;
                    path.unshift(selector);
                    break;
                } else {
                    let nth = 1;
                    let sib = el;
                    while (sib.previousElementSibling) {
                        if (sib.previousElementSibling.tagName === el.tagName) nth++;
                        sib = sib.previousElementSibling;
                    }
                    if (nth > 1) selector += ':nth-of-type(' + nth + ')';
                }
                path.unshift(selector);
                el = el.parentElement;
            }
            return path.join(' > ');
        }''')
        
        return info

    async def smart_click(self, page: Page, selector: str) -> bool:
        """智能點擊功能"""
        try:
            element = await page.query_selector(selector)
            if not element:
                return False
                
            # 分析元素
            element_info = await self.analyze_element(element)
            self.logger.info(f"元素分析: {element_info}")
            
            # 檢查元素是否可見且可點擊
            is_visible = await element.is_visible()
            is_enabled = await element.evaluate('el => !el.disabled')
            
            if not is_visible or not is_enabled:
                alternative_selector = element_info['css_selector']
                self.logger.info(f"嘗試使用替代選擇器: {alternative_selector}")
                element = await page.query_selector(alternative_selector)
            
            await element.click()
            return True
            
        except Exception as e:
            self.logger.error(f"智能點擊失敗: {str(e)}")
            return False

    async def smart_fill(self, page: Page, selector: str, value: str) -> bool:
        """智能填寫功能"""
        try:
            element = await page.query_selector(selector)
            if not element:
                return False
                
            # 分析元素
            element_info = await self.analyze_element(element)
            
            # 檢查元素是否為輸入框
            tag_name = element_info['tag']
            if tag_name not in ['input', 'textarea']:
                self.logger.warning(f"元素不是輸入框: {tag_name}")
                return False
            
            # 智能填寫
            await element.fill(value)
            return True
            
        except Exception as e:
            self.logger.error(f"智能填寫失敗: {str(e)}")
            return False