# FPG 標售案件 / 政府財物變賣歸檔

以 **HTTP** 擷取資料並寫入 **Notion**（兩套獨立 database）；GitHub Actions 平日 08:00／16:00 執行。

## 功能

### 台塑 e-fpg（既有）
- HTTP 登入（Azure OCR 驗證碼）
- 依公告日搜尋標售公報、台灣案篩選
- 報價明細／ZIP 附件 → Notion upsert（SHA-256 去重）

### 政府電子採購網・財物變賣（新增）
- 免登入 HTTP
- 依**截止投標**區間搜尋 → 詳情頁
- 寫入獨立 Notion database（`PCC_NOTION_DATABASE_ID`）
- 桌面表格 + 本月／下月 view（依截止投標）

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
| `LOGIN_URL` | 完整登入頁 URL（網域只放這裡；其他 FPG 路徑由程式推導） |
| `AZURE_ENDPOINT` / `AZURE_API_KEY` | 驗證碼 OCR |
| `NOTION_TOKEN` | Notion integration token（共用） |
| `NOTION_DATABASE_ID` | 台塑「FPG 標售案件」 |
| `PCC_NOTION_DATABASE_ID` | 政府「財物變賣」（獨立庫） |
| `NOTION_VERSION` | 預設 `2022-06-28` |
| `NOTION_FILE_UPLOAD_VERSION` | 預設 `2026-03-11` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 可選通知 |
| `ENABLE_TELEGRAM_NOTIFY` | 是否啟用（本機腳本可關） |

GitHub Actions Secrets 需含：帳密、Azure、Notion（含 `PCC_NOTION_DATABASE_ID`）、Telegram。

## 日常執行

```bash
# 台塑：今天公告 → 僅台灣案 → Notion
python -m app.scripts.run_archive
python -m app.scripts.run_archive --date 2026/07/22
python -m app.scripts.run_archive --limit 3

# 政府財物變賣：截止投標今天起 7 天
python -m app.scripts.run_pcc_archive
python -m app.scripts.run_pcc_archive --start 2026/07/23 --end 2026/07/29
python -m app.scripts.run_pcc_archive --limit 5
```

台塑 Notion 第一眼欄位：標售案號、案件類型、廠區聯絡人、品名規格／標售數量、提貨地點、公告日、報價截止日、有附件。

政府財物變賣第一眼欄位：標案案號、機關名稱、財物名稱、公告日期、截止投標、開標時間、底價金額、變賣標的所在地、聯絡人。

## 專案結構（重點）

```
app/
  scripts/
    run_archive.py              # 台塑歸檔
    run_pcc_archive.py          # 政府財物變賣歸檔
  services/
    fpg_http_client.py
    fpg_parser.py
    notion_archive_service.py   # 台塑 Notion
    pcc_http_client.py          # 採購網 HTTP
    pcc_parser.py
    pcc_notion_archive_service.py
    taiwan_case_filter.py
  models/
    case_record.py
    pcc_asset_record.py
```

## GitHub Actions

- Workflow：`.github/workflows/automation.yml`
- 排程：週一–五 台北 08:00、16:00
- Job：`run-archive`（台塑）與 `run-pcc-archive`（政府）並行
- Secrets 需含 `PCC_NOTION_DATABASE_ID`
