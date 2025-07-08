import logging
from typing import List, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.utils import (
    click_element_by_text,
    take_screenshot,
    wait_for_element,
    handle_error
)
from app.models.tender_status import TenderBidder, TenderStatus
from datetime import datetime

class TenderStatusService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def navigate_to_tender_status(self, driver) -> bool:
        """導航到標售案件處理情形頁面"""
        try:
            # 點擊標案管理連結
            await click_element_by_text(
                driver, 
                'a.menu_sec1.lnk_module', 
                '標案管理', 
                self.logger
            )
            
            # 等待並確認頁面標題
            await wait_for_element(
                driver,
                'div.title',
                text='標售案件處理情形',
                logger=self.logger
            )
            
            # 拍攝截圖
            await take_screenshot(driver, "標售案件處理情形頁面", self.logger)
            
            return True
            
        except Exception as e:
            await handle_error(driver, "導航到標售案件處理情形頁面", e, self.logger)
            return False

    async def extract_table_data(self, driver) -> List[TenderBidder]:
        """擷取表格資料"""
        try:
            # 等待表格載入
            table = await wait_for_element(driver, 'table', logger=self.logger)
            if not table:
                raise Exception("找不到表格元素")

            # 找到所有資料行
            rows = driver.find_elements(By.CSS_SELECTOR, 'tbody tr')
            bidders = []

            for row in rows:
                try:
                    # 獲取各欄位資料
                    columns = row.find_elements(By.TAG_NAME, 'td')
                    if len(columns) >= 4:  # 確保有足夠的欄位
                        bidder = TenderBidder(
                            company_name=columns[0].text.strip(),
                            not_yet_quoted=int(columns[1].text.strip() or '0'),
                            quoted=int(columns[2].text.strip() or '0'),
                            price_quoted=int(columns[3].text.strip() or '0')
                        )
                        bidders.append(bidder)
                except Exception as e:
                    self.logger.error(f"處理行資料時發生錯誤: {str(e)}")
                    continue

            return bidders

        except Exception as e:
            self.logger.error(f"擷取表格資料時發生錯誤: {str(e)}")
            await take_screenshot(driver, "error_extract_table", self.logger)
            return []

    async def get_tender_status(self, driver) -> Optional[TenderStatus]:
        """獲取標售案件狀態"""
        try:
            # 導航到標售案件頁面
            if not await self.navigate_to_tender_status(driver):
                return None

            # 擷取表格資料
            bidders = await self.extract_table_data(driver)
            
            # 獲取標案編號（如果有的話）
            tender_no = await self._get_tender_number(driver) or "Unknown"

            # 建立狀態物件
            status = TenderStatus(
                tender_no=tender_no,
                bidders=bidders,
                last_updated=datetime.now()
            )

            return status

        except Exception as e:
            self.logger.error(f"獲取標售案件狀態時發生錯誤: {str(e)}")
            return None

    async def _get_tender_number(self, driver) -> Optional[str]:
        """獲取標案編號"""
        try:
            element = driver.find_element(By.CSS_SELECTOR, 'input[name="tender_no"]')
            return element.get_attribute('value')
        except Exception as e:
            self.logger.warning(f"無法獲取標案編號: {str(e)}")
            return None 