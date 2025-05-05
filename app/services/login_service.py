"""FPG 自動化登入服務模組。"""
from datetime import date, datetime
from app.models.schema import SearchRequest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from app.services.browser import BrowserService
from app.services.captcha_service import CaptchaService
from app.core.config import settings
from app.services.result_processor import ResultProcessor
from app.utils import (
    click_element_by_text,
    take_screenshot,
    wait_for_element,
    get_today_date,
    handle_error,
    clear_screenshots_folder,
    ensure_screenshots_dir
)
from app.utils.selenium_utils import (
    verify_search_result, 
    get_element_text,
    wait_for_page_load
)
import asyncio
import logging
import re

class LoginService:
    """處理 FPG 網站的自動化登入流程。"""

    def __init__(self) -> None:
        self.browser_service = BrowserService()
        self.captcha_service = CaptchaService()
        self.result_processor = ResultProcessor()
        self.logger = logging.getLogger(__name__)
        self.max_retries = 5
        self.driver = None
        self.is_logged_in = False
        self.SEARCH_RESULT_SELECTORS = {
            'SUCCESS_TITLE': 'div[align="center"] font[color="#FFFFFF"] b',
            'ERROR_MESSAGE': 'td[bgcolor="#FF9933"] font[color="#FFFFFF"]'
        }
        self.MESSAGES = {
            'SUCCESS_TITLE': '標售公報查詢清單',
            'NOT_FOUND': '找不到您輸入的案號'
        }

    async def get_driver(self):
        """獲取或初始化driver"""
        if not self.driver:
            self.driver = self.browser_service.init_driver()
            self.is_logged_in = False
        return self.driver

    async def ensure_login(self):
        """確保已登入狀態"""
        if not self.is_logged_in:
            await self.login()
        return self.is_logged_in

    async def login(self) -> dict:
        """執行登入流程"""
        try:
            await clear_screenshots_folder(self.logger)  
            await ensure_screenshots_dir(self.logger)   
            self.logger.info("開始登入流程")
            
            # 添加更多日誌
            self.logger.info("正在初始化 driver...")
            driver = await self.get_driver()
            self.logger.info("driver 初始化完成")
            
            # 添加 driver 資訊日誌
            if driver:
                self.logger.info(f"Driver 類型: {type(driver)}")
                self.logger.info(f"Driver 設定: {driver.capabilities}")
            else:
                self.logger.error("Driver 初始化失敗")
                return {"status": "error", "message": "Driver 初始化失敗"}

            # 嘗試訪問頁面
            self.logger.info(f"正在訪問 FPG 登入頁面: {settings.LOGIN_URL}")
            try:
                driver.get(settings.LOGIN_URL)  # 使用 FPG 的登入 URL
                self.logger.info("成功訪問 FPG 登入頁面")
            except Exception as e:
                self.logger.error(f"訪問 FPG 登入頁面失敗: {str(e)}")
                return {"status": "error", "message": f"訪問 FPG 登入頁面失敗: {str(e)}"}

            login_result = await self.perform_login(driver)
            self.logger.info(f"登入結果: {login_result}")
            
            if login_result["status"] == "success":
                self.is_logged_in = True
                self.logger.info("登入成功，已設置登入狀態")
            else:
                self.logger.warning("登入失敗")
                
            return login_result
        except WebDriverException as e:
            self.logger.error("瀏覽器操作錯誤: %s", str(e))
            # 添加更多錯誤資訊
            self.logger.error(f"錯誤類型: {type(e).__name__}")
            self.logger.error(f"錯誤詳情: {str(e)}")
            await self.cleanup()
            return {"status": "error", "message": str(e)}
        except Exception as e:
            self.logger.error("未預期的錯誤: %s", str(e))
            # 添加堆疊追蹤
            import traceback
            self.logger.error(f"錯誤堆疊: {traceback.format_exc()}")
            await self.cleanup()
            return {"status": "error", "message": str(e)}

    async def perform_login(self, driver) -> dict:
        """執行具體的登入操作流程"""
        try:
            self.logger.info("正在確認 FPG 登入頁面...")
            await self.wait_for_page_load(driver)

            for attempt in range(self.max_retries):
                try:
                    self.logger.info(f"正在進行第 {attempt + 1} 次登入嘗試...")
                    await self.fill_login_form(driver)

                    # 處理驗證碼
                    captcha_result = await self.handle_captcha(driver)
                    if not captcha_result["success"]:
                        self.logger.error(f"驗證碼處理失敗: {captcha_result['message']}")
                        if attempt < self.max_retries - 1:
                            self.logger.info("重新整理頁面準備重試...")
                            driver.refresh()
                            await self.wait_for_page_load(driver)
                            continue

                    # 如果驗證碼成功，嘗試提交
                    success = await self.submit_form(driver)
                    if success:
                        self.logger.info("登入成功")
                        return {"status": "success", "message": "登入成功"}

                    self.logger.warning("登入失敗，準備重試")
                    driver.refresh()
                    await self.wait_for_page_load(driver)

                except Exception as e:
                    self.logger.error(f"登入嘗試失敗: {str(e)}")
                    if attempt == self.max_retries - 1:
                        raise

            return {"status": "error", "message": f"登入失敗，已嘗試 {self.max_retries} 次"}

        except Exception as e:
            self.logger.error(f"登入過程發生錯誤: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def wait_for_page_load(self, driver) -> None:
        """
        等待頁面載入完成。

        Args:
            driver: Selenium WebDriver 實例。

        Raises:
            TimeoutException: 當頁面載入超時時拋出。
        """
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "id"))
            )
            self.logger.info("頁面載入完成")
        except TimeoutException:
            self.logger.error("頁面載入超時")
            raise

    async def fill_login_form(self, driver) -> None:
        """
        填寫登入表單。

        Args:
            driver: Selenium WebDriver 實例。

        Raises:
            WebDriverException: 當表單操作失敗時拋出。
        """
        try:
            username_field = driver.find_element(By.NAME, "id")
            password_field = driver.find_element(By.NAME, "passwd")

            username_field.clear()
            password_field.clear()

            username_field.send_keys(settings.USERNAME)
            password_field.send_keys(settings.PASSWORD)

            self.logger.info("表單填寫完成")
        except WebDriverException as e:
            self.logger.error("填寫表單時發生錯誤: %s", str(e))
            raise

    async def handle_captcha(self, driver) -> dict:
        """處理驗證碼"""
        try:
            self.logger.info("開始處理驗證碼...")
            captcha_img = driver.find_element(By.ID, "vcode")
            captcha_buffer = await self._get_captcha_image_buffer(captcha_img)

            if not captcha_buffer:
                return {"success": False, "message": "驗證碼圖片擷取失敗"}

            captcha_text = await self.captcha_service.solve_captcha(captcha_buffer)

            if not captcha_text or captcha_text == "error" or len(captcha_text) != 4:
                return {"success": False, "message": f"驗證碼解析結果無效: {captcha_text}"}

            self.logger.info(f"填入驗證碼: {captcha_text}")
            captcha_input = driver.find_element(By.NAME, "vcode")
            captcha_input.clear()
            captcha_input.send_keys(captcha_text)

            return {"success": True, "message": "驗證碼處理成功"}

        except Exception as e:
            self.logger.error(f"驗證碼處理發生錯誤: {str(e)}")
            return {"success": False, "message": str(e)}

    async def submit_form(self, driver) -> bool:
        """提交登入表單並等待結果"""
        try:
            submit_button = driver.find_element(
                By.CSS_SELECTOR, 
                'input[type="submit"][value="登入"]'
            )
            submit_button.click()

            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )

            login_success = await self.verify_login_success(driver)
            if login_success:
                self.logger.info("驗證登入成功")
                return True

            self.logger.warning("登入驗證失敗")
            return False

        except Exception as e:
            self.logger.error(f"提交表單時發生錯誤: {str(e)}")
            return False

    async def verify_login_success(self, driver) -> bool:
        """驗證登入是否成功"""
        try:
            menu_element = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "menu_pos"))
            )

            menu_text = menu_element.text
            required_items = ["熱訊", "標售公報", "標案管理"]
            success = all(text in menu_text for text in required_items)

            if success:
                self.logger.info("成功驗證登入狀態")
            else:
                self.logger.warning("未能找到預期的選單項目")

            return success

        except TimeoutException:
            self.logger.warning("等待選單元素超時")
            return False
        except WebDriverException as e:
            self.logger.error(f"驗證登入狀態時發生錯誤: {str(e)}")
            return False

    async def _get_captcha_image_buffer(self, element) -> bytes:
        """擷取驗證碼圖片"""
        try:
            self.logger.info("正在擷取驗證碼圖片...")
            original_implicit_wait = element.parent.timeouts.implicit_wait
            element.parent.implicitly_wait(1)
            
            try:
                return element.screenshot_as_png
            finally:
                element.parent.implicitly_wait(original_implicit_wait)
                
        except WebDriverException as e:
            self.logger.error(f"擷取驗證碼圖片時發生錯誤: {str(e)}")
            raise

    async def get_total_pages(self, driver) -> int:
        """獲取搜尋結果的總頁數"""
        try:
            search_result = await verify_search_result(driver)
            if not search_result['success']:
                return 0

            # 找到包含頁數資訊的元素
            pagination_info = driver.find_element(
                By.CSS_SELECTOR, 
                'input[name="gtpage2"]'
            ).get_attribute("value")

            # 頁數資訊格式為: "頁次：1/6頁"
            matches = re.search(r'/(\d+)頁', pagination_info)
            if matches:
                total_pages = int(matches.group(1))
                self.logger.info(f"找到總頁數: {total_pages}")
                return total_pages

            page_text = await self.get_page_text_by_js(driver)
            matches = re.search(r'/(\d+)頁', page_text)
            if matches:
                total_pages = int(matches.group(1))
                self.logger.info(f"找到總頁數: {total_pages}")
                return total_pages

            self.logger.warning("無法找到總頁數資訊，返回預設值 1")
            return 1
                
        except Exception as e:
            self.logger.warning(f"獲取總頁數時發生錯誤: {str(e)}, 返回預設值 1")
            await take_screenshot(driver, "error_get_total_pages", self.logger)
            return 1

    async def get_page_text_by_js(self, driver) -> str:
        """使用 JavaScript 獲取頁數文字"""
        script = """
        const input = document.querySelector('input[name="gtpage2"]');
        if (!input) return '';
        
        // 檢查下一個相鄰節點
        let next = input.nextSibling;
        while (next) {
            if (next.nodeType === 3) {  // 文字節點
                return next.textContent || '';
            }
            next = next.nextSibling;
        }
        return '';
        """
        return driver.execute_script(script)
        
    async def search_bulletins(self, search_params: SearchRequest) -> dict:
        """搜尋標售公報"""
        try:
            self.logger.info("開始搜尋標售公報")
            if not await self.ensure_login():
                return {"status": "error", "message": "登入失敗"}

            # 如果沒有提供任何搜尋參數，使用今天日期
            if not search_params.case_number and not search_params.start_date:
                today_str = get_today_date()  # 使用 utils 中的函數
                today = datetime.strptime(today_str, "%Y/%m/%d").date()
                search_params = SearchRequest(
                    case_number=None,
                    start_date=today,
                    end_date=today
                )
                self.logger.info(f"使用預設日期參數：{today_str}")
            
            # 確保結束日期存在
            if search_params.start_date and not search_params.end_date:
                search_params.end_date = search_params.start_date
            
            # 更新 ResultProcessor 的搜尋參數
            self.result_processor.update_search_params(search_params)
            
            # 導航到標售公報頁面
            await self.navigate_to_bulletin(self.driver)
            
            # 總是使用日期範圍搜尋
            start_date_str = search_params.start_date.strftime('%Y/%m/%d')
            end_date_str = search_params.end_date.strftime('%Y/%m/%d')
            self.logger.info(f"搜尋日期範圍：{start_date_str} 至 {end_date_str}")
            
            await self.search_by_date_range(
                self.driver,
                start_date_str,
                end_date_str
            )
            
            # 驗證搜尋結果
            search_result = await verify_search_result(self.driver)
            if not search_result['success']:
                return {
                    "status": "success", 
                    "message": search_result['message']
                }
            
            # 獲取總頁數並處理結果
            total_pages = await self.get_total_pages(self.driver)
            self.logger.info(f"搜尋完成，共 {total_pages} 頁")
            
            # 處理搜尋結果
            if total_pages > 0:
                success = await self.result_processor.process_results(self.driver, total_pages)
                return {
                    "status": "success" if success else "error",
                    "message": "處理完成" if success else "處理失敗"
                }
            else:
                return {"status": "success", "message": "沒有找到符合條件的資料"}
            
        except Exception as e:
            self.logger.error(f"搜尋過程發生錯誤: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def navigate_to_bulletin(self, driver) -> None:
        """導航到標售公報頁面"""
        try:
            await click_element_by_text(driver, '.menu_pos a', '標售公報', self.logger)
            await wait_for_element(driver, 'input[type="button"][value="開始搜尋"]', logger=self.logger)
            self.logger.info("成功導航到標售公報頁面")
            await take_screenshot(driver, "標售公報頁面", self.logger)
        except Exception as e:
            await handle_error(driver, "導航到標售公報", e, self.logger)

    async def perform_search(self, driver, search_params: SearchRequest) -> dict:
        """執行搜尋操作"""
        try:
            if search_params.case_number:
                await self.search_by_case_number(driver, search_params.case_number)
            else:
                await self.search_by_date_range(
                    driver, 
                    search_params.start_date.strftime('%Y-%m-%d'),
                    search_params.end_date.strftime('%Y-%m-%d')
                )
            
            return {"status": "success", "message": "搜尋完成"}
        except Exception as e:
            return {"status": "error", "message": f"搜尋失敗: {str(e)}"}

    async def search_by_case_number(self, driver, case_number: str) -> None:
        """使用案號搜尋"""
        try:
            # 選擇案號搜尋選項
            radio = driver.find_element(By.CSS_SELECTOR, 'input[type="radio"][value="radio1"]')
            radio.click()
            
            # 輸入案號
            case_input = driver.find_element(By.NAME, "tndsalno")
            case_input.clear()
            case_input.send_keys(case_number)
            
            # 點擊搜尋按鈕
            await self.click_search_button(driver)
            
        except Exception as e:
            self.logger.error(f"案號搜尋失敗: {str(e)}")
            raise           

    async def click_search_button(self, driver) -> None:
        """點擊搜尋按鈕並等待結果"""
        try:
            search_button = driver.find_element(
                By.CSS_SELECTOR, 
                'input[type="button"][value="開始搜尋"]'
            )
            search_button.click()
            await wait_for_element(driver, 'table', timeout=10, logger=self.logger)
            await take_screenshot(driver, '搜尋結果', self.logger)
        except Exception as e:
            await handle_error(driver, '點擊搜索按鈕', e, self.logger)

    async def wait_for_search_results(self, driver) -> None:
        """等待搜尋結果載入"""
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
            self.logger.info("搜尋結果已載入")
        except TimeoutException:
            self.logger.error("搜尋結果載入超時")
            raise

    async def cleanup(self):
        """清理資源"""
        if self.driver:
            self.browser_service.close_driver()
            self.driver = None
            self.is_logged_in = False

    async def search_by_date_range(self, driver, start_date: str, end_date: str) -> None:
        """使用日期範圍搜尋"""
        try:
            self.logger.info("選擇日期範圍...")
            
            # 選擇日期搜尋選項
            await self.click_radio_button(driver)
            
            # 確保日期輸入欄位可見
            await self.ensure_date_inputs_visible(driver)
            
            # 使用 JavaScript 直接設定日期值
            driver.execute_script(f"""
                document.getElementById('date_f').value = '{start_date}';
                document.getElementById('date_e').value = '{end_date}';
            """)
            self.logger.info(f"已設定日期範圍: {start_date} 至 {end_date}")
            
            # 註解掉原本的日期選擇按鈕操作
            # # 選擇開始日期
            # await self.select_date(driver, '#button3', start_date)
            # # 選擇結束日期
            # await self.select_date(driver, '#button4', end_date)
            
            # 驗證選擇的日期
            await self.verify_selected_dates(driver, start_date, end_date)
            
            # 選擇公告日期
            await self.select_announcement_date(driver)
            
            # 點擊搜尋按鈕
            await self.click_search_button(driver)
            
        except Exception as e:
            self.logger.error(f"日期範圍搜尋失敗: {str(e)}")
            raise

    async def click_radio_button(self, driver):
        """點擊日期搜尋的 radio button"""
        radio = driver.find_element(By.CSS_SELECTOR, 'input[type="radio"][value="radio2"]')
        radio.click()
        self.logger.info("已選擇日期搜尋選項")

    async def ensure_date_inputs_visible(self, driver):
        """確保日期輸入欄位可見"""
        await wait_for_element(driver, '#date_f', logger=self.logger)
        await wait_for_element(driver, '#date_e', logger=self.logger)
        self.logger.info("日期輸入欄位已可見")

    async def select_date(self, driver, button_selector: str, date: str):
        """選擇日期（處理彈出視窗）"""
        try:
            # 找到並點擊日期選擇按鈕
            date_button = await wait_for_element(driver, button_selector, logger=self.logger)
            if not date_button:
                raise Exception(f"無法找到日期選擇按鈕: {button_selector}")
                
            date_button.click()
            self.logger.info(f"點擊日期選擇按鈕: {button_selector}")
            
            # 等待彈出視窗
            await asyncio.sleep(1)
            
            # 獲取所有視窗句柄
            handles = driver.window_handles
            if len(handles) < 2:
                raise Exception("未檢測到日期選擇視窗")
                
            # 切換到彈出視窗
            popup_window = handles[-1]
            driver.switch_to.window(popup_window)
            
            try:
                # 在彈出視窗中選擇日期
                await self.click_date_in_popup(driver, date)
                self.logger.info(f"已在彈出視窗中選擇日期: {date}")
            finally:
                # 確保切回主視窗
                if len(driver.window_handles) > 1:  # 如果彈出視窗還在
                    driver.close()  # 關閉彈出視窗
                driver.switch_to.window(handles[0])  # 切回主視窗
                
        except Exception as e:
            self.logger.error(f"選擇日期時發生錯誤: {str(e)}")
            await take_screenshot(driver, f"error_select_date_{date}", self.logger)
            raise

    async def click_date_in_popup(self, driver, target_date: str):
        """在彈出視窗中點擊指定日期"""
        try:
            # 等待表格載入
            await wait_for_element(driver, 'table', logger=self.logger)
            
            # 使用 JavaScript 找到並點擊日期
            date_clicked = driver.execute_script("""
                const links = Array.from(document.querySelectorAll('table tr td a'));
                const targetLink = links.find(link => {
                    const onclick = link.getAttribute('onclick');
                    return onclick && onclick.includes(arguments[0]);
                });
                if (targetLink) {
                    targetLink.click();
                    return true;
                }
                return false;
            """, target_date)
            
            if not date_clicked:
                raise Exception(f"在彈出視窗中未找到日期: {target_date}")
                
            self.logger.info(f"成功點選日期: {target_date}")
            
        except Exception as e:
            self.logger.error(f"在彈出視窗中選擇日期時發生錯誤: {str(e)}")
            raise

    async def verify_selected_dates(self, driver, start_date: str, end_date: str):
        """驗證選擇的日期是否正確"""
        start_value = driver.find_element(By.ID, "date_f").get_attribute("value")
        end_value = driver.find_element(By.ID, "date_e").get_attribute("value")
        
        self.logger.info(f"日期範圍選擇完成: {start_value} 至 {end_value}")
        
        if start_value != start_date or end_value != end_date:
            self.logger.warning("選擇的日期可能不正確，請檢查")

    async def select_announcement_date(self, driver):
        """選擇公告日期選項"""
        radio = driver.find_element(By.CSS_SELECTOR, 'input[type="radio"][value="ntidat"]')
        radio.click()
        self.logger.info("已選擇公告日期選項")

    def __del__(self):
        """析構函數，確保資源被清理"""
        if self.driver:
            self.browser_service.close_driver()
