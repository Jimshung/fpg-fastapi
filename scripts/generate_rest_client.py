import json
import requests
from datetime import datetime

def generate_rest_client_file():
    # 獲取 OpenAPI 規範
    response = requests.get('http://localhost:8000/openapi.json')
    api_spec = response.json()
    
    # 生成 REST Client 格式的請求
    requests_content = [
        "### FastAPI 內建文檔\n",
        "# 以下路由可在瀏覽器中訪問：",
        "# - /docs         Swagger UI 文檔",
        "# - /redoc        ReDoc 文檔",
        "# - /openapi.json OpenAPI 規範",
        "\n###\n"
    ]
    
    for path, methods in api_spec['paths'].items():
        # 跳過文檔相關的路由
        if path in ['/docs', '/redoc', '/openapi.json']:
            continue
            
        for method, details in methods.items():
            # 添加註解
            requests_content.append(f"### {details.get('summary', path)}")
            
            # 基本請求
            requests_content.append(f"{method.upper()} http://localhost:8000{path}")
            requests_content.append("Content-Type: application/json")
            
            # 如果有請求體，添加範例數據
            if 'requestBody' in details:
                example = details.get('requestBody', {}).get('content', {}).get('application/json', {}).get('example', {})
                if example:
                    requests_content.append("")  # 空行
                    requests_content.append(json.dumps(example, indent=2))
            
            requests_content.append("\n###\n")  # 請求之間的分隔符
    
    # 保存到 .http 檔案
    filename = f"api_requests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.http"
    with open(filename, 'w') as f:
        f.write("\n".join(requests_content))
    
    print(f"REST Client requests saved to: {filename}")
    print("\n使用方法：")
    print("1. 在 VSCode 中安裝 'REST Client' 擴充功能")
    print("2. 打開生成的 .http 檔案")
    print("3. 在每個請求上方會看到 'Send Request' 的連結")
    print("4. 點擊 'Send Request' 即可發送請求")

if __name__ == '__main__':
    generate_rest_client_file() 