from __future__ import annotations

import asyncio
import contextlib
import json
import queue
import threading

from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.environment_orchestrator import run_environment
from services.event_emitter import EventEmitter, QueueLogWriter


app = FastAPI(title="AI K8s Twin API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "AI K8s Twin API",
        "docs": "http://localhost:8000/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}



class EnvironmentRunRequest(BaseModel):
    github_url: str = Field(min_length=1)
    cpu: str = Field(min_length=1)
    memory: str = Field(min_length=1)
    vus: str = Field(min_length=1)
    duration: str = Field(min_length=1)
    environments: List[str] = Field(min_length=1)
    mode: str = "binary_search"


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/environment-orchestrator/run")
async def start_environment_orchestrator(request: EnvironmentRunRequest):
    events = queue.Queue()
    emitter = EventEmitter(events)
    output = QueueLogWriter(emitter)
    sentinel = object()

    def execute():
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = run_environment(
                    **request.model_dump(),
                    event_emitter=emitter,
                )
            emitter.emit("result", {"status": "completed", "result": result})
            emitter.emit("aggregate_complete", {"status": "completed", "total": len(result), "results": result})
        except Exception as error:
            emitter.emit("error", {"status": "failed", "message": str(error)})
        finally:
            events.put(sentinel)

    threading.Thread(target=execute, daemon=True).start()

    async def stream():
        while True:
            try:
                event = await asyncio.to_thread(events.get)
            except asyncio.CancelledError:
                return
            if event is sentinel:
                yield _sse("done", {"status": "finished"})
                return
            yield _sse(event[0], event[1])

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )