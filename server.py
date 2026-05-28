"""
Vidya Voice POC — FastAPI server (single port, Render-compatible)
Serves index.html, handles WebSocket bridge, and manages VidyaVoiceSession.
Run: uvicorn server:app --host 0.0.0.0 --port $PORT
"""

import os
import asyncio
import threading
import base64
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from realtime_handler import VidyaVoiceSession

app = FastAPI()

# Shared session reference
session_ref: dict = {}

@app.get("/")
async def index():
    return FileResponse("index.html")

@app.websocket("/ws")
async def websocket_bridge(websocket: WebSocket):
    """Single WebSocket endpoint — bridges browser mic ↔ Gemini Live."""
    await websocket.accept()
    print("[WS] Browser connected", flush=True)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        await websocket.close()
        return

    transcript_log = []

    def on_user(t):
        transcript_log.append({"role": "user", "text": t})
        session_ref["transcript"] = transcript_log[:]

    def on_asst(t):
        transcript_log.append({"role": "assistant", "text": t})
        session_ref["transcript"] = transcript_log[:]

    def on_status(s):
        session_ref["status"] = s
        print(f"[Server] Status: {s}", flush=True)

    def on_info(i):
        session_ref["info"] = i

    session = VidyaVoiceSession(
        api_key=api_key,
        on_user_transcript=on_user,
        on_assistant_transcript=on_asst,
        on_status_change=on_status,
        on_info_update=on_info,
    )

    # Give session a reference to this websocket for audio playback
    session._ws = websocket
    session_ref["session"] = session
    session_ref["status"] = "connecting"
    session_ref["transcript"] = []
    session_ref["info"] = {}

    # Run Gemini session in background thread
    loop = asyncio.get_event_loop()

    def run_session():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        new_loop.run_until_complete(session.run())
        new_loop.close()

    t = threading.Thread(target=run_session, daemon=True, name="VidyaSession")
    t.start()

    # Forward browser audio → session._audio_queue
    try:
        while True:
            message = await websocket.receive_text()
            msg = json.loads(message)
            if msg.get("type") == "audio":
                pcm = base64.b64decode(msg["data"])
                await session._audio_queue.put(pcm)
            elif msg.get("type") == "stop":
                session.stop()
                break
    except WebSocketDisconnect:
        print("[WS] Browser disconnected", flush=True)
    except Exception as e:
        print(f"[WS] Error: {e}", flush=True)
    finally:
        session.stop()
        session._ws = None
        session_ref["status"] = "disconnected"

@app.get("/state")
async def get_state():
    return {
        "status": session_ref.get("status", "disconnected"),
        "transcript": session_ref.get("transcript", []),
        "info": session_ref.get("info", {}),
    }
