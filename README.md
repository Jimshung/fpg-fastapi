# FPG 標售案件歸檔

以 **HTTP** 登入 e-fpg 標售市集，擷取當日（台灣）公告案件與附件，寫入 **Notion**；可選 Telegram 通知。不再依賴模擬點選作為主路徑。

## 功能

- HTTP 登入（Azure OCR 驗證碼）
- 依公告日搜尋標售公報、分頁彙整
- 台灣案篩選（排除大陸案）
- 讀取標售詢價單／報價明細重點欄位
- 下載 ZIP 附件 → Notion upsert（SHA-256 去重）
- GitHub Actions 可排程（舊 Selenium 自動化仍在，預計下一階段移除）

## 環境需求

- Python 3.9+
- 建議虛擬環境：`fpg_venv`

```bash
python3 -m venv fpg_venv
source fpg_venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 再填入實際值
```

## 環境變數（`.env`）

| 變數 | 用途 |
|------|------|
| `USERNAME` / `PASSWORD` | e-fpg 帳密 |
| `LOGIN_URL` | 登入頁 URL |
| `AZURE_ENDPOINT` / `AZURE_API_KEY` | 驗證碼 OCR |
| `NOTION_TOKEN` / `NOTION_DATABASE_ID` | Notion 歸檔 |
| `NOTION_VERSION` | 預設 `2022-06-28` |
| `NOTION_FILE_UPLOAD_VERSION` | 預設 `2026-03-11`（上傳／Views） |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 可選通知 |
| `ENABLE_TELEGRAM_NOTIFY` | 是否啟用 Telegram |

## 日常執行（建議）

```bash
# 今天公告 → 僅台灣案 → Notion
python -m app.scripts.run_archive

# 指定日期
python -m app.scripts.run_archive --date 2026/07/22

# 試跑前 N 案
python -m app.scripts.run_archive --limit 3

# 若要連大陸案一併寫入（預設不會）
python -m app.scripts.run_archive --include-mainland
```

Notion 桌面表格第一眼欄位：標售案號、廠區聯絡人、公告次數、品名規格／標售數量、提貨地點、公告日、報價截止日、有附件。

## 專案結構（重點）

```
app/
  scripts/run_archive.py          # 歸檔入口
  scripts/run_automation.py       # 舊 Selenium 轉報價流程（待移除）
  services/
    fpg_http_client.py            # HTTP session
    fpg_parser.py                 # HTML 解析
    notion_archive_service.py     # Notion upsert
    taiwan_case_filter.py         # 台灣案篩選
  models/case_record.py
scripts/
  probes/                         # 探測用，非正式排程
  ci/                             # CI helpers
  generate_rest_client.py
```

## 舊路徑（Selenium）

```bash
python -m app.scripts.run_automation
```

此路徑仍會開 Chrome／模擬點選做「轉報價」。產品方向已改為 **讀取＋Notion 歸檔**，Selenium 相關程式（`LoginService`、`selenium_utils`、ChromeDriver CI 等）規劃於**下一階段刪除或改為可選**，請以 `run_archive` 為主。

本機探測（需 ChromeDriver）仍可放在 `scripts/probes/`，非正式流程。

## API（開發用）

```bash
uvicorn app.main:app --reload
python scripts/generate_rest_client.py   # 產生 tests/http/test.http
```

## GitHub Actions

- Workflow：`.github/workflows/automation.yml`
- 目前仍跑 `run_automation`（Selenium）；之後應改為 `run_archive` 並拿掉 ChromeDriver 安裝步驟

## 注意

- 勿把 `.env`、截圖、下載 ZIP commit 進 repo（已在 `.gitignore`）
- OCR 不穩時會自動重試登入
- 標案管理尚無「填寫報價單」時，仍會用公報摘要寫入 Notion（無附件）
