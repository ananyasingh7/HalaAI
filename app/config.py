import yaml
from pydantic import BaseModel
from pathlib import Path


class QueueConfig(BaseModel):
    max_size: int = 100
    starvation_prevention: bool = True
    aging_interval_sec: int = 60
    default_priority: int = 10


class Priorities(BaseModel):
    ui: int = 0
    critical: int = 1
    standard: int = 10
    background: int = 20


class EngineMemoryConfig(BaseModel):
    # Rotating KV cache cap to prevent runaway memory on long context requests.
    max_kv_size: int = 2048
    # Hard cap on prompt tokens after templating (history/memory/search included).
    max_prompt_tokens: int = 1024
    # Extra room reserved for template/control tokens and generation bookkeeping.
    prompt_token_reserve: int = 128
    # Preserve the leading instruction tokens when trimming oversized prompts.
    preserve_prompt_head_tokens: int = 256
    # Optional KV cache quantization controls (disabled by default).
    kv_bits: int | None = None
    kv_group_size: int = 64
    quantized_kv_start: int = 0
    # Memory cleanup behavior after each inference request.
    force_gc_after_request: bool = True
    # Metal wired memory controls.
    enable_metal_wired_limit: bool = True
    metal_wired_limit_gb: float | None = None
    metal_wired_limit_ratio: float = 0.67


class ChromaMemoryConfig(BaseModel):
    # Chroma only supports LRU for segment cache policy.
    segment_cache_policy: str = "LRU"
    memory_limit_bytes: int = 536870912  # 512 MB


class Settings(BaseModel):
    queue: QueueConfig
    priorities: Priorities
    engine_memory: EngineMemoryConfig = EngineMemoryConfig()
    chroma_memory: ChromaMemoryConfig = ChromaMemoryConfig()


def load_config() -> Settings:
    path = Path("settings.yaml")
    if not path.exists():
        return Settings(
            queue=QueueConfig(),
            priorities=Priorities(),
            engine_memory=EngineMemoryConfig(),
            chroma_memory=ChromaMemoryConfig(),
        )
    
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
        return Settings(**data)


settings = load_config()
