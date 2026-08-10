"""純 HTTP 重放 FPG 登入流程（不開瀏覽器），並記錄 cookies / 回應特徵。"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.config import settings
from app.services.captcha_service import CaptchaService
from app.services.fpg_urls import CAPTCHA_PATH, LOGIN_SERVLET_PATH, fpg_base_url, fpg_url

OUT = ROOT / "app" / "utils" / "screenshots" / "probe"
OUT.mkdir(parents=True, exist_ok=True)

LOGIN_PAGE = settings.LOGIN_URL
CAPTCHA_URL = fpg_url(CAPTCHA_PATH)
POST_URL = fpg_url(LOGIN_SERVLET_PATH)
ORIGIN = fpg_base_url()


def sniff_success(html: str, final_url: str) -> dict:
    markers = {
        "captcha_error": "驗證碼錯誤" in html,
        "login_fail": any(x in html for x in ("帳號或密碼", "登入失敗", "密碼錯誤", "無此帳號")),
        "has_menu": "menu_pos" in html or "標售公報" in html,
        "has_logon_form": 'name="passwd"' in html and 'name="vcode"' in html,
        "title_match": bool(re.search(r"<title>([^<]+)</title>", html, re.I)),
    }
    title = re.search(r"<title>([^<]+)</title>", html, re.I)
    return {
        "final_url": final_url,
        "title": title.group(1).strip() if title else None,
        "markers": markers,
        "len": len(html),
    }


async def fetch_captcha(session: aiohttp.ClientSession) -> bytes:
    url = f"{CAPTCHA_URL}?rrr={int(time.time() * 1000)}"
    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.read()
        print(
            f"[captcha] GET {url} -> {resp.status} {len(data)} bytes "
            f"ct={resp.headers.get('Content-Type')}"
        )
        return data


async def login_once(session: aiohttp.ClientSession, captcha_text: str) -> dict:
    form = {
        "FROMJSP": "FJ2XXMG01",
        "BTN": "",
        "Lang": "",
        "logonstate": "",
        "id": settings.FPG_USERNAME,
        "passwd": settings.FPG_PASSWORD,
        "vcode": captcha_text,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": ORIGIN,
        "Referer": LOGIN_PAGE,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        ),
    }
    async with session.post(POST_URL, data=form, headers=headers, allow_redirects=True) as resp:
        html = await resp.text(errors="replace")
        info = sniff_success(html, str(resp.url))
        info["status"] = resp.status
        info["set_cookie"] = resp.headers.getall("Set-Cookie", [])
        (OUT / "http_login_response.html").write_text(html, encoding="utf-8")
        return info


async def inspect_login_page(session: aiohttp.ClientSession) -> None:
    async with session.get(LOGIN_PAGE) as resp:
        html = await resp.text(errors="replace")
        print(f"[page] GET {LOGIN_PAGE} -> {resp.status}")
        print(f"[page] cookies after GET: {list(session.cookie_jar)}")
        actions = re.findall(r'<form[^>]*action=["\']([^"\']*)["\'][^>]*>', html, re.I)
        hiddens = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', html, re.I)
        names = re.findall(r'name=["\']([^"\']+)["\']', " ".join(hiddens), re.I)
        values = re.findall(r'value=["\']([^"\']*)["\']', " ".join(hiddens), re.I)
        print(f"[page] form actions: {actions}")
        print(f"[page] hidden names: {names}")
        print(f"[page] hidden values: {values}")
        caps = re.findall(r'src=["\']([^"\']*Captcha[^"\']*)["\']', html, re.I)
        print(f"[page] captcha srcs: {caps}")
        (OUT / "http_login_page.html").write_text(html, encoding="utf-8")


async def main() -> None:
    captcha_service = CaptchaService()
    timeout = aiohttp.ClientTimeout(total=60)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar, timeout=timeout) as session:
        await inspect_login_page(session)

        for attempt in range(1, 6):
            print(f"\n===== HTTP login attempt {attempt}/5 =====")
            img = await fetch_captcha(session)
            (OUT / f"http_captcha_{attempt}.png").write_bytes(img)
            text = await captcha_service.solve_captcha(img)
            print(f"[ocr] => {text!r}")
            if not text or text == "error" or len(str(text)) != 4:
                print("[ocr] invalid, retry")
                continue
            info = await login_once(session, str(text))
            print(f"[login] status={info['status']} url={info['final_url']}")
            print(f"[login] title={info['title']}")
            print(f"[login] markers={info['markers']}")
            print(f"[login] cookies now: {[c.key for c in session.cookie_jar]}")
            if info["markers"]["captcha_error"]:
                print("-> captcha wrong, retry")
                continue
            if info["markers"]["has_menu"] and not info["markers"]["has_logon_form"]:
                print("-> LOGIN SUCCESS (menu present)")
                break
            if not info["markers"]["has_logon_form"] and not info["markers"]["captcha_error"]:
                print("-> possible success (no login form)")
                break
            print("-> still on login-like page / unknown, stop or retry")
            if info["markers"]["login_fail"]:
                break
        else:
            print("all attempts exhausted")

        print("\nfinal cookies:")
        for cookie in session.cookie_jar:
            print(f"  {cookie.key}={cookie.value[:20]}... domain={cookie.get('domain')}")


if __name__ == "__main__":
    asyncio.run(main())
