"""
WebSocket bridge: browser mic → Gemini Live session.
Runs as a local server on ws://localhost:8765
"""

import asyncio
import base64
import json
import threading
import websockets

_bridge_started = False
_bridge_lock = threading.Lock()


async def _handle_client(websocket, session_ref: dict):
    """Handle a single browser WebSocket connection."""
    print(f"[Bridge] Browser connected", flush=True)
    voice_session = session_ref.get("session")
    if voice_session:
        voice_session._ws = websocket

    try:
        async for message in websocket:
            if not voice_session:
                voice_session = session_ref.get("session")
                if voice_session:
                    voice_session._ws = websocket

            if voice_session and not voice_session._stop.is_set():
                try:
                    msg = json.loads(message)
                    if msg.get("type") == "audio":
                        pcm_data = base64.b64decode(msg["data"])
                        await voice_session._audio_queue.put(pcm_data)
                except Exception as e:
                    print(f"[Bridge] Error processing message: {e}", flush=True)
    except websockets.exceptions.ConnectionClosed:
        print(f"[Bridge] Browser disconnected", flush=True)
    finally:
        if voice_session:
            voice_session._ws = None


def start_bridge(session_ref: dict, port: int = 8765):
    """Start WebSocket bridge in a background thread. Call once at app startup."""
    global _bridge_started
    with _bridge_lock:
        if _bridge_started:
            return
        _bridge_started = True

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def serve():
            async with websockets.serve(
                lambda ws: _handle_client(ws, session_ref),
                "0.0.0.0", port
            ):
                print(f"[Bridge] WebSocket server started on ws://0.0.0.0:{port}", flush=True)
                await asyncio.Future()  # run forever

        loop.run_until_complete(serve())

    t = threading.Thread(target=_run, daemon=True, name="WsBridge")
    t.start()
    print(f"[Bridge] Bridge thread started", flush=True)
