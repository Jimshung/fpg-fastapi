from fastapi.openapi.utils import get_openapi
from app.main import app

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title="FPG 自動化 API",
        version="1.0.0",
        description="FPG 自動化流程的 RESTful API",
        routes=app.routes,
        tags=[
            {
                "name": "FPG 自動化",
                "description": "FPG 網站自動化操作相關的 API"
            }
        ]
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema 