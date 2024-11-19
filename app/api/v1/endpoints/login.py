from fastapi import APIRouter, HTTPException
from datetime import date
from app.services.login_service import LoginService
from app.models.schema import LoginResponse, SearchRequest, SearchResponse
from typing import Optional
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/api/v1",
    tags=["FPG 自動化"],
    responses={404: {"description": "未找到"}}
)

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="執行自動登入",
    description="自動執行 FPG 網站的登入流程",
    responses={
        200: {
            "description": "登入成功",
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "登入成功"}
                }
            }
        },
        400: {
            "description": "登入失敗",
            "content": {
                "application/json": {
                    "example": {"detail": "登入失敗：驗證碼錯誤"}
                }
            }
        }
    }
)
async def login():
    """
    執行自動登入程序
    
    Returns:
        LoginResponse: 登入結果，包含狀態和訊息
    """
    login_service = LoginService()
    result = await login_service.login()

    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])

    return result

@router.post(
    "/search",
    response_model=SearchResponse,
    summary="搜尋標售公報",
    description="根據指定的參數搜尋 FPG 標售公報",
    responses={
        200: {
            "description": "搜尋成功",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "message": "搜尋完成",
                        "data": [{"case_number": "FPG-2024-001", "title": "測試案件"}]
                    }
                }
            }
        },
        400: {"description": "搜尋失敗"}
    }
)
async def search_bulletins(search_params: Optional[SearchRequest] = None):
    """
    執行標售公報搜尋
    
    Args:
        search_params (SearchRequest, optional): 搜尋參數，包含日期範圍或案號
            
    Returns:
        SearchResponse: 搜尋結果，包含狀態和資料
    
    Raises:
        HTTPException: 當搜尋失敗時拋出 400 錯誤
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