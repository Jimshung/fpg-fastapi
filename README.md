# FPG 標售案件 / 政府財物變賣歸檔

以 **HTTP** 擷取資料並寫入 **Notion**（兩套獨立 database）；GitHub Actions 平日 08:00／16:00 執行。

## 功能

### 台塑 e-fpg

- HTTP 登入（本機 ddddocr 驗證碼）；網域只來自 `.env` 的 `LOGIN_URL`
- 依**公告日**搜尋標售公報 → 台灣案篩選
- 報價明細／ZIP 附件 → Notion upsert（SHA-256 去重）

### 政府電子採購網・財物變賣

- 免登入 HTTP（[web.pcc.gov.tw](https://web.pcc.gov.tw)）
- **日常節奏與台塑相同**：依**公告日**搜尋（預設今天）→ 詳情頁 → Notion
- 寫入獨立 database（`PCC_NOTION_DATABASE_ID`），以系統 `pk` 去重 upsert
- 頁面 body 寫入**案情摘要**（來源短連結置頂、機關／財物／日期／底價／聯絡／資格等），side peek 不必點 View details
- 桌面表格依**公告日**排序；本月／下月 view 依**截止投標**（作業篩選用）
- 可選：`--deadline-from` 依截止投標做歷史回填（一次性）

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

| 變數                                      | 用途                                                            |
| ----------------------------------------- | --------------------------------------------------------------- |
| `FPG_USERNAME` / `FPG_PASSWORD`           | e-fpg 帳密                                                      |
| `LOGIN_URL`                               | 完整登入頁 URL（網域只放這裡；其他 FPG 路徑由 `fpg_urls` 推導） |
| `NOTION_TOKEN`                            | Notion integration token（兩庫共用）                            |
| `NOTION_DATABASE_ID`                      | 台塑「FPG 標售案件」                                            |
| `PCC_NOTION_DATABASE_ID`                  | 政府「財物變賣」（獨立庫）                                      |
| `NOTION_VERSION`                          | 預設 `2022-06-28`                                               |
| `NOTION_FILE_UPLOAD_VERSION`              | 預設 `2026-03-11`                                               |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 可選通知                                                        |
| `ENABLE_TELEGRAM_NOTIFY`                  | 是否啟用（本機腳本可關）                                        |

GitHub Actions Secrets 需含：帳密、Notion（含 `PCC_NOTION_DATABASE_ID`）、Telegram。`LOGIN_URL` 必填；不再需要 `BASE_URL`。

## 日常執行

```bash
# 台塑：今天公告 → 僅台灣案 → Notion
python -m app.scripts.run_archive
python -m app.scripts.run_archive --date 2026/07/22
python -m app.scripts.run_archive --limit 3

# 政府財物變賣：今天公告（對齊台塑節奏）
python -m app.scripts.run_pcc_archive
python -m app.scripts.run_pcc_archive --date 2026/07/22
python -m app.scripts.run_pcc_archive --start 2026/07/22 --end 2026/07/29
python -m app.scripts.run_pcc_archive --days 3 --limit 5

# 歷史回填：截止投標 ≥ 某日（迄日預設 2027/12/31；與公告日參數互斥）
python -m app.scripts.run_pcc_archive --deadline-from 2026/07/29
python -m app.scripts.run_pcc_archive --deadline-from 2026/07/29 --deadline-to 2026/12/31
```

### Notion 第一眼

- **台塑**：標售案號、案件類型、廠區聯絡人、品名規格／標售數量、提貨地點、公告日、報價截止日、有附件；詳情頁可展開 ZIP 附件內容。
- **政府財物變賣（表格）**：標案案號、機關名稱、財物名稱、公告日期、截止投標、開標時間、底價金額、變賣標的所在地、聯絡人。
- **政府財物變賣（side peek）**：案情摘要正文（來源連結 → 機關／財物／日期／底價／所在地／聯絡 → 資格／文件領取／附加說明）。

## 專案結構（重點）

```
app/
  scripts/
    run_archive.py                 # 台塑歸檔
    run_pcc_archive.py             # 政府財物變賣歸檔
  services/
    fpg_urls.py                    # FPG 路徑／網域（來自 LOGIN_URL）
    fpg_http_client.py
    fpg_parser.py
    notion_archive_service.py      # 台塑 Notion
    pcc_http_client.py             # 採購網 HTTP（公告日／截止投標搜尋）
    pcc_parser.py
    pcc_notion_archive_service.py  # 財物變賣 Notion（含案情摘要 body）
    taiwan_case_filter.py
  utils/
    telegram_digest.py             # Telegram 當日速覽（短訊息）
  models/
    case_record.py
    pcc_asset_record.py
tests/
  test_*.py                        # 單元測試（不需網路）
  http/                            # REST Client 探測用
```

## GitHub Actions

- Workflow：`.github/workflows/automation.yml`
- 排程：週一–五 台北 08:00、16:00
- Job：`run-archive`（台塑，**僅早上 08:00**／手動）與 `run-pcc-archive`（政府，早／晚皆跑）並行
- 台塑歸檔遇登入失敗時，CI 會冷卻後最多再試 3 輪
- 各 job 歸檔後發 **Telegram 當日速覽**（短清單；完整 log 在 Actions／artifact）
- PCC job 使用 `--skip-notion-view`（避免每次改 view）；本機完整跑可省略該旗標以調整桌面／月 view
- Secrets 需含 `PCC_NOTION_DATABASE_ID`、`LOGIN_URL`、`FPG_USERNAME`、`FPG_PASSWORD`（勿再依賴 `BASE_URL`／系統 `USERNAME`）
