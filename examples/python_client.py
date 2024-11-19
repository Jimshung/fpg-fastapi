from fpg_client import Configuration, ApiClient
from fpg_client.api.default_api import DefaultApi

# 配置客戶端
configuration = Configuration(host="http://localhost:8000")
api_client = ApiClient(configuration)
api = DefaultApi(api_client)

# 使用生成的客戶端
try:
    # 登入
    login_response = api.login_api_v1_login_post()
    print(f"登入結果: {login_response}")
    
    # 搜尋今天的公報
    today_result = api.search_today_bulletins_api_v1_today_get()
    print(f"今日搜尋結果: {today_result}")
    
except Exception as e:
    print(f"發生錯誤: {e}") 