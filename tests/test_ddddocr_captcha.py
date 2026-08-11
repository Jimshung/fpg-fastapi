"""ddddocr 驗證碼後處理與樣本辨識：不需外網 API。

用法:
  python -m tests.test_ddddocr_captcha
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from app.services.captcha_service import CaptchaService
from app.utils.telegram_digest import build_fpg_failure_digest, build_pcc_digest


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    svc = CaptchaService()
    _assert(svc._process_captcha_text("4587") == "4587", "digits")
    _assert(svc._process_captcha_text("45 87") == "4587", "spaces")
    _assert(svc._process_captcha_text("ab4587cd") == "4587", "mixed")
    _assert(svc._process_captcha_text("458") == "error", "too short")
    _assert(svc._process_captcha_text("45870") == "error", "too long")

    sample = Path("app/utils/screenshots/captcha_probe/captcha_01.jpg")
    if sample.is_file():
        code = asyncio.run(svc.solve_captcha(sample.read_bytes()))
        _assert(code == "4587", f"sample captcha_01 expected 4587 got {code!r}")

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

    pcc_ok = build_pcc_digest(
        range_label="2026-08-10",
        records=[],
        ok=0,
        err=0,
        elapsed_s=3,
    )
    _assert(pcc_ok.startswith("✅"), pcc_ok)
    _assert("PCC 財物變賣歸檔" in pcc_ok, pcc_ok)

    print("OK: ddddocr captcha / digest 單元測試通過")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
