"""FastAPI server and REST API for Technocore Work Graph Dashboard."""

from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from client import TechnocoreClient
from config import (
    DID,
    DID_FP,
    DID_SHARD,
    HOST,
    MAILBOX_NAME,
    PORT,
    PROOFS_NS,
    REPORTS_NS,
    STATE_NS,
    TECHNOCORE_HOST,
)
from daemon import WorkGraphDaemon
from observer import NetworkObserver
from state import StateManager
from task_engine import TaskEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("workgraph.server")

# Global instances
client = TechnocoreClient()
state_mgr = StateManager(client)
observer = NetworkObserver(client, state_mgr)
task_engine = TaskEngine(client, observer, state_mgr)
daemon = WorkGraphDaemon(client, state_mgr, observer, task_engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Technocore Work Graph Server...")
    await daemon.initialize()
    await daemon.start()
    yield
    # Shutdown
    logger.info("Shutting down Technocore Work Graph Server...")
    await daemon.stop()
    await client.close()


app = FastAPI(
    title="Technocore Work Graph API",
    description="Observatory and Task Engine for technocore.chat",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parent / "web"
WEB_DIR.mkdir(exist_ok=True)


class TaskRequestPayload(BaseModel):
    action: str
    target: str | None = None
    reply_to: str | None = None


@app.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """Return identity, mailbox, cursors, and system health."""
    return {
        "status": "online",
        "did": DID,
        "did_abbreviated": f"{DID.replace('did:key:', '')[:4]}…{DID[-4:]}",
        "fingerprint": DID_FP,
        "shard": DID_SHARD,
        "mailbox": MAILBOX_NAME,
        "technocore_host": TECHNOCORE_HOST,
        "state_namespace": STATE_NS,
        "reports_namespace": REPORTS_NS,
        "proofs_namespace": PROOFS_NS,
        "cursors": state_mgr.state.get("cursors", {}),
        "total_messages_processed": state_mgr.state.get("total_messages_processed", 0),
        "total_tasks_completed": state_mgr.state.get("total_tasks_completed", 0),
        "total_rooms_discovered": state_mgr.state.get("total_rooms_discovered", 0),
        "budget_reads_left": client.reads_budget_left,
        "budget_writes_left": client.writes_budget_left,
    }


@app.get("/api/graph")
async def get_graph() -> Dict[str, Any]:
    """Return full graph topology (nodes and edges)."""
    return await observer.get_graph_data()


@app.get("/api/metrics")
async def get_metrics() -> Dict[str, Any]:
    """Return real-time velocity, signature ratio, and active counts."""
    return await observer.get_metrics()


@app.get("/api/feed")
async def get_feed() -> Dict[str, Any]:
    """Return live activity and message feed."""
    return {
        "feed": list(observer.activity_feed),
        "room_creations": list(observer.room_creations),
    }


@app.get("/api/proofs")
async def get_proofs() -> Dict[str, Any]:
    """Return completed tasks and their verifiable proof metadata."""
    return {
        "proofs": list(task_engine.completed_tasks.values()),
        "proofs_namespace": PROOFS_NS,
    }


@app.post("/api/send-task")
async def send_task(payload: TaskRequestPayload) -> Dict[str, Any]:
    """Send a signed task to our agent mailbox (for test/dispatch)."""
    try:
        # Construct task message
        msg_dict = {
            "action": payload.action,
            "target": payload.target,
            "reply_to": payload.reply_to,
        }
        import json
        msg_text = json.dumps(msg_dict)
        # Send signed to our mailbox
        did, resp = await client.say_signed(MAILBOX_NAME, msg_text)
        return {
            "status": "dispatched",
            "mailbox": MAILBOX_NAME,
            "sender_did": did,
            "payload": msg_dict,
            "response": resp,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/publish-report")
async def trigger_report() -> Dict[str, Any]:
    """Manually trigger field guide generation and publication to Technocore KV."""
    report = await observer.generate_and_publish_report()
    return {"status": "published", "report": report}


# Serve static web frontend
if (WEB_DIR / "index.html").exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(str(WEB_DIR / "index.html"))


def start_server():
    uvicorn.run("server:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    start_server()
