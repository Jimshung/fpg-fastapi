# FPG 自動化流程

自動化搜尋和處理 FPG 相關資料的工具。

## 功能特點

- 🤖 自動化登入和搜尋
- 📊 資料擷取和處理
- 📱 Telegram 通知整合
- 🔄 GitHub Actions 自動執行

## 環境設置

### 1. 虛擬環境設置

確認並設置 Python 虛擬環境：

```bash
# 檢查虛擬環境是否存在
ls -la | grep fpg_venv

# 如果不存在，建立新的虛擬環境
python -m venv fpg_venv

# 啟動虛擬環境
source fpg_venv/bin/activate

# 確認 Python 解釋器位置
which python  # 應顯示 fpg_venv 中的 Python 路徑
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

## 執行方式

### 本地執行

1. **自動化腳本**（主要使用）:

```bash
python -m app.scripts.run_automation
```

2. **API 服務**（需要時）:

```bash
uvicorn app.main:app --reload
```

可用的 API 端點：

- POST `/api/v1/login`: 執行登入
- POST `/api/v1/search`: 搜尋標售公報
- GET `/api/v1/today`: 搜尋今天的標售公報

### GitHub Actions

- 自動執行：每個工作日 (週一至週五) 的 00:30 (UTC)
- 手動觸發：通過 GitHub Actions 介面

## 環境變數

請確保 `.env` 檔案包含必要的設定：

- BASE_URL
- LOGIN_URL
- USERNAME
- PASSWORD
- AZURE_ENDPOINT
- AZURE_API_KEY
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

## 注意事項

- 執行前請確保虛擬環境已啟動
- 確保所有環境變數都已正確設置
- 檢查 Chrome 和 ChromeDriver 版本相符
