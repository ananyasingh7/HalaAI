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

class Settings(BaseModel):
    queue: QueueConfig
    priorities: Priorities

def load_config() -> Settings:
    path = Path("settings.yaml")
    if not path.exists():
        return Settings(
            queue=QueueConfig(),
            priorities=Priorities()
        )
    
    with open(path, "r") as f:
        data = yaml.safe_load(f)
        return Settings(**data)

settings = load_config()