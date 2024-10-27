# FPG FastAPI Automation

自動化登入和處理 FPG 網站的 FastAPI 應用。

## 安裝步驟

1. 建立虛擬環境

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows
```

2. 安裝依賴

```bash
pip install -r requirements.txt
```

3. 設定環境變數

```bash
cp .env.example .env
# 編輯 .env 文件填入實際值
```

4. 運行應用

```bash
uvicorn app.main:app --reload
```

## GitHub Actions 自動化

此專案使用 GitHub Actions 進行自動化運行：

- 每個工作日台灣時間早上 8:00 自動執行
- 可以手動觸發運行
- 運行結果和截圖會被保存為 artifacts

## 目錄結構

```
.
├── app/
│   ├── api/
│   ├── core/
│   ├── models/
│   ├── services/
│   └── utils/
├── .github/workflows/
├── requirements.txt
├── .env.example
└── README.md
```
