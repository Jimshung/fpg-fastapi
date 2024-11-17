import pytest
from playwright.async_api import async_playwright
from app.core.config import settings
from app.services.login_service import LoginService
from app.models.schema import SearchRequest
from datetime import date

@pytest.mark.asyncio
async def test_login_with_playwright():
    """測試使用 Playwright 的登入功能"""
    service = LoginService(use_playwright=True)
    
    try:
        result = await service.login()
        
        if "系統維護中" in result.get("message", ""):
            pytest.skip("系統維護中")
            
        assert result["status"] in ["success", "error"]
        if result["status"] == "error":
            assert "message" in result
            
    finally:
        if hasattr(service, 'playwright_service'):
            await service.playwright_service.cleanup()

@pytest.mark.asyncio
async def test_search_with_playwright():
    """測試使用 Playwright 的搜尋功能"""
    service = LoginService(use_playwright=True)
    
    try:
        # 使用今天日期進行搜尋
        today = date.today()
        search_params = SearchRequest(
            start_date=today,
            end_date=today
        )
        
        result = await service.search_bulletins(search_params)
        
        if "系統維護中" in result.get("message", ""):
            pytest.skip("系統維護中")
            
        assert result["status"] in ["success", "error"]
        
    finally:
        if hasattr(service, 'playwright_service'):
            await service.playwright_service.cleanup()

@pytest.mark.asyncio
async def test_case_number_search():
    """測試案號搜尋功能"""
    service = LoginService(use_playwright=True)
    
    try:
        search_params = SearchRequest(case_number="AB-12345")
        result = await service.search_bulletins(search_params)
        
        if "系統維護中" in result.get("message", ""):
            pytest.skip("系統維護中")
            
        assert result["status"] in ["success", "error"]
        
    finally:
        if hasattr(service, 'playwright_service'):
            await service.playwright_service.cleanup() 