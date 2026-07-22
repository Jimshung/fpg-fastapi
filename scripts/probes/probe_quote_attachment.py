"""登入 FPG 標案管理並探測報價單附件下載。

此腳本只進入報價單與下載附件，不填價、不儲存、不送出報價。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin

import aiohttp
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException,
    UnexpectedAlertPresentException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
load_dotenv(ROOT / ".env")

from app.core.config import settings
from app.services.captcha_service import CaptchaService


CASE_NUMBER = os.getenv("PROBE_CASE_NUMBER", "03-UT1GN9")
DRIVER_PATH = Path(
    os.getenv(
        "PROBE_CHROMEDRIVER",
        "/tmp/chromedriver-extract/chromedriver-mac-arm64/chromedriver",
    )
)
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = ROOT / "app" / "utils" / "screenshots" / "quote_probe" / STAMP
DOWNLOAD_DIR = OUT_DIR / "downloads"
OUT_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def create_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--window-size=1500,1000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if os.getenv("PROBE_HEADLESS", "false").lower() == "true":
        options.add_argument("--headless=new")
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(DOWNLOAD_DIR),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    driver = webdriver.Chrome(
        service=Service(executable_path=str(DRIVER_PATH)),
        options=options,
    )
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(2)
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def save_state(driver: webdriver.Chrome, name: str) -> None:
    driver.save_screenshot(str(OUT_DIR / f"{name}.png"))
    (OUT_DIR / f"{name}.html").write_text(
        driver.page_source,
        encoding="utf-8",
    )
    print(f"[state] {name}: {driver.current_url}")


def accept_alert_if_present(driver: webdriver.Chrome) -> str | None:
    try:
        alert = driver.switch_to.alert
        text = alert.text
        alert.accept()
        print(f"[alert] accepted: {text}")
        return text
    except NoAlertPresentException:
        return None


def wait_document(driver: webdriver.Chrome, timeout: int = 30) -> None:
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except UnexpectedAlertPresentException:
        accept_alert_if_present(driver)
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )


async def login(driver: webdriver.Chrome) -> None:
    captcha_service = CaptchaService()
    for attempt in range(1, 11):
        print(f"[login] attempt {attempt}/10")
        driver.get(settings.LOGIN_URL)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "id"))
        )

        username = driver.find_element(By.NAME, "id")
        password = driver.find_element(By.NAME, "passwd")
        username.clear()
        password.clear()
        username.send_keys(settings.USERNAME)
        password.send_keys(settings.PASSWORD)

        captcha_image = driver.find_element(By.ID, "vcode")
        captcha_text = await captcha_service.solve_captcha(
            captcha_image.screenshot_as_png
        )
        print(f"[login] OCR={captcha_text!r}")
        if captcha_text == "error" or len(captcha_text) != 4:
            continue

        captcha = driver.find_element(By.NAME, "vcode")
        captcha.clear()
        captcha.send_keys(captcha_text)
        driver.find_element(
            By.CSS_SELECTOR,
            'input[type="submit"][value="登入"]',
        ).click()
        wait_document(driver)
        time.sleep(1)

        if "驗證碼錯誤" in driver.page_source:
            print("[login] captcha rejected")
            continue
        if driver.find_elements(By.LINK_TEXT, "標案管理"):
            print("[login] success")
            save_state(driver, "01_logged_in")
            return
        print("[login] unexpected response, retrying")

    raise RuntimeError("登入失敗：驗證碼重試已耗盡")


def click_and_wait(
    driver: webdriver.Chrome,
    element,
    *,
    allow_new_window: bool = False,
) -> None:
    old_handles = set(driver.window_handles)
    old_url = driver.current_url
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});",
        element,
    )
    element.click()
    deadline = time.time() + 10
    switched_window = False
    while time.time() < deadline:
        alert_text = accept_alert_if_present(driver)
        new_handles = set(driver.window_handles) - old_handles
        if allow_new_window and new_handles:
            driver.switch_to.window(new_handles.pop())
            print("[window] switched to popup")
            switched_window = True
            break
        try:
            if driver.current_url != old_url:
                break
        except UnexpectedAlertPresentException:
            continue
        if alert_text:
            time.sleep(1)
            continue
        time.sleep(0.25)

    if allow_new_window and not switched_window:
        try:
            new_handles = set(driver.window_handles) - old_handles
            if new_handles:
                driver.switch_to.window(new_handles.pop())
                print("[window] switched to popup")
                switched_window = True
        finally:
            if not switched_window:
                accept_alert_if_present(driver)
            print("[window] no new window; continuing in current tab")

    wait_document(driver)
    time.sleep(1)


def dump_page_controls(driver: webdriver.Chrome, name: str) -> dict[str, Any]:
    controls = driver.execute_script(
        """
        return {
          links: Array.from(document.querySelectorAll('a')).map(a => ({
            text: (a.innerText || a.textContent || '').trim(),
            href: a.href,
            onclick: a.getAttribute('onclick'),
            target: a.target
          })),
          inputs: Array.from(document.querySelectorAll('input')).map(i => ({
            type: i.type, name: i.name, value: i.value,
            onclick: i.getAttribute('onclick')
          })),
          forms: Array.from(document.forms).map(f => ({
            name: f.name, action: f.action, method: f.method,
            fields: Array.from(f.elements).map(e => ({
              type: e.type, name: e.name, value: e.value
            }))
          }))
        };
        """
    )
    (OUT_DIR / f"{name}_controls.json").write_text(
        json.dumps(controls, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return controls


def collect_network(driver: webdriver.Chrome) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for entry in driver.get_log("performance"):
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, json.JSONDecodeError):
            continue
        if message.get("method") not in {
            "Network.requestWillBeSent",
            "Network.responseReceived",
        }:
            continue
        params = message.get("params", {})
        request = params.get("request", {})
        response = params.get("response", {})
        event = {
            "method": message.get("method"),
            "url": request.get("url") or response.get("url"),
            "httpMethod": request.get("method"),
            "postData": request.get("postData"),
            "status": response.get("status"),
            "mimeType": response.get("mimeType"),
        }
        if event["postData"]:
            event["postData"] = re.sub(
                r"(^|&)(passwd|id|vcode)=[^&]*",
                lambda match: match.group(1) + match.group(2) + "=***",
                event["postData"],
            )
        events.append(event)
    return events


def candidate_attachment_elements(driver: webdriver.Chrome) -> list[Any]:
    xpath = (
        "//*[self::a or self::input or self::button]"
        "[contains(normalize-space(.), '附件下載')"
        " or contains(@value, '附件下載')"
        " or contains(translate(@href, 'ZIP', 'zip'), '.zip')"
        " or contains(translate(@onclick, 'ZIP', 'zip'), '.zip')]"
    )
    return driver.find_elements(By.XPATH, xpath)


def attachment_candidates_from_controls(
    controls: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates = []
    for link in controls["links"]:
        haystack = " ".join(
            str(link.get(key) or "")
            for key in ("text", "href", "onclick")
        ).lower()
        if "附件" in haystack or ".zip" in haystack or "download" in haystack:
            candidates.append(link)
    return candidates


def filename_from_response(headers: aiohttp.typedefs.LooseHeaders, url: str) -> str:
    disposition = headers.get("Content-Disposition", "")
    encoded = re.search(r"filename\\*=UTF-8''([^;]+)", disposition, re.I)
    if encoded:
        return Path(unquote(encoded.group(1))).name
    plain = re.search(r'filename="?([^";]+)"?', disposition, re.I)
    if plain:
        return Path(plain.group(1)).name
    fallback = Path(url.split("?", 1)[0]).name or "attachment.zip"
    return fallback if fallback.lower().endswith(".zip") else f"{fallback}.zip"


async def download_direct_candidates(
    driver: webdriver.Chrome,
    candidates: list[dict[str, Any]],
) -> list[Path]:
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    timeout = aiohttp.ClientTimeout(total=60)
    downloaded: list[Path] = []
    async with aiohttp.ClientSession(
        cookie_jar=cookie_jar,
        timeout=timeout,
        headers={
            "User-Agent": driver.execute_script("return navigator.userAgent"),
            "Referer": driver.current_url,
        },
    ) as session:
        for cookie in driver.get_cookies():
            session.cookie_jar.update_cookies(
                {cookie["name"]: cookie["value"]}
            )
        for candidate in candidates:
            href = candidate.get("href")
            if not href or href.startswith("javascript:"):
                continue
            url = urljoin(driver.current_url, href)
            print(f"[download] HTTP GET {url}")
            async with session.get(url, allow_redirects=True) as response:
                content = await response.read()
                content_type = response.headers.get("Content-Type", "")
                disposition = response.headers.get("Content-Disposition", "")
                print(
                    f"[download] {response.status} {content_type} "
                    f"{disposition} bytes={len(content)}"
                )
                if response.status != 200:
                    continue
                if (
                    "zip" not in content_type.lower()
                    and not content.startswith(b"PK")
                    and ".zip" not in url.lower()
                ):
                    continue
                filename = filename_from_response(response.headers, str(response.url))
                path = DOWNLOAD_DIR / filename
                path.write_bytes(content)
                downloaded.append(path)
    return downloaded


def wait_for_browser_downloads(timeout: int = 30) -> list[Path]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        partials = list(DOWNLOAD_DIR.glob("*.crdownload"))
        files = [path for path in DOWNLOAD_DIR.iterdir() if path.is_file()]
        if files and not partials:
            return files
        time.sleep(0.5)
    return [
        path
        for path in DOWNLOAD_DIR.iterdir()
        if path.is_file() and path.suffix != ".crdownload"
    ]


def inspect_zip(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        print(f"[zip] not a valid ZIP: {path}")
        return
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    print(f"[zip] {path.name}: {len(names)} entries")
    for name in names[:20]:
        print(f"      {name}")


async def main() -> None:
    print(f"[probe] case={CASE_NUMBER}")
    print(f"[probe] output={OUT_DIR}")
    driver = create_driver()
    network_events: list[dict[str, Any]] = []
    try:
        await login(driver)

        bid_management = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "標案管理"))
        )
        click_and_wait(driver, bid_management)
        save_state(driver, "02_bid_management")

        case_input = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.NAME, "srh_tndsalno"))
        )
        case_input.clear()
        case_input.send_keys(CASE_NUMBER)
        search_button = driver.find_element(
            By.CSS_SELECTOR,
            'input[type="button"][value="開始搜尋"],'
            'input[type="submit"][value="開始搜尋"]',
        )
        click_and_wait(driver, search_button)
        save_state(driver, "03_search_result")

        quote_buttons = driver.find_elements(
            By.XPATH,
            "//*[self::input or self::button or self::a]"
            "[contains(@value, '填寫報價單')"
            " or contains(normalize-space(.), '填寫報價單')]",
        )
        if not quote_buttons:
            controls = dump_page_controls(driver, "03_search_result")
            raise RuntimeError(
                "搜尋結果找不到「填寫報價單」；控制項已輸出供分析："
                f"{len(controls['inputs'])} inputs"
            )

        click_and_wait(driver, quote_buttons[0], allow_new_window=True)
        accept_alert_if_present(driver)
        save_state(driver, "04_quote_popup")

        safety_tabs = driver.find_elements(
            By.XPATH,
            "//a[normalize-space(.)='安全告知單']"
            "|//input[@value='安全告知單']"
            "|//button[normalize-space(.)='安全告知單']",
        )
        if safety_tabs:
            print("[quote] opening 安全告知單 as required")
            click_and_wait(driver, safety_tabs[0])
            accept_alert_if_present(driver)
            save_state(driver, "04a_safety_notice")

        quote_tabs = driver.find_elements(
            By.XPATH,
            "//a[normalize-space(.)='報價單']"
            "|//input[@value='報價單']"
            "|//button[normalize-space(.)='報價單']",
        )
        if quote_tabs:
            click_and_wait(driver, quote_tabs[0])
        save_state(driver, "05_quote_form")
        controls = dump_page_controls(driver, "05_quote_form")

        candidates = attachment_candidates_from_controls(controls)
        print("[attachment] candidates:")
        for candidate in candidates:
            print(json.dumps(candidate, ensure_ascii=False))

        downloaded = await download_direct_candidates(driver, candidates)
        if not downloaded:
            elements = candidate_attachment_elements(driver)
            print(f"[attachment] clickable elements={len(elements)}")
            for index, element in enumerate(elements):
                try:
                    print(
                        f"[attachment] click #{index + 1}: "
                        f"{element.tag_name} {element.text!r} "
                        f"{element.get_attribute('value')!r}"
                    )
                    element.click()
                    accept_alert_if_present(driver)
                    files = wait_for_browser_downloads()
                    if files:
                        downloaded.extend(files)
                        break
                except Exception as error:
                    print(f"[attachment] click failed: {error}")

        network_events.extend(collect_network(driver))
        (OUT_DIR / "network.json").write_text(
            json.dumps(network_events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        unique_downloads = list(dict.fromkeys(downloaded))
        if not unique_downloads:
            raise RuntimeError(
                "已到報價單頁，但未找到或未能下載 ZIP；"
                "HTML、控制項與 Network 已保存。"
            )
        for path in unique_downloads:
            print(f"[download] saved: {path}")
            inspect_zip(path)
    finally:
        try:
            network_events.extend(collect_network(driver))
            (OUT_DIR / "network_final.json").write_text(
                json.dumps(network_events, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
        if os.getenv("PROBE_KEEP_BROWSER", "false").lower() == "true":
            print("[probe] keeping browser open for 30 seconds")
            time.sleep(30)
        driver.quit()


if __name__ == "__main__":
    asyncio.run(main())
