from pydantic import BaseModel
from typing import Optional, List, Dict

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 1024
    system_prompt: Optional[str] = None

class GenerateResponse(BaseModel):
    text: str
    token_count: int
    processing_time: float

class AdapterLoadRequest(BaseModel):
    adapter_name: str