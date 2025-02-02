import json
import requests
from datetime import datetime, date

def generate_rest_client_file():
    # 獲取 OpenAPI 規範
    response = requests.get('http://localhost:8000/openapi.json')
    api_spec = response.json()
    
    # 生成 REST Client 格式的請求
    requests_content = [
        "### FastAPI 內建文檔",
        "# 以下路由可在瀏覽器中訪問：",
        "# - /docs         Swagger UI 文檔",
        "# - /redoc        ReDoc 文檔",
        "# - /openapi.json OpenAPI 規範",
        "\n",
        "### 健康檢查",
        "GET http://localhost:8000/health",
        "\n",
        "### 測試登入功能",
        "POST http://localhost:8000/api/v1/login",
        "Content-Type: application/json",
        "\n",
        "### 搜尋標售公報 - 使用日期範圍",
        "POST http://localhost:8000/api/v1/search",
        "Content-Type: application/json",
        "",
        json.dumps({
            "start_date": "2025-01-06",
            "end_date": "2024-12-06"
        }, indent=4),
        "\n",
        "### 搜尋標售公報 - 使用案號",
        "POST http://localhost:8000/api/v1/search",
        "Content-Type: application/json",
        "",
        json.dumps({
            "case_number": "FPG-2024-001"
        }, indent=4),
        "\n",
        "### 搜尋標售公報 - 使用單一日期（結束日期會自動設為開始日期）",
        "POST http://localhost:8000/api/v1/search",
        "Content-Type: application/json",
        "",
        json.dumps({
            "start_date": "2024-01-01"
        }, indent=4),
        "\n",
        "### 搜尋標售公報 - 空請求體（使用今天日期作為預設值）",
        "POST http://localhost:8000/api/v1/search",
        "Content-Type: application/json",
        "",
        json.dumps({}, indent=4),
        "\n",
        "### 搜尋今天的標售公報",
        "GET http://localhost:8000/api/v1/today",
        "\n",
        "### 獲取標售案件列表",
        "GET http://localhost:8000/api/v1/tender/list",
        "\n",
        "### 獲取特定標售案件詳細資訊",
        "GET http://localhost:8000/api/v1/tender/detail/{tender_no}",
        "\n"
    ]
    
    # 添加其他 API 端點
    for path, methods in api_spec['paths'].items():
        # 跳過已經處理的路由
        if path in ['/docs', '/redoc', '/openapi.json', '/api/v1/search', 
                   '/api/v1/tender/list', '/api/v1/tender/detail/{tender_no}',
                   '/health', '/api/v1/login', '/api/v1/today']:
            continue
            
        for method, details in methods.items():
            requests_content.extend([
                f"### {details.get('summary', path)}",
                f"{method.upper()} http://localhost:8000{path}",
                "Content-Type: application/json" if method.upper() in ['POST', 'PUT', 'PATCH'] else "",
                ""
            ])
            
            # 如果有請求體，添加範例數據
            if 'requestBody' in details:
                example = details.get('requestBody', {}).get('content', {}).get('application/json', {}).get('example', {})
                if example:
                    requests_content.append(json.dumps(example, indent=4))
            
            requests_content.append("\n")
    
    # 添加使用說明
    requests_content.extend([
        "# 使用說明：",
        "# 1. 在 VSCode 中安裝 'REST Client' 擴充功能",
        "# 2. 在每個請求上方會看到 'Send Request' 的連結",
        "# 3. 點擊 'Send Request' 即可發送請求並查看結果"
    ])
    
    # 保存到 test.http 檔案
    with open('tests/http/test.http', 'w') as f:
        f.write("\n".join(requests_content))
    
    print("REST Client requests 已更新到: tests/http/test.http")

if __name__ == '__main__':
    generate_rest_client_file() 