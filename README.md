# FPG 標售案件歸檔

以 **HTTP** 登入 e-fpg 標售市集，擷取當日（台灣）公告案件與附件，寫入 **Notion**；GitHub Actions 平日排程執行。

## 功能

- HTTP 登入（Azure OCR 驗證碼）
- 依公告日搜尋標售公報、分頁彙整
- 台灣案篩選（排除大陸案）
- 讀取標售詢價單／報價明細重點欄位
- 下載 ZIP 附件 → Notion upsert（SHA-256 去重）
- Telegram 通知（Actions 報告）

## 環境需求

- Python 3.9+
- 建議虛擬環境：`fpg_venv`

```bash
python3 -m venv fpg_venv
source fpg_venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 再填入實際值
```

**不需要** Chrome／ChromeDriver。

## 環境變數（`.env`）

| 變數 | 用途 |
|------|------|
| `USERNAME` / `PASSWORD` | e-fpg 帳密 |
| `LOGIN_URL` | 登入頁 URL |
| `AZURE_ENDPOINT` / `AZURE_API_KEY` | 驗證碼 OCR |
| `NOTION_TOKEN` / `NOTION_DATABASE_ID` | Notion 歸檔（必填） |
| `NOTION_VERSION` | 預設 `2022-06-28` |
| `NOTION_FILE_UPLOAD_VERSION` | 預設 `2026-03-11` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 可選通知 |
| `ENABLE_TELEGRAM_NOTIFY` | 是否啟用（本機腳本可關） |

GitHub Actions Secrets 需含：帳密、Azure、Notion、Telegram（與上表對應）。

## 日常執行

```bash
# 今天公告 → 僅台灣案 → Notion
python -m app.scripts.run_archive

# 指定日期／試跑
python -m app.scripts.run_archive --date 2026/07/22
python -m app.scripts.run_archive --limit 3

# 連大陸案一併寫入（預設不會）
python -m app.scripts.run_archive --include-mainland
```

Notion 桌面表格第一眼欄位：標售案號、案件類型（一般標售／競標）、廠區聯絡人、品名規格／標售數量、提貨地點、公告日、報價截止日、有附件（公告次數僅詳細頁顯示）。歸檔時會自動確保「本月」「下個月」view（依公告日區間篩選）。

## 專案結構（重點）

```
app/
  scripts/run_archive.py          # 歸檔入口
  services/
    captcha_service.py            # OCR
    fpg_http_client.py            # HTTP session
    fpg_parser.py                 # HTML 解析
    notion_archive_service.py     # Notion upsert
    notion_zip_contents.py        # ZIP 解壓 → 頁面內容區塊
    taiwan_case_filter.py         # 台灣案篩選
  models/case_record.py
scripts/
  probes/probe_login_http.py      # 可選探測
  generate_rest_client.py
```

## API（開發用）

```bash
uvicorn app.main:app --reload
```

- `POST /api/v1/login` — HTTP 登入探測
- `POST /api/v1/search` — 依公告日搜尋（回傳台灣案計數）
- `GET /api/v1/today` — 今天公告搜尋
- `GET /health`

## GitHub Actions

- Workflow：`.github/workflows/automation.yml`
- 排程：週一–五 台北 08:00、16:00（UTC `0 0` / `0 8`）
- 執行：`python -m app.scripts.run_archive --skip-notion-view`
- 無 Chrome；需 Repository Secrets 含 `NOTION_TOKEN`、`NOTION_DATABASE_ID`

## 注意

- 勿把 `.env`、截圖、下載 ZIP commit 進 repo
- OCR 不穩時會自動重試登入
- 標案管理尚無「填寫報價單」時，仍會用公報摘要寫入 Notion（無附件）
- 公報標示「競標案件」者改走競標管理（`/j202/cmp`）；一般案走標案管理（`/j202/prc`），找不到會互備 fallback
- 有 ZIP 時除寫入「附件」屬性外，也會解壓並把 PDF／圖片寫進詳細頁內容區（標題「標售附件」；TIF 會轉 PNG）
- Notion Integration 須保持連到「FPG 標售案件」資料庫
