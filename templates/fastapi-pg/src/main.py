"""Application entry point."""
import uvicorn
from fastapi import FastAPI

app = FastAPI(title="{{ name }}")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
