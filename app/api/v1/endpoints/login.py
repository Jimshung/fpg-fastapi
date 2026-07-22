from fastapi import APIRouter, HTTPException
from datetime import date

from app.models.schema import LoginResponse, SearchRequest, SearchResponse
from app.services.fpg_http_client import FpgHttpClient
from app.services.taiwan_case_filter import filter_taiwan_cases

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login():
    """HTTP 登入探測（不開瀏覽器）。"""
    try:
        async with FpgHttpClient() as fpg:
            await fpg.login()
        return {"status": "success", "message": "HTTP 登入成功"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search", response_model=SearchResponse)
async def search_bulletins(search_params: SearchRequest = None):
    """依公告日搜尋標售公報（HTTP），預設僅回傳台灣案摘要。"""
    if search_params is None:
        search_params = SearchRequest.with_defaults()
    if search_params.case_number:
        raise HTTPException(
            status_code=400,
            detail="此案號搜尋請改用 python -m app.scripts.run_archive 流程",
        )

    start = (search_params.start_date or date.today()).strftime("%Y/%m/%d")
    end = (search_params.end_date or date.today()).strftime("%Y/%m/%d")

    try:
        async with FpgHttpClient() as fpg:
            await fpg.login()
            bases = await fpg.search_bulletin_by_announce_date(start, end)
        kept, skipped = filter_taiwan_cases(bases)
        return {
            "status": "success",
            "message": (
                f"{start}~{end}：公報 {len(bases)} 案，"
                f"台灣 {len(kept)}，排除 {len(skipped)}"
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/today", response_model=SearchResponse)
async def search_today_bulletins():
    """搜尋今天公告（HTTP，台灣案篩選後計數）。"""
    today = date.today()
    return await search_bulletins(
        SearchRequest(start_date=today, end_date=today)
    )
