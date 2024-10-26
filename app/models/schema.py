from datetime import date
from typing import Optional
from pydantic import BaseModel, validator
from datetime import datetime

class LoginResponse(BaseModel):
    """登入回應模型"""
    status: str
    message: str

class SearchRequest(BaseModel):
    case_number: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

    @validator('start_date', 'end_date', pre=True)
    def parse_date(cls, v):
        if isinstance(v, str):
            try:
                return datetime.strptime(v, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError('日期格式必須為 YYYY-MM-DD')
        return v

    @validator('end_date')
    def validate_date_range(cls, v, values):
        start_date = values.get('start_date')
        if start_date and v and v < start_date:
            raise ValueError('結束日期不能早於開始日期')
        return v

    @validator('case_number')
    def validate_search_criteria(cls, v, values):
        # 檢查是否同時有案號和日期
        has_date = values.get('start_date') is not None or values.get('end_date') is not None
        if v and has_date:
            raise ValueError('不能同時指定案號和日期範圍')
        return v

    @classmethod
    def with_defaults(cls):
        """創建帶有預設值的實例"""
        today = date.today()
        return cls(
            case_number=None,
            start_date=today,
            end_date=today
        )

class SearchResponse(BaseModel):
    """搜尋回應模型"""
    status: str
    message: str