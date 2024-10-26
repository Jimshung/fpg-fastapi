from fastapi import APIRouter, HTTPException
from datetime import date
from app.services.login_service import LoginService
from app.models.schema import LoginResponse, SearchRequest, SearchResponse

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login():
    """
    執行自動登入程序
    """
    login_service = LoginService()
    result = await login_service.login()

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result

@router.post("/search", response_model=SearchResponse)
async def search_bulletins(search_params: SearchRequest = None):
    """
    執行標售公報搜尋
    如果沒有提供參數，使用今天日期作為預設值
    """
    if search_params is None:
        search_params = SearchRequest.with_defaults()
    
    login_service = LoginService()
    
    # 先執行登入
    login_result = await login_service.login()
    if login_result["status"] == "error":
        raise HTTPException(status_code=400, detail=login_result["message"])
    
    # 執行搜尋
    search_result = await login_service.search_bulletins(search_params)
    
    if search_result["status"] == "error":
        raise HTTPException(status_code=400, detail=search_result["message"])
        
    return search_result

@router.get("/today", response_model=SearchResponse)
async def search_today_bulletins():
    """
    搜尋今天的標售公報
    """
    today = date.today()
    search_params = SearchRequest(start_date=today, end_date=today)
    
    login_service = LoginService()
    
    # 先執行登入
    login_result = await login_service.login()
    if login_result["status"] == "error":
        raise HTTPException(status_code=400, detail=login_result["message"])
    
    # 執行搜尋
    search_result = await login_service.search_bulletins(search_params)
    
    if search_result["status"] == "error":
        raise HTTPException(status_code=400, detail=search_result["message"])
        
    return search_result