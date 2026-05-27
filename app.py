"""
Vidya Voice POC — Streamlit Voice App (Gemini Live, mic required)

Run: streamlit run app.py
Requires: pip install -r requirements.txt + working microphone
"""

import asyncio
import threading
import streamlit as st
from datetime import datetime
from realtime_handler import VidyaVoiceSession
import logging
import sys
import queue
import os
from dotenv import load_dotenv
from ws_audio_bridge import start_bridge


# Load environment variables from .env file
load_dotenv()

# Suppress Streamlit's async warnings
logging.getLogger("streamlit").setLevel(logging.ERROR)

# Import learner intelligence system
try:
    parent_dir = os.path.dirname(__file__)
    sys.path.insert(0, parent_dir)
    sys.path.insert(0, os.path.join(parent_dir, 'models'))
    from services.learner_state import LearnerStateManager
    from services.signal_extractor import SignalExtractionOrchestrator
    from services.prompt_injector import PromptContextInjector
    from services.learner_state_persistence import LearnerStatePersistence
    LEARNER_SYSTEM_AVAILABLE = True
except Exception as e:
    LEARNER_SYSTEM_AVAILABLE = False
    print(f"[WARNING] Learner intelligence system not available: {type(e).__name__}: {e}", flush=True)
    import traceback
    traceback.print_exc()


def init_state():
    defaults = {
        "api_key":      os.getenv("GEMINI_API_KEY"),
        "session":      None,
        "chat_log":     [],
        "extracted_info": {
            "name": None, "background": None, "career_context": None,
            "skills": None, "goal": None, "time_commitment": None,
            "preferred_language": None,
        },
        "turn_count":   0,
        "aha_reached":  False,
        "is_running":   False,
        "status":       "disconnected",
        "pending_user":      [],
        "pending_assistant": [],
        # NEW: Learner intelligence system
        "learner_state_manager": None,
        "signal_orchestrator": None,
        "learner_session_id": None,
        "learner_state": None,
        "learner_signals": {},
        "learner_context": "",
        "persistence": None,
        "session_start_time": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    
    # Initialize learner system if available
    if LEARNER_SYSTEM_AVAILABLE and st.session_state.learner_state_manager is None:
        try:
            st.session_state.learner_state_manager = LearnerStateManager()
            st.session_state.persistence = LearnerStatePersistence()
            # Use the hardcoded API key from session state for learner system
            api_key = st.session_state.get("api_key", os.getenv("GEMINI_API_KEY", None))
            st.session_state.signal_orchestrator = SignalExtractionOrchestrator(
                llm_api_key=api_key
            )
            # Create session-specific learner state
            session_id = f"streamlit_{datetime.now().timestamp()}"
            st.session_state.learner_session_id = session_id
            st.session_state.learner_state = st.session_state.learner_state_manager.initialize_session(session_id)
            st.session_state.session_start_time = datetime.now()
            print(f"[LEARNER SYSTEM] Initialized with session_id={session_id}", flush=True)
        except Exception as e:
            print(f"[LEARNER SYSTEM] Initialization failed: {e}", flush=True)
            import traceback
            traceback.print_exc()
    if "bridge_session_ref" not in st.session_state:
    st.session_state.bridge_session_ref = {"session": None}
    start_bridge(st.session_state.bridge_session_ref, port=8765)
            


def detect_phase(info):
    filled = sum(1 for v in info.values() if v is not None)
    phases = [
        (1,"Rapport & Language","#A78BFA"),
        (2,"Identity & Context","#60A5FA"),
        (3,"Urgency & Pain","#F97316"),
        (4,"Skills & Resources","#34D399"),
        (5,"Goal & Belief","#FBBF24"),
        (6,"Commitment","#F472B6"),
        (7,"Future You Reveal","#22C55E"),
    ]
    return phases[min(filled, 6)]


def save_learner_state_to_disk():
    """Save the learner state to disk when conversation ends"""
    if not LEARNER_SYSTEM_AVAILABLE:
        print("[PERSISTENCE] Learner system not available, skipping save", flush=True)
        return
    
    try:
        learner_state = st.session_state.learner_state
        persistence = st.session_state.persistence
        
        if not learner_state or not persistence:
            print("[PERSISTENCE] Learner state or persistence not initialized", flush=True)
            return
        
        # Calculate conversation duration
        duration_seconds = None
        if st.session_state.session_start_time:
            duration = datetime.now() - st.session_state.session_start_time
            duration_seconds = int(duration.total_seconds())
        
        # Prepare metadata - use learner_state.turn_count (actual turns, not fragments)
        metadata = {
            "duration_seconds": duration_seconds,
            "turns": learner_state.turn_count,  # Use learner_state tracking, not st.session_state (counts fragments)
            "aha_reached": st.session_state.aha_reached,
            "extracted_info": st.session_state.extracted_info,
        }
        
        # Save to disk
        saved_path = persistence.save_session_state(learner_state, metadata)
        print(f"[PERSISTENCE] ✓ Learner state saved to {saved_path}", flush=True)
        
        # Show success message
        st.success(f"✓ Conversation saved! View at: `{saved_path}`")
        
        return saved_path
        
    except Exception as e:
        print(f"[PERSISTENCE] Error saving learner state: {e}", flush=True)
        import traceback
        traceback.print_exc()
        st.warning(f"⚠️ Could not save learner state: {str(e)}")



def launch_voice_session(api_key: str):
    """Start VidyaVoiceSession in a background thread with queue-based communication."""
    print(f"[DEBUG] launch_voice_session called with api_key={api_key[:20]}...", flush=True)

    # Create a queue for thread-safe communication
    event_queue = queue.Queue()
    st.session_state.event_queue = event_queue

    def on_user(text):
        event_queue.put(("user", text))

    def on_asst(text):
        event_queue.put(("assistant", text))
        if any(p in text.lower() for p in ["12 week","12 hafte","ready?","ready ho?"]):
            st.session_state.aha_reached = True

    def on_status(s):
        print(f"[STATUS] {s}", flush=True)
        event_queue.put(("status", s))

    def on_info(i):
        event_queue.put(("info", i))
    
    def on_learner_signals(signals_dict):
        """Callback when new signals are extracted"""
        event_queue.put(("learner_signals", signals_dict))
    
    def on_learner_context(context_str):
        """Callback when learner context is built"""
        event_queue.put(("learner_context", context_str))

    session = VidyaVoiceSession(
        api_key=api_key,
        on_user_transcript=on_user,
        on_assistant_transcript=on_asst,
        on_status_change=on_status,
        on_info_update=on_info,
        # NEW: Pass learner system components
        learner_state_manager=st.session_state.learner_state_manager if LEARNER_SYSTEM_AVAILABLE else None,
        signal_orchestrator=st.session_state.signal_orchestrator if LEARNER_SYSTEM_AVAILABLE else None,
        learner_session_id=st.session_state.learner_session_id if LEARNER_SYSTEM_AVAILABLE else None,
        on_learner_signals=on_learner_signals,
        on_learner_context=on_learner_context,
    )
    st.session_state.session = session
    st.session_state.bridge_session_ref["session"] = session
    print(f"[DEBUG] VidyaVoiceSession created", flush=True)

    def _run():
        print(f"[DEBUG] Background thread started", flush=True)
        # Create a new event loop for this thread to avoid ScriptRunContext warnings
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            print(f"[DEBUG] Running session.run()...", flush=True)
            loop.run_until_complete(session.run())
            print(f"[DEBUG] session.run() completed", flush=True)
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
            event_queue.put(("status", f"error: {str(e)[:100]}"))
        finally:
            loop.close()
            print(f"[DEBUG] Event loop closed", flush=True)

    t = threading.Thread(target=_run, daemon=True, name="VidyaVoiceThread")
    t.start()
    print(f"[DEBUG] Background thread started with name={t.name}", flush=True)


def main():
    init_state()

    st.set_page_config(
        page_title="Vidya — Gemini Live Voice",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
      .stApp { background:#0B0F19; }
      #MainMenu, footer, header { visibility:hidden; }
      [data-testid="stSidebar"] { background:#0F172A; border-right:1px solid #1E293B; }
      .stButton>button { border-radius:12px !important; font-weight:600 !important; }
      .stTextInput>div>div>input {
          background:#1E293B !important; color:#E2E8F0 !important;
          border:1px solid #334155 !important; border-radius:12px !important; }
      @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
      .pulsing { animation:pulse 1.2s infinite; }
    </style>
    """, unsafe_allow_html=True)

    # Process queue events from background thread
    if st.session_state.is_running and hasattr(st.session_state, 'event_queue'):
        try:
            while True:
                event_type, event_data = st.session_state.event_queue.get_nowait()
                if event_type == "user":
                    st.session_state.pending_user.append(event_data)
                    st.session_state.turn_count += 1  # Only increment on user turn, not assistant response
                elif event_type == "assistant":
                    st.session_state.pending_assistant.append(event_data)
                    # Do NOT increment turn_count here - already counted on user message
                elif event_type == "status":
                    st.session_state.status = event_data
                elif event_type == "info":
                    st.session_state.extracted_info = event_data
                elif event_type == "learner_signals":
                    st.session_state.learner_signals = event_data
                elif event_type == "learner_context":
                    st.session_state.learner_context = event_data
        except queue.Empty:
            pass

    # Flush pending transcript updates into chat_log
    for t in st.session_state.pending_user:
        # Check if last entry is also from user, if so append to it
        if (st.session_state.chat_log and 
            st.session_state.chat_log[-1]["role"] == "user"):
            st.session_state.chat_log[-1]["text"] += " " + t
        else:
            st.session_state.chat_log.append(
                {"role":"user","text":t,"time":datetime.now().strftime("%H:%M")}
            )
    st.session_state.pending_user.clear()

    for t in st.session_state.pending_assistant:
        # Check if last entry is also from assistant, if so append to it
        if (st.session_state.chat_log and 
            st.session_state.chat_log[-1]["role"] == "assistant"):
            st.session_state.chat_log[-1]["text"] += " " + t
        else:
            st.session_state.chat_log.append(
                {"role":"assistant","text":t,"time":datetime.now().strftime("%H:%M")}
            )
    st.session_state.pending_assistant.clear()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:20px 0 10px;">
          <div style="font-size:42px;font-weight:800;
               background:linear-gradient(135deg,#A78BFA,#6D28D9);
               -webkit-background-clip:text;-webkit-text-fill-color:transparent;">VIDYA</div>
          <div style="font-size:12px;color:#64748B;letter-spacing:2px;
               text-transform:uppercase;">Gemini Live · Voice</div>
        </div>""", unsafe_allow_html=True)
        st.markdown("---")

        # Display masked API key status
        has_api_key = bool(st.session_state.api_key)
        if has_api_key:
            masked_key = st.session_state.api_key[:8] + "*" * (len(st.session_state.api_key) - 8) if st.session_state.api_key else ""
            st.info(f"✅ API Key loaded: {masked_key}")
            override_key = st.text_input("Override API Key (optional)", type="password",
                                        value="", placeholder="Leave empty to use .env key")
            if override_key:
                st.session_state.api_key = override_key
        else:
            st.warning("⚠️ No API key found. Please set GEMINI_API_KEY in .env")
            api_key_input = st.text_input("Google AI API Key", type="password",
                                        placeholder="AIza...")
            if api_key_input:
                st.session_state.api_key = api_key_input

        st.markdown("---")

        # Status
        status = st.session_state.status
        dot_color = {"ready":"#22C55E","listening":"#22C55E",
                     "connecting":"#F59E0B","disconnected":"#EF4444"}.get(
                    status.split(":")[0], "#EF4444")
        pulse = "pulsing" if status in ("connecting","listening") else ""
        st.markdown(f"""
        <div style="display:flex;align-items:center;margin-bottom:12px;">
          <div class="{pulse}" style="width:10px;height:10px;border-radius:50%;
               background:{dot_color};margin-right:8px;box-shadow:0 0 6px {dot_color};"></div>
          <span style="color:#94A3B8;font-size:13px;font-weight:600;
                       text-transform:uppercase;letter-spacing:1px;">{status}</span>
        </div>""", unsafe_allow_html=True)

        # Debug info
        if st.session_state.is_running:
            st.caption(f"🔧 Debug: is_running={st.session_state.is_running}, session_obj={'exists' if st.session_state.session else 'None'}")

        st.markdown("---")

        # Extracted info
        st.markdown("""<div style="font-size:13px;font-weight:700;color:#A78BFA;
                    letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;">
                    📋 Extracted Info</div>""", unsafe_allow_html=True)

        info = st.session_state.extracted_info
        for label, key in [
            ("👤 Name","name"), ("🏫 Background","background"),
            ("💼 Trigger","career_context"), ("⚡ Skills","skills"),
            ("🎯 Goal","goal"), ("⏰ Time/Week","time_commitment"),
            ("🌐 Language","preferred_language"),
        ]:
            value = info[key]
            bg     = "#1E293B" if value else "#0F172A"
            border = "solid #334155" if value else "dashed #1E293B"
            color  = "#E2E8F0" if value else "#475569"
            italic = "" if value else "font-style:italic;"
            st.markdown(f"""
            <div style="background:{bg};border:1px {border};border-radius:8px;
                        padding:8px 12px;margin-bottom:6px;opacity:{'1' if value else '0.5'};">
              <div style="font-size:10px;color:#64748B;text-transform:uppercase;">{label}</div>
              <div style="font-size:13px;color:{color};margin-top:2px;{italic}">
                  {value if value else 'Waiting...'}</div>
            </div>""", unsafe_allow_html=True)

        filled = sum(1 for v in info.values() if v)
        pct    = int(filled / 7 * 100)
        st.markdown(f"""
        <div style="margin-top:12px;">
          <div style="font-size:11px;color:#64748B;margin-bottom:4px;">
              Info gathered: {filled}/7 ({pct}%)</div>
          <div style="background:#1E293B;border-radius:8px;height:8px;overflow:hidden;">
            <div style="background:linear-gradient(90deg,#6D28D9,#A78BFA);
                        width:{pct}%;height:100%;border-radius:8px;"></div>
          </div>
        </div>""", unsafe_allow_html=True)
        
        # NEW: Display learner signals if available
        if LEARNER_SYSTEM_AVAILABLE and st.session_state.learner_signals:
            st.markdown("---")
            st.markdown("""<div style="font-size:13px;font-weight:700;color:#60A5FA;
                        letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;">
                        🧠 Learner Signals</div>""", unsafe_allow_html=True)
            
            signals = st.session_state.learner_signals
            for signal_name, signal_value in signals.items():
                if signal_value and signal_value != "unknown":
                    st.markdown(f"""
                    <div style="background:#0F172A;border:1px solid #334155;border-radius:6px;
                                padding:6px 10px;margin-bottom:4px;font-size:12px;">
                      <span style="color:#64748B;">{signal_name}:</span>
                      <span style="color:#60A5FA;font-weight:600;"> {signal_value}</span>
                    </div>""", unsafe_allow_html=True)

    # ── Main ─────────────────────────────────────────────────────────────────
    col_chat, col_panel = st.columns([3, 1])

    with col_chat:
        st.markdown("""
        <div style="margin-bottom:20px;">
          <h1 style="font-size:26px;font-weight:800;color:#E2E8F0;margin:0;">
              🎙️ Vidya — Voice Mode (Gemini Live)
          </h1>
          <p style="color:#64748B;font-size:14px;margin-top:6px;">
              Real-time voice conversation. Speak naturally — Hindi, English, or mix.
          </p>
        </div>""", unsafe_allow_html=True)

        chat_box = st.container(height=420)
        # Browser mic capture + audio playback component
st.components.v1.html("""
<script>
const WS_URL = "ws://" + window.location.hostname + ":8765";
let ws, audioCtx, processor, source, stream;
let playbackQueue = [];
let isPlaying = false;

function connectWS() {
    ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => console.log("[Audio] WS connected");
    ws.onmessage = async (evt) => {
        const msg = JSON.parse(evt.data);
        if (msg.type === "audio") {
            const raw = atob(msg.data);
            const buf = new Uint8Array(raw.length);
            for (let i = 0; i < raw.length; i++) buf[i] = raw.charCodeAt(i);
            playbackQueue.push(buf.buffer);
            if (!isPlaying) drainQueue();
        }
    };
    ws.onclose = () => { console.log("[Audio] WS closed, retrying..."); setTimeout(connectWS, 2000); };
    ws.onerror = (e) => console.error("[Audio] WS error", e);
}

async function drainQueue() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    isPlaying = true;
    while (playbackQueue.length > 0) {
        const pcmBuffer = playbackQueue.shift();
        const samples = new Int16Array(pcmBuffer);
        const float32 = new Float32Array(samples.length);
        for (let i = 0; i < samples.length; i++) float32[i] = samples[i] / 32768.0;
        const audioBuffer = audioCtx.createBuffer(1, float32.length, 24000);
        audioBuffer.copyToChannel(float32, 0);
        const src = audioCtx.createBufferSource();
        src.buffer = audioBuffer;
        src.connect(audioCtx.destination);
        await new Promise(resolve => { src.onended = resolve; src.start(); });
    }
    isPlaying = false;
}

async function startMic() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 }, video: false });
    source = audioCtx.createMediaStreamSource(stream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (e) => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        const float32 = e.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
        const b64 = btoa(String.fromCharCode(...new Uint8Array(int16.buffer)));
        ws.send(JSON.stringify({ type: "audio", data: b64 }));
    };
    source.connect(processor);
    processor.connect(audioCtx.destination);
    document.getElementById("mic-btn").textContent = "🔴 Mic Active";
    document.getElementById("mic-btn").style.background = "#ef4444";
}

function stopMic() {
    if (processor) { processor.disconnect(); processor = null; }
    if (source) { source.disconnect(); source = null; }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    document.getElementById("mic-btn").textContent = "🎤 Start Mic";
    document.getElementById("mic-btn").style.background = "#6d28d9";
}

connectWS();

window.micActive = false;
function toggleMic() {
    window.micActive ? stopMic() : startMic();
    window.micActive = !window.micActive;
}
</script>
<div style="text-align:center;padding:8px 0;">
  <button id="mic-btn" onclick="toggleMic()"
    style="background:#6d28d9;color:white;border:none;border-radius:12px;
           padding:10px 28px;font-size:15px;font-weight:700;cursor:pointer;
           box-shadow:0 0 16px #6d28d944;">
    🎤 Start Mic
  </button>
  <div style="font-size:11px;color:#64748b;margin-top:6px;">
    Click to allow mic access — audio goes directly to Gemini
  </div>
</div>
""", height=90)
with chat_box:
            if not st.session_state.chat_log:
                st.markdown("""
                <div style="text-align:center;padding:80px 40px;color:#475569;">
                  <div style="font-size:56px;margin-bottom:12px;">🎤</div>
                  <div style="font-size:16px;font-weight:600;color:#64748B;">
                      Connect and start speaking</div>
                  <div style="font-size:13px;margin-top:8px;">
                      Vidya will greet you and adapt to your language</div>
                </div>""", unsafe_allow_html=True)
            else:
                for entry in st.session_state.chat_log:
                    with st.chat_message(entry["role"],
                                         avatar="🎓" if entry["role"]=="assistant" else "🧑"):
                        st.markdown(entry["text"])

        # Controls
        c1, c2, c3 = st.columns(3)
        with c1:
            if not st.session_state.is_running:
                if st.button("🔌 Connect & Listen", use_container_width=True,
                             disabled=not st.session_state.api_key, type="primary"):
                    st.session_state.is_running = True
                    launch_voice_session(st.session_state.api_key)
                    st.rerun()
            else:
                if st.button("⏹️ Stop Session", use_container_width=True):
                    if st.session_state.session:
                        st.session_state.session.stop()
                    # SAVE: Persist learner state before stopping
                    save_learner_state_to_disk()
                    st.session_state.is_running = False
                    st.rerun()

        with c2:
            if st.button("🔄 New Conversation", use_container_width=True):
                if st.session_state.session:
                    st.session_state.session.stop()
                # SAVE: Persist learner state before starting new conversation
                save_learner_state_to_disk()
                keys = ["session","chat_log","turn_count","aha_reached","is_running","status","event_queue"]
                for k in keys:
                    if k in st.session_state:
                        del st.session_state[k]
                st.session_state.extracted_info = {k: None for k in st.session_state.extracted_info}
                st.rerun()

        with c3:
            if st.session_state.is_running:
                st.markdown("""
                <div style="background:#1E293B;border:1px solid #22C55E;border-radius:12px;
                            padding:8px;text-align:center;">
                  <span style="color:#22C55E;font-size:13px;font-weight:600;">
                      🔴 LIVE — Speak now</span>
                </div>""", unsafe_allow_html=True)

        # Auto-refresh while running
        if st.session_state.is_running:
            st.markdown("""
            <div style="font-size:11px;color:#475569;margin-top:8px;text-align:center;">
                Transcript appears after each voice turn</div>""", unsafe_allow_html=True)
            # Poll for status updates every 500ms for responsive UI
            import time
            time.sleep(0.5)
            st.rerun()

    with col_panel:
        st.markdown(f"""
        <div style="background:#1E293B;border:1px solid #334155;border-radius:14px;
                    padding:16px;text-align:center;margin-bottom:12px;">
          <div style="font-size:10px;color:#64748B;text-transform:uppercase;letter-spacing:1px;">Turn</div>
          <div style="font-size:40px;font-weight:800;color:#A78BFA;margin:4px 0;">
              {st.session_state.turn_count}</div>
        </div>""", unsafe_allow_html=True)

        p_num, p_name, p_color = detect_phase(st.session_state.extracted_info)
        st.markdown(f"""
        <div style="background:#1E293B;border:1px solid {p_color}44;border-radius:14px;
                    padding:16px;text-align:center;margin-bottom:12px;">
          <div style="font-size:10px;color:#64748B;text-transform:uppercase;">Phase {p_num}</div>
          <div style="font-size:14px;font-weight:700;color:{p_color};margin:6px 0;">{p_name}</div>
        </div>""", unsafe_allow_html=True)

        all_phases = [("Rapport",1),("Context",2),("Pain",3),("Skills",4),
                      ("Belief",5),("Commit",6),("Reveal",7)]
        st.markdown("""<div style="background:#1E293B;border:1px solid #334155;
                    border-radius:14px;padding:16px;margin-bottom:12px;">""",
                   unsafe_allow_html=True)
        for name, num in all_phases:
            active = num == p_num; done = num < p_num
            c  = "#A78BFA" if active else ("#22C55E" if done else "#334155")
            ic = "●" if active else ("✓" if done else "○")
            tc = "#E2E8F0" if active else ("#94A3B8" if done else "#475569")
            st.markdown(f"""
            <div style="display:flex;align-items:center;margin-bottom:4px;">
              <span style="color:{c};font-size:13px;margin-right:8px;font-weight:bold;">{ic}</span>
              <span style="color:{tc};font-size:12px;font-weight:{'600' if active else '400'};">{name}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.aha_reached:
            st.markdown("""
            <div style="background:linear-gradient(135deg,#065F46,#047857);
                        border-radius:14px;padding:16px;text-align:center;">
              <div style="font-size:28px;">✨</div>
              <div style="font-size:14px;font-weight:700;color:#D1FAE5;">AHA REACHED</div>
            </div>""", unsafe_allow_html=True)

    # ── Saved Conversations Section ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div style="font-size:16px;font-weight:700;color:#A78BFA;
                letter-spacing:1px;text-transform:uppercase;margin:20px 0 10px;">
                💾 Saved Conversations</div>""", unsafe_allow_html=True)
    
    if LEARNER_SYSTEM_AVAILABLE and st.session_state.persistence:
        try:
            saved_sessions = st.session_state.persistence.list_saved_sessions()
            
            if not saved_sessions:
                st.info("📭 No conversations saved yet. Complete a conversation and click 'Stop Session' to save.")
            else:
                st.markdown(f"**{len(saved_sessions)} conversation(s) saved**")
                
                for session_info in saved_sessions[:5]:  # Show last 5
                    session_id = session_info["session_id"]
                    with st.expander(f"🎤 {session_id}", expanded=False):
                        try:
                            summary = st.session_state.persistence.get_session_summary(session_id)
                            if summary:
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Turns", summary.get("turn_count", 0))
                                with col2:
                                    st.metric("Messages", summary.get("messages_count", 0))
                                with col3:
                                    st.metric("Avg Confidence", f"{summary.get('signal_confidence_avg', 0):.2f}")
                                
                                st.markdown("**Key Signals Detected:**")
                                key_signals = summary.get("key_signals", {})
                                for signal_name, signal_value in key_signals.items():
                                    st.write(f"- **{signal_name}**: {signal_value}")
                                
                                if st.button(f"📊 View Full Report", key=f"report_{session_id}"):
                                    report = st.session_state.persistence.export_evaluation_report(session_id)
                                    st.markdown("```\n" + report + "\n```")
                        except Exception as e:
                            st.warning(f"Error loading summary: {str(e)}")
        except Exception as e:
            st.error(f"Error loading saved conversations: {str(e)}")
    else:
        st.info("📭 Learner system not available")


if __name__ == "__main__":
    main()
