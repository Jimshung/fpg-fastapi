# FPG 自動化流程

自動化搜尋和處理 FPG 相關資料的工具。

## 功能特點

- 🤖 自動化登入和搜尋
- 📊 資料擷取和處理
- 📱 Telegram 通知整合
- 🔄 GitHub Actions 自動執行
- 📸 自動截圖功能

## 環境要求

- Python 3.9+
- Chrome 瀏覽器
- ChromeDriver

## 安裝步驟

1. 複製專案

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

2. 安裝依賴

```bash
pip install -r requirements.txt
```

3. 環境設定

- 複製 `.env.example` 到 `.env`
- 填入必要的環境變數：
  - 基本設定（BASE_URL, LOGIN_URL 等）
  - Azure 設定（如果使用）
  - Telegram Bot 設定（用於通知）
  - ChromeDriver 路徑

## Telegram Bot 設定

1. 在 Telegram 中搜尋 @BotFather 創建新的 bot
2. 保存 bot token
3. 獲取您的 chat ID
4. 在 GitHub Secrets 中設置：
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

## 自動化執行

專案使用 GitHub Actions 進行自動化執行：

- 週一至週五自動執行
- 支援手動觸發
- 執行結果通過 Telegram 通知
- 自動保存執行日誌和截圖

## 本地執行

```bash
python app/scripts/run_automation.py
```

## 注意事項

- 確保所有敏感資訊都存放在 `.env` 檔案中
- 不要將 `.env` 檔案提交到版本控制
- 定期檢查 GitHub Actions 執行記錄
- 保持 ChromeDriver 版本與 Chrome 瀏覽器版本一致

## 貢獻指南

歡迎提交 Pull Requests 或建立 Issues 來改善專案。

## 授權

[您的授權方式]

## FPG FastAPI 專案

### API 測試工具

#### 生成 API 測試檔案

1. 安裝 VSCode REST Client 擴充功能
2. 確保 FastAPI 服務正在運行：

```bash
uvicorn app.main:app --reload
```

3. 執行生成腳本：

```bash
python scripts/generate_rest_client.py
```

4. 使用生成的測試檔案：
   - 打開生成的 `api_requests_*.http` 檔案
   - 在每個請求上方會看到 "Send Request" 的連結
   - 點擊連結即可發送請求

#### API 端點說明

##### POST /api/v1/search

支援以下幾種請求格式：

1. 使用日期範圍搜尋：

```json
{
  "start_date": "2024-01-01",
  "end_date": "2024-01-31"
}
```

2. 使用案號搜尋：

```json
{
  "case_number": "FPG-2024-001"
}
```

3. 使用單一日期：

```json
{
  "start_date": "2024-01-01"
}
```

4. 空請求體（使用今天日期）：

```json
{}
```

注意：不能同時指定案號和日期範圍。
