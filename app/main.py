from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import CLEANUP_INTERVAL_SECONDS, STATIC_DIR
from app.routes import details, download, records, upload
from app.services.session_store import session_store


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        session_store.cleanup_expired()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    session_store.cleanup_expired()
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Record Exporter", lifespan=lifespan)

app.include_router(upload.router, prefix="/api")
app.include_router(records.router, prefix="/api")
app.include_router(details.router, prefix="/api")
app.include_router(download.router, prefix="/api")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
