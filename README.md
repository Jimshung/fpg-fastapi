# FPG 自動化流程

自動化搜尋和處理 FPG 相關資料的工具。

## 功能特點

- 🤖 自動化登入和搜尋
- 📊 資料擷取和處理
- 📱 Telegram 通知整合
- 🔄 GitHub Actions 自動執行
- 📝 REST Client API 測試支援

## 環境需求

### Python 版本

- Python 3.9.18
- 建議使用 pyenv 進行版本管理：`pyenv install 3.9.18`
- 或使用 Homebrew：`brew install python@3.9`

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

### 3. ChromeDriver 設定 (本機測試用)

確保 Chrome 瀏覽器和 ChromeDriver 版本相匹配：

```bash
# 檢查 Chrome 和 ChromeDriver 版本
google-chrome --version
chromedriver --version

# 如果版本不匹配，更新 ChromeDriver
brew upgrade chromedriver

# 如果更新後仍有問題，可以重新安裝
brew uninstall chromedriver && brew install chromedriver

# 確認 ChromeDriver 路徑和權限
ls -l /opt/homebrew/bin/chromedriver
chmod +x /opt/homebrew/bin/chromedriver
```

### 4. Python 環境重置（如遇到問題時使用）

如果遇到 Python 相關的問題（如 segmentation fault），可以嘗試以下步驟：

```bash
# 停用當前的虛擬環境
deactivate

# 移除 pyenv 的 Python 版本
pyenv uninstall 3.9.18

# 確保使用 Homebrew 的 Python
brew unlink python@3.9 && brew link python@3.9 --force

# 移除現有的虛擬環境
rm -rf fpg_venv

# 使用 Homebrew 的 Python 創建新的虛擬環境
/opt/homebrew/bin/python3.9 -m venv fpg_venv

# 啟動虛擬環境
source fpg_venv/bin/activate

# 升級 pip
python -m pip install --upgrade pip

# 安裝依賴
pip install -r requirements.txt
```

### 5. 疑難排解

如果遇到自動化腳本執行問題，可以嘗試以下步驟：

```bash
# 1. 清除 Python 快取文件
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -r {} +

# 2. 使用 PYTHONUNBUFFERED 執行腳本（可以看到即時日誌輸出）
PYTHONUNBUFFERED=1 python -m app.scripts.run_automation
```

### 6. API 服務重啟流程

```bash
# 1. 檢查當前運行的 uvicorn 進程
ps aux | grep uvicorn

# 2. 停止現有的 uvicorn 進程（如果有的話）
# 假設 PID 為 1234
kill -9 1234

# 3. 重新啟動 API 服務
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 執行方式

### 本地執行

1. **自動化腳本**（主要使用）:

```bash
python -m app.scripts.run_automation
```

2. **API 服務**（開發測試用）:

```bash
# 啟動 FastAPI 服務
uvicorn app.main:app --reload

# 生成最新的 API 測試檔案
python scripts/generate_rest_client.py
```

### API 測試

本專案使用 VSCode REST Client 擴充功能進行 API 測試：

1. 在 VSCode 中安裝 "REST Client" 擴充功能
2. 啟動 FastAPI 服務
3. 執行 `python scripts/generate_rest_client.py` 生成最新的 API 測試檔案
4. 打開 `tests/http/test.http`
5. 點擊每個請求上方的 "Send Request" 進行測試

可用的 API 端點：

- GET `/health`: 健康檢查
- POST `/api/v1/login`: 執行登入
- POST `/api/v1/search`: 搜尋標售公報
- GET `/api/v1/today`: 搜尋今天的標售公報
- GET `/api/v1/tender/list`: 獲取標售案件列表
- GET `/api/v1/tender/detail/{tender_no}`: 獲取特定標售案件詳細資訊

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
- API 測試前確保 FastAPI 服務正在運行
