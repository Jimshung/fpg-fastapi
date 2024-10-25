cat > README.md << EOL

# FPG Automation

自動化登入和操作 FPG 網站的工具。

## 安裝

1. 創建虛擬環境：
   \`\`\`bash
   python3 -m venv fpg_venv
   source fpg_venv/bin/activate # Linux/Mac

# 或

.\fpg_venv\Scripts\activate # Windows
\`\`\`

2. 安裝依賴：
   \`\`\`bash
   pip install -r requirements.txt
   \`\`\`

3. 安裝開發工具（可選）：
   \`\`\`bash
   pip install -r requirements-dev.txt
   \`\`\`

4. 配置環境變數：
   \`\`\`bash
   cp .env.example .env

# 編輯 .env 文件，填入實際的設定值

\`\`\`

## 使用方法

啟動服務：
\`\`\`bash
uvicorn app.main:app --reload
\`\`\`

## 開發

格式化代碼：
\`\`\`bash
black app/

# 或

autopep8 --in-place --recursive app/
\`\`\`
EOL
