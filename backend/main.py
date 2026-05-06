"""
GridWar Backend
FastAPI + WebSockets + Supabase (persistent grid state)
"""

import asyncio
import json
import time
import random
import string
import os
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import uvicorn
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="GridWar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

# ── Config ────────────────────────────────────────────────────────────────────
GRID_COLS        = 40
GRID_ROWS        = 25
TOTAL_CELLS      = GRID_COLS * GRID_ROWS
COOLDOWN_SECONDS = 1.5

COLOR_PALETTE = [
    "#FF6B6B","#FF9F43","#FECA57","#48DBFB","#1DD1A1",
    "#FF9FF3","#54A0FF","#5F27CD","#00D2D3","#FF6348",
    "#7BED9F","#70A1FF","#ECCC68","#A29BFE","#FD79A8",
    "#6C5CE7","#00CEC9","#E17055","#74B9FF","#55EFC4",
]

grid:  Dict[int, Optional[dict]] = {i: None for i in range(TOTAL_CELLS)}
users: Dict[str, dict] = {}


# ── Supabase Helpers ──────────────────────────────────────────────────────────

async def load_grid_from_db():
    if not supabase:
        print("[DB] Supabase not configured — running in-memory only")
        return
    try:
        res = supabase.table("grid_cells").select("*").execute()
        for row in res.data:
            cid = row["cell_id"]
            if 0 <= cid < TOTAL_CELLS:
                grid[cid] = {
                    "owner": row["owner_id"],
                    "color": row["color"],
                    "name":  row["owner_name"],
                    "ts":    row["captured_at"],
                }
        print(f"[DB] Loaded {len(res.data)} cells from Supabase")
    except Exception as e:
        print(f"[DB] Failed to load grid: {e}")


async def persist_capture(cell_id: int, user_id: str, color: str, name: str, score: int):
    if not supabase:
        return
    try:
        supabase.table("grid_cells").upsert({
            "cell_id":     cell_id,
            "owner_id":    user_id,
            "owner_name":  name,
            "color":       color,
            "captured_at": time.time(),
        }, on_conflict="cell_id").execute()

        supabase.table("user_scores").upsert({
            "user_id": user_id,
            "name":    name,
            "color":   color,
            "score":   score,
        }, on_conflict="user_id").execute()
    except Exception as e:
        print(f"[DB] Persist error: {e}")


# ── Connection Manager ────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.connections: Dict[WebSocket, str] = {}

    async def connect(self, ws: WebSocket, user_id: str):
        await ws.accept()
        self.connections[ws] = user_id

    def disconnect(self, ws: WebSocket):
        self.connections.pop(ws, None)

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        dead = []
        for ws in list(self.connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.pop(ws, None)

    async def send_to(self, ws: WebSocket, message: dict):
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass

    @property
    def online_count(self):
        return len(self.connections)


manager = ConnectionManager()


def generate_user_id():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def get_leaderboard(top_n=10):
    sorted_users = sorted(users.values(), key=lambda u: u["score"], reverse=True)
    return [{"name": u["name"], "color": u["color"], "score": u["score"]} for u in sorted_users[:top_n]]

def grid_snapshot():
    return {str(k): v for k, v in grid.items() if v is not None}


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await load_grid_from_db()
    print(f"[GridWar] Ready — {TOTAL_CELLS} cells | Supabase: {'ON' if supabase else 'OFF (in-memory)'}")


# ── HTTP ──────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "online": manager.online_count, "supabase": bool(supabase)}

@app.get("/state")
def full_state():
    return {
        "grid": grid_snapshot(),
        "leaderboard": get_leaderboard(),
        "online": manager.online_count,
        "config": {"cols": GRID_COLS, "rows": GRID_ROWS, "cooldown": COOLDOWN_SECONDS}
    }


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    user_id = generate_user_id()
    await manager.connect(ws, user_id)
    try:
        await manager.send_to(ws, {
            "type": "init", "userId": user_id,
            "grid": grid_snapshot(), "leaderboard": get_leaderboard(),
            "online": manager.online_count,
            "config": {"cols": GRID_COLS, "rows": GRID_ROWS, "cooldown": COOLDOWN_SECONDS}
        })
        await manager.broadcast({"type": "presence", "online": manager.online_count})

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await handle_message(ws, user_id, msg)

    except WebSocketDisconnect:
        manager.disconnect(ws)
        await manager.broadcast({"type": "presence", "online": manager.online_count})


async def handle_message(ws: WebSocket, user_id: str, msg: dict):
    t = msg.get("type")

    if t == "register":
        name  = (msg.get("name") or "Player").strip()[:20] or "Player"
        used  = {u["color"] for u in users.values()}
        avail = [c for c in COLOR_PALETTE if c not in used]
        color = random.choice(avail) if avail else random.choice(COLOR_PALETTE)
        users[user_id] = {"name": name, "color": color, "score": 0, "last_capture": 0.0}
        await manager.send_to(ws, {"type": "registered", "userId": user_id, "name": name, "color": color})

    elif t == "capture":
        if user_id not in users:
            await manager.send_to(ws, {"type": "error", "msg": "Register first"})
            return
        cell_id = msg.get("cellId")
        if cell_id is None or not (0 <= cell_id < TOTAL_CELLS):
            await manager.send_to(ws, {"type": "error", "msg": "Invalid cell"})
            return

        user = users[user_id]
        now  = time.time()
        if now - user["last_capture"] < COOLDOWN_SECONDS:
            await manager.send_to(ws, {"type": "cooldown", "remaining": round(COOLDOWN_SECONDS - (now - user["last_capture"]), 2)})
            return
        if grid[cell_id] and grid[cell_id]["owner"] == user_id:
            return

        existing = grid[cell_id]
        if existing and existing["owner"] in users:
            users[existing["owner"]]["score"] = max(0, users[existing["owner"]]["score"] - 1)

        grid[cell_id] = {"owner": user_id, "color": user["color"], "name": user["name"], "ts": now}
        user["score"] += 1
        user["last_capture"] = now

        asyncio.create_task(persist_capture(cell_id, user_id, user["color"], user["name"], user["score"]))

        await manager.broadcast({
            "type": "capture", "cellId": cell_id,
            "cell": grid[cell_id], "leaderboard": get_leaderboard(),
            "online": manager.online_count,
        })


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
