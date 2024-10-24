from fastapi import APIRouter, HTTPException
from app.services.login_service import LoginService
from app.models.schema import LoginResponse

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