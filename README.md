# GridWar — Real-Time Shared Grid

> A real-time territory battle. Click cells to claim them, steal from others, climb the leaderboard.

---

## Architecture

```
Browser A ──┐
Browser B ──┤── WebSocket ──► FastAPI Backend ◄──► Supabase (Postgres)
Browser C ──┘       │
                    └── Broadcast to ALL connected clients instantly
```

---

## Tech Stack

| Layer     | Tech                  | Why                                                              |
|-----------|-----------------------|------------------------------------------------------------------|
| Frontend  | Vanilla HTML/JS/Canvas | Zero build step. Canvas renders 1000 cells without any lag.     |
| Backend   | FastAPI (Python)       | Async-native, built-in WebSocket support, minimal boilerplate.  |
| Real-time | WebSockets             | True bidirectional push — every capture instantly fans out.     |
| Database  | Supabase (Postgres)    | Grid persists across server restarts. Leaderboard is durable.   |
| State     | In-memory + Supabase   | Memory = fast reads; Supabase = persistence via async upserts.  |

---

## Project Structure

```
gridwar/
├── backend/
│   ├── main.py              # FastAPI WS server + game logic
│   ├── requirements.txt     # Python dependencies
│   └── .env.example         # Env var template
├── frontend/
│   └── index.html           # Entire frontend (no build needed)
├── supabase_schema.sql      # Run this in Supabase SQL Editor
└── README.md
```

---

## Setup — Step by Step

### 1. Supabase Setup

1. Go to [supabase.com](https://supabase.com) → create a new project
2. Open **SQL Editor** → paste contents of `supabase_schema.sql` → Run
3. Go to **Project Settings → API**:
   - Copy **Project URL** → `SUPABASE_URL`
   - Copy **service_role** secret key → `SUPABASE_SERVICE_KEY`

### 2. Backend

```bash
cd backend

# Copy env file and fill in your keys
cp .env.example .env
# Edit .env and paste your Supabase URL + service_role key

pip install -r requirements.txt
python main.py
# → Server starts on http://localhost:8000
```

### 3. Frontend

Open `frontend/index.html` directly in a browser, or:

```bash
cd frontend
python -m http.server 5500
# → http://localhost:5500
```

> **Deploying** Change `WS_URL` at the top of the `<script>` in `index.html` to your deployed backend URL, e.g. `wss://gridwar.yourserver.com/ws`

---

## How Real-Time Works

```
1. Client connects via WebSocket
2. Server sends INIT → full grid snapshot (sparse, claimed cells only)
3. Client clicks a cell → sends { type: "capture", cellId: N }
4. Server validates (cooldown, bounds, ownership)
5. Server updates in-memory grid
6. Server fires async Supabase upsert (non-blocking)
7. Server broadcasts to ALL connected clients immediately
8. All clients receive { type: "capture", cellId, cell, leaderboard }
9. All clients redraw that one cell on their canvas
```

---

## Supabase Tables

### `grid_cells`
| Column       | Type    | Description                     

| cell_id      | INTEGER | Primary key (0–999)             
| owner_id     | TEXT    | Session user ID                 
| owner_name   | TEXT    | Display name                    
| color        | TEXT    | Hex color                       
| captured_at  | FLOAT   | Unix timestamp of last capture  

### `user_scores`
| Column     | Type        | Description              |
|------------|-------------|--------------------------|
| user_id    | TEXT        | Primary key              |
| name       | TEXT        | Display name             |
| color      | TEXT        | Hex color                |
| score      | INTEGER     | Current cell count       |
| updated_at | TIMESTAMPTZ | Auto-updated on change   |

---

## Features

- 40×25 = 1000 cell canvas grid
- WebSocket real-time broadcast to all clients
- Capture + steal cells
- Supabase persistence (grid survives server restart)
- Live leaderboard (top 10)
- Per-user colors, cooldown (1.5s, server-enforced)
- Zoom/pan (scroll + alt+drag)
- Ripple animations on capture
- Hover tooltip (owner + time)
- Activity feed (real-time)
- Online presence count
- Optimistic UI (feels instant)

---

## Scaling Notes

| Problem             | Solution                                          

| Multi-server nodes  | Redis Pub/Sub for cross-node broadcast            
| High write volume   | Batch Supabase upserts or use Supabase Realtime   
| Large grids         | Already using sparse grid format (only claimed)   
| Auth                | JWT in WebSocket handshake                        
