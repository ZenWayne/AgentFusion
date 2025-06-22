from pydantic import BaseModel

class Config(BaseModel):
    api_keys: dict[str, str]