from pydantic import BaseModel

class LoginResponse(BaseModel):
    status: str
    message: str