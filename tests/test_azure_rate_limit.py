"""Azure OCR 429 退避與 RateLimitError：不需網路。

用法:
  python -m tests.test_azure_rate_limit
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.captcha_service import (
    AzureRateLimitError,
    CaptchaService,
    retry_after_seconds,
)
from app.utils.telegram_digest import build_fpg_failure_digest, build_pcc_digest


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


async def _test_solve_raises_rate_limit() -> None:
    service = CaptchaService()
    service.max_rate_limit_retries = 2

    response = MagicMock()
    response.status = 429
    response.headers = {"Retry-After": "1"}
    response.text = AsyncMock(return_value="throttled")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock()
    session.post = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.captcha_service.aiohttp.ClientSession", return_value=session):
        with patch.object(service, "_resize_image", AsyncMock(return_value=b"img")):
            with patch.object(service, "_save_original_image", AsyncMock()):
                with patch.object(service, "_cleanup_temp_files", AsyncMock()):
                    with patch("app.services.captcha_service.asyncio.sleep", AsyncMock()):
                        try:
                            await service.solve_captcha(b"raw")
                            raised = False
                        except AzureRateLimitError as exc:
                            raised = True
                            _assert(exc.retry_after >= 1.0, str(exc.retry_after))
    _assert(raised, "solve_captcha must raise AzureRateLimitError after 429s")


def main() -> int:
    _assert(retry_after_seconds({"Retry-After": "7"}, attempt=1) == 7.0, "exact")
    _assert(retry_after_seconds({"Retry-After": "2"}, attempt=3) == 15.0, "floor")
    _assert(retry_after_seconds({}, attempt=2) == 10.0, "default")
    _assert(retry_after_seconds({"Retry-After": "x"}, attempt=1) == 5.0, "bad")

    asyncio.run(_test_solve_raises_rate_limit())

    digest = build_fpg_failure_digest(
        announce_label="2026/08/10",
        error="FPG 登入失敗：驗證碼重試耗盡",
        elapsed_s=45.2,
        actions_url="https://github.com/Jimshung/fpg-fastapi/actions/runs/1",
    )
    _assert(digest.startswith("❌"), digest)
    _assert("FPG 標售歸檔" in digest, digest)
    _assert("驗證碼重試耗盡" in digest, digest)
    _assert("Actions log" in digest, digest)
    _assert("actions/runs/1" in digest, digest)

    pcc_ok = build_pcc_digest(
        range_label="2026-08-10",
        records=[],
        ok=0,
        err=0,
        elapsed_s=3,
    )
    _assert(pcc_ok.startswith("✅"), pcc_ok)
    _assert("PCC 財物變賣歸檔" in pcc_ok, pcc_ok)

    print("OK: azure rate limit / digest header 單元測試通過")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
