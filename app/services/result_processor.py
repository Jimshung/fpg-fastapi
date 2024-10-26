import logging
import asyncio
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.utils import (
    take_screenshot,
    press_esc,
    wait_for_element,
    handle_error
)

class ResultProcessor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.search_params = None
        self.checkbox_selector = 'input[type="checkbox"][name="item"][onclick="goCheck(this.form,this)"]'

    def update_search_params(self, search_params):
        """更新搜尋參數"""
        self.search_params = search_params

    async def process_results(self, driver, total_pages: int) -> bool:
        """處理搜尋結果"""
        try:
            if total_pages > 1:
                return await self.handle_multi_page_results(driver, total_pages)
            else:
                return await self.handle_single_page_result(driver)
        except Exception as e:
            self.logger.error(f"處理結果時發生錯誤: {str(e)}")
            return False

    async def handle_single_page_result(self, driver) -> bool:
        """處理單頁結果"""
        try:
            checkboxes = await self.find_checkboxes(driver)
            if not checkboxes:
                self.logger.info("未找到複選框，準備點擊回主畫面")
                await self.click_back_to_main_button(driver, mode='search')
                return True
            
            self.logger.info(f"找到 {len(checkboxes)} 個複選框，開始處理")
            await self.select_all_checkboxes(driver, checkboxes)
            await self.click_save_button(driver)
            return True
        except Exception as e:
            self.logger.error(f"處理單頁結果時發生錯誤: {str(e)}")
            return False

    async def handle_multi_page_results(self, driver, total_pages: int) -> bool:
        """處理多頁結果"""
        current_page = 1
        while current_page <= total_pages:
            self.logger.info(f"正在處理第 {current_page}/{total_pages} 頁")
            
            checkboxes = await self.find_checkboxes(driver)
            if checkboxes:
                await self.handle_page_with_checkboxes(driver, checkboxes, current_page, total_pages)
            else:
                await self.handle_page_without_checkboxes(driver, current_page, total_pages)
            
            current_page += 1

        self.logger.info("所有頁面處理完成")
        return True

    async def handle_page_with_checkboxes(self, driver, checkboxes, current_page, total_pages):
        """處理有複選框的頁面"""
        try:
            await self.select_all_checkboxes(driver, checkboxes)
            await self.click_save_button(driver)
            self.logger.info(f"第 {current_page} 頁的選擇已保存")
            
            if current_page < total_pages:
                # 不是最後一頁，需要重新搜尋並跳到下一頁
                await self.navigate_with_research(driver, current_page + 1)
            else:
                self.logger.info("已處理完最後一頁")
                
        except Exception as e:
            self.logger.error(f"處理第 {current_page} 頁複選框時發生錯誤: {str(e)}")
            raise

    async def handle_page_without_checkboxes(self, driver, current_page, total_pages):
        """處理沒有複選框的頁面"""
        self.logger.info(f"第 {current_page} 頁沒有找到複選框")
        
        if current_page < total_pages:
            # 不是最後一頁，直接點擊下一頁
            await self.navigate_to_next_page(driver)
        else:
            # 最後一頁沒有複選框，返回主畫面
            self.logger.info("最後一頁沒有複選框，返回主畫面")
            await self.click_back_to_main_button(driver, mode='search')

    async def find_checkboxes(self, driver):
        """找尋頁面上的複選框（先確保 DOM 加載完成）"""
        try:
            original_implicit_wait = driver.timeouts.implicit_wait
            driver.implicitly_wait(0)
            
            try:
                WebDriverWait(driver, 2).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete'
                )
                checkboxes = driver.find_elements(By.CSS_SELECTOR, self.checkbox_selector)
                self.logger.info(f"找到 {len(checkboxes)} 個複選框")
                return checkboxes
                
            finally:
                driver.implicitly_wait(original_implicit_wait)
                
        except Exception as e:
            self.logger.warning(f"查找複選框時發生錯誤: {str(e)}")
            return []

    async def select_all_checkboxes(self, driver, checkboxes):
        """選取所有未勾選的複選框"""
        for i, checkbox in enumerate(checkboxes, 1):
            if not await self.is_checkbox_checked(driver, checkbox):
                await self.click_checkbox_safely(driver, checkbox)
                self.logger.info(f"已選擇第 {i} 個複選框")
                await asyncio.sleep(1)

    async def is_checkbox_checked(self, driver, checkbox):
        """檢查複選框是否已被選取"""
        return driver.execute_script("""
            const cb = arguments[0];
            return cb.checked || 
                   cb.closest('tr')?.classList.contains('selected') ||
                   document.querySelector(`label[for="${cb.id}"]`)?.textContent.includes('已選擇');
        """, checkbox)

    async def click_checkbox_safely(self, driver, checkbox):
        """安全地點擊複選框（處理彈窗）"""
        try:
            checkbox.click()
            await asyncio.sleep(1)
            await press_esc(driver, self.logger)
        except Exception as e:
            self.logger.error(f"點擊複選框時發生錯誤: {str(e)}")
            raise

    async def click_save_button(self, driver):
        """點擊轉報價作業按鈕"""
        try:
            save_button = driver.find_element(
                By.CSS_SELECTOR,
                "input[type=\"button\"][value=\"轉報價作業\"][onclick=\"goSave(this.form,'all','ntidat','all','T')\"]"
            )
            save_button.click()
            self.logger.info("成功點擊轉報價作業按鈕")
            await asyncio.sleep(1)
        except Exception as e:
            await handle_error(driver, "點擊轉報價作業按鈕", e, self.logger)

    async def click_back_to_main_button(self, driver, mode='search'):
        """點擊回主畫面按鈕"""
        try:
            selector = (
                'input[type="button"][value="回主畫面"][onclick="goSearch(this.form,\'srh\')"]'
                if mode == 'search'
                else 'input[type="button"][value="回主畫面"][onclick="goList(this.form)"]'
            )
            
            back_button = driver.find_element(By.CSS_SELECTOR, selector)
            back_button.click()
            self.logger.info(f"成功點擊回主畫面按鈕 (mode: {mode})")
            await asyncio.sleep(1)
            
        except Exception as e:
            await handle_error(driver, "點擊回主畫面按鈕", e, self.logger)

    async def navigate_to_next_page(self, driver):
        """導航到下一頁"""
        try:
            next_page_link = driver.find_element(By.XPATH, "//a[text()='下一頁']")
            next_page_link.click()
            
            # 等待頁面導航完成
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            self.logger.info("已成功導航到下一頁")
            
        except Exception as e:
            self.logger.error(f"導航到下一頁時發生錯誤: {str(e)}")
            raise

    async def navigate_with_research(self, driver, page_number: int):
        """重新搜尋並導航到指定頁面"""
        try:
            self.logger.info(f"重新搜索並跳轉到第 {page_number} 頁")
            await take_screenshot(driver, f"重新搜索到第_{page_number}_頁", self.logger)
            
            # 回到主畫面
            await self.click_back_to_main_button(driver, mode='list')
            
            # 等待搜尋按鈕可見
            await wait_for_element(
                driver,
                'input[type="button"][value="開始搜尋"]',
                logger=self.logger
            )
            
            # 重新執行搜尋
            if self.search_params.case_number:
                await self.search_by_case_number(driver, self.search_params.case_number)
            else:
                await self.search_by_date_range(
                    driver,
                    self.search_params.start_date,
                    self.search_params.end_date
                )
            
            # 跳轉到指定頁面
            await self.go_to_specific_page(driver, page_number)
            
        except Exception as e:
            self.logger.error(f"重新搜索並跳轉到第 {page_number} 頁時發生錯誤: {str(e)}")
            await take_screenshot(driver, f"error_re_search_page_{page_number}", self.logger)
            raise

    async def go_to_specific_page(self, driver, page_number: int):
        """跳轉到指定頁面"""
        try:
            # 等待頁面元素
            await wait_for_element(driver, 'input[name="gtpage1"]', logger=self.logger)
            await wait_for_element(driver, 'input[value="Go"]', logger=self.logger)
            
            # 輸入頁碼並點擊跳轉
            page_input = driver.find_element(By.CSS_SELECTOR, 'input[name="gtpage1"]')
            go_button = driver.find_element(By.CSS_SELECTOR, 'input[value="Go"]')
            
            page_input.clear()
            page_input.send_keys(str(page_number))
            go_button.click()
            
            # 等待頁面加載
            await wait_for_element(driver, 'table', logger=self.logger)
            self.logger.info(f"已跳轉到第 {page_number} 頁")
            await asyncio.sleep(2)
            
        except Exception as e:
            self.logger.error(f"跳轉到第 {page_number} 頁時發生錯誤: {str(e)}")
            raise