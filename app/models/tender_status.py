from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class TenderBidder(BaseModel):
    """投標商資訊"""
    company_name: str
    not_yet_quoted: int = 0
    quoted: int = 0
    price_quoted: int = 0

class TenderStatus(BaseModel):
    """標售案件狀態"""
    tender_no: str
    bidders: List[TenderBidder]
    last_updated: datetime = datetime.now() 