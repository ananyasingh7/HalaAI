import asyncio

from fastapi import FastAPI, HTTPException
from app.engine import engine
from app.session_manager import start_session_sweeper
from app.schemas import GenerateRequest, GenerateResponse, AdapterLoadRequest
from app.ws_chat import router as ws_router
from data.service.history_api import router as history_router
from data.service.vector_api import router as vector_router

app = FastAPI(title="HalaAI", version="1.0")
app.include_router(ws_router)
app.include_router(history_router)
app.include_router(vector_router)

@app.on_event("startup")
async def start_engine_tasks():
    await engine.start_background_tasks()
    app.state.session_sweeper = asyncio.create_task(start_session_sweeper(engine))

@app.on_event("shutdown")
async def stop_engine_tasks():
    await engine.shutdown()
    sweeper = getattr(app.state, "session_sweeper", None)
    if sweeper:
        sweeper.cancel()

@app.get("/")
def health_check():
    return {"status": "online", "current_adapter": engine.adapter_id}

@app.post("/chat", response_model=GenerateResponse)
async def chat_endpoint(request: GenerateRequest):
    """
    Main endpoint for all your apps 
    """
    try:
        result = await engine.generate_text(request)
        return GenerateResponse(
            text=result["text"],
            token_count=result["token_count"],
            processing_time=result["processing_time"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/adapters/load")
def load_adapter(request: AdapterLoadRequest):
    """
    Call this BEFORE sending a chat request if you need a specific specialist.
    """
    try:
        engine.load_adapter(request.adapter_name)
        return {"status": "success", "loaded": request.adapter_name}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Adapter not found")
