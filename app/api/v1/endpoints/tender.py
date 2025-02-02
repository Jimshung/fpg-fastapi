from fastapi import APIRouter, Depends, HTTPException
from app.services.tender_status_service import TenderStatusService
from app.services.login_service import LoginService
from app.models.tender_status import TenderStatus
from typing import List

router = APIRouter()

@router.get("/list", response_model=List[TenderStatus])
async def list_tenders():
    """獲取標售案件列表"""
    login_service = LoginService()
    tender_service = TenderStatusService()
    
    try:
        # 登入
        login_result = await login_service.login()
        if login_result["status"] != "success":
            raise HTTPException(status_code=401, detail="登入失敗")

        # 獲取標售案件狀態
        status = await tender_service.get_tender_status(login_service.driver)
        if not status:
            raise HTTPException(status_code=404, detail="無法獲取標售案件狀態")

        return [status]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await login_service.cleanup() 