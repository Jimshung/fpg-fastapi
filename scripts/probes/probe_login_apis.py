"""用 Selenium 登入 FPG，並以 CDP 攔截網路請求，觀察實際 API。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 專案根目錄
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.core.config import settings
from app.services.captcha_service import CaptchaService


OUT_DIR = ROOT / "app" / "utils" / "screenshots" / "probe"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DRIVER_PATH = "/tmp/chromedriver-extract/chromedriver-mac-arm64/chromedriver"


class NetworkCapture:
    def __init__(self) -> None:
        self.requests: Dict[str, Dict[str, Any]] = {}
        self.finished: List[Dict[str, Any]] = []

    def on_request(self, params: dict) -> None:
        req = params.get("request", {})
        rid = params.get("requestId")
        self.requests[rid] = {
            "requestId": rid,
            "url": req.get("url"),
            "method": req.get("method"),
            "headers": req.get("headers"),
            "postData": req.get("postData"),
            "type": params.get("type"),
            "timestamp": params.get("timestamp"),
            "hasPostData": req.get("hasPostData"),
        }

    def on_response(self, params: dict) -> None:
        rid = params.get("requestId")
        resp = params.get("response", {})
        entry = self.requests.get(rid, {"requestId": rid})
        entry["status"] = resp.get("status")
        entry["mimeType"] = resp.get("mimeType")
        entry["responseHeaders"] = resp.get("headers")
        entry["responseUrl"] = resp.get("url")
        self.requests[rid] = entry

    def on_loading_finished(self, params: dict) -> None:
        rid = params.get("requestId")
        if rid in self.requests:
            self.finished.append(self.requests[rid])


def create_driver(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--window-size=1400,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if headless:
        options.add_argument("--headless=new")
    # 開 performance log 備援
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    service = Service(executable_path=DRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(60)
    return driver


def attach_cdp(driver: webdriver.Chrome, capture: NetworkCapture) -> None:
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Page.enable", {})
    # selenium 4.15 支援 execute_cdp_cmd，事件需透過 performance log 或 selenium wire
    # 改用 performance log 輪詢（相容性較好）


def drain_performance_logs(driver: webdriver.Chrome, capture: NetworkCapture) -> None:
    try:
        logs = driver.get_log("performance")
    except Exception:
        return
    for item in logs:
        try:
            msg = json.loads(item["message"])["message"]
        except Exception:
            continue
        method = msg.get("method")
        params = msg.get("params", {})
        if method == "Network.requestWillBeSent":
            capture.on_request(params)
        elif method == "Network.responseReceived":
            capture.on_response(params)
        elif method == "Network.loadingFinished":
            capture.on_loading_finished(params)


async def solve_and_fill_captcha(driver, captcha_service: CaptchaService, max_tries: int = 5) -> bool:
    for attempt in range(1, max_tries + 1):
        print(f"[captcha] attempt {attempt}/{max_tries}")
        img = driver.find_element(By.ID, "vcode")
        buf = img.screenshot_as_png
        text = await captcha_service.solve_captcha(buf)
        print(f"[captcha] OCR result: {text!r}")
        if not text or text == "error" or len(text) != 4:
            driver.refresh()
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.NAME, "id")))
            continue
        field = driver.find_element(By.NAME, "vcode")
        field.clear()
        field.send_keys(text)
        return True
    return False


def summarize(capture: NetworkCapture) -> List[Dict[str, Any]]:
    rows = []
    seen = set()
    for e in capture.requests.values():
        url = e.get("url") or e.get("responseUrl") or ""
        method = e.get("method") or "?"
        key = (method, url, e.get("postData"))
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "method": method,
            "status": e.get("status"),
            "type": e.get("type"),
            "mimeType": e.get("mimeType"),
            "url": url,
            "postData": e.get("postData"),
            "requestHeaders": e.get("headers"),
            "responseHeaders": e.get("responseHeaders"),
        })
    # 有趣的：同站 XHR/Document/Fetch、或含 form post
    def score(r: dict) -> int:
        u = (r.get("url") or "").lower()
        t = (r.get("type") or "")
        s = 0
        if "e-fpg.com.tw" in u or "fpg.com.tw" in u:
            s += 10
        if t in ("XHR", "Fetch", "Document"):
            s += 5
        if r.get("postData"):
            s += 8
        if any(x in u for x in (".jsp", ".do", "api", "ajax", "json", "servlet")):
            s += 4
        return s

    rows.sort(key=score, reverse=True)
    return rows


async def main() -> None:
    headless = os.getenv("PROBE_HEADLESS", "false").lower() == "true"
    print(f"LOGIN_URL={settings.LOGIN_URL}")
    print(f"USERNAME={settings.USERNAME}")
    print(f"headless={headless}")
    print(f"driver={DRIVER_PATH}")

    capture = NetworkCapture()
    driver = create_driver(headless=headless)
    captcha_service = CaptchaService()

    try:
        # 先開空頁再開 CDP
        driver.get("about:blank")
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})

        print(">>> navigate login page")
        driver.get(settings.LOGIN_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.NAME, "id")))
        drain_performance_logs(driver, capture)
        driver.save_screenshot(str(OUT_DIR / "01_login_page.png"))

        # 填帳密
        user = driver.find_element(By.NAME, "id")
        pwd = driver.find_element(By.NAME, "passwd")
        user.clear()
        pwd.clear()
        user.send_keys(settings.USERNAME)
        pwd.send_keys(settings.PASSWORD)

        ok = await solve_and_fill_captcha(driver, captcha_service)
        if not ok:
            raise RuntimeError("驗證碼多次失敗")

        drain_performance_logs(driver, capture)
        driver.save_screenshot(str(OUT_DIR / "02_before_submit.png"))

        print(">>> submit login")
        submit = driver.find_element(By.CSS_SELECTOR, 'input[type="submit"][value="登入"]')
        submit.click()

        # 等導向或選單
        time.sleep(2)
        for _ in range(20):
            drain_performance_logs(driver, capture)
            try:
                menu = driver.find_elements(By.CLASS_NAME, "menu_pos")
                if menu and any(t in menu[0].text for t in ("標售公報", "熱訊", "標案管理")):
                    print(">>> login success (menu found)")
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            print(">>> login may have failed; dumping page source snippet")
            print(driver.title, driver.current_url)
            print(driver.page_source[:800])

        drain_performance_logs(driver, capture)
        driver.save_screenshot(str(OUT_DIR / "03_after_login.png"))
        print(f"current_url={driver.current_url}")
        print(f"title={driver.title}")

        # cookies
        cookies = driver.get_cookies()
        (OUT_DIR / "cookies.json").write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        rows = summarize(capture)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_json = OUT_DIR / f"network_{stamp}.json"
        out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

        print("\n===== interesting network calls =====")
        for r in rows[:40]:
            pd = r.get("postData")
            pd_preview = (pd[:120] + "...") if pd and len(pd) > 120 else pd
            print(
                f"{r.get('status') or '-':>4} {r.get('method'):<6} "
                f"[{r.get('type') or '?'}] {r.get('url')}"
            )
            if pd_preview:
                print(f"       POST: {pd_preview}")

        print(f"\nsaved: {out_json}")
        print(f"screenshots: {OUT_DIR}")

        # 登入成功後再點一下「標售公報」，抓後續 API
        try:
            links = driver.find_elements(By.CSS_SELECTOR, ".menu_pos a")
            for a in links:
                if "標售公報" in (a.text or ""):
                    print(">>> click 標售公報")
                    a.click()
                    time.sleep(2)
                    drain_performance_logs(driver, capture)
                    driver.save_screenshot(str(OUT_DIR / "04_bulletin.png"))
                    break
        except Exception as e:
            print(f"bulletin nav skip: {e}")

        rows2 = summarize(capture)
        out_json2 = OUT_DIR / f"network_after_nav_{stamp}.json"
        out_json2.write_text(json.dumps(rows2, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"saved after nav: {out_json2}")
        print("\n===== after bulletin nav (top) =====")
        for r in rows2[:50]:
            pd = r.get("postData")
            pd_preview = (pd[:120] + "...") if pd and len(pd) > 120 else pd
            print(
                f"{r.get('status') or '-':>4} {r.get('method'):<6} "
                f"[{r.get('type') or '?'}] {r.get('url')}"
            )
            if pd_preview:
                print(f"       POST: {pd_preview}")

        # 停留一下方便目視（有頭模式）
        if not headless:
            print("browser stays open 8s for visual check...")
            time.sleep(8)

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
