import uvicorn

if __name__ == "__main__":
    # Host 0.0.0.0 allows other computers on your network to access this AI
    # Port 8000 is the standard API port
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)