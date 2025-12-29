from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from app.config import settings

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 1024
    system_prompt: Optional[str] = None
    priority: int = Field(default=settings.priorities.standard)

class GenerateResponse(BaseModel):
    text: str
    token_count: int
    processing_time: float

class AdapterLoadRequest(BaseModel):
    adapter_name: str