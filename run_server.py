import uvicorn

if __name__ == "__main__":
    try:
        import websockets  # noqa: F401
    except Exception:
        try:
            import wsproto  # noqa: F401
        except Exception as e:
            raise RuntimeError(
                "WebSocket support is not installed. Install dependencies with "
                "`python -m pip install -r requirements.txt` (or `pip install 'uvicorn[standard]'`)."
            ) from e

    # Host 0.0.0.0 allows other computers on your network to access this AI
    # Port 8000 is the standard API port
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
