from datetime import datetime
from sqlmodel import SQLModel, Field, create_engine, Session

sqlite_file_name = "inference_logs.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url)

class InferenceLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Context
    request_id: str
    adapter_name: str | None = "base"
    
    # Content (Text)
    prompt: str
    system_prompt: str | None
    response_text: str
    
    # Physics (The Stats)
    tokens_in: int
    tokens_out: int
    total_time_sec: float
    tokens_per_sec: float     # (tokens_out / total_time_sec)
    
    # Config
    model_name: str
    temp: float

    # Hardware Stats
    gpu_usage_pct: float = 0.0
    cpu_usage_pct: float = 0.0
    gpu_temp_c: float = 0.0
    ram_usage_pct: float = 0.0
    wattage: float = 0.0

def init_db():
    SQLModel.metadata.create_all(engine)

def log_interaction(log_entry: InferenceLog):
    """Fire and forget logger."""
    with Session(engine) as session:
        session.add(log_entry)
        session.commit()


def log_stats(log_entry: InferenceLog):
    """Backward-compatible alias for log_interaction."""
    log_interaction(log_entry)
