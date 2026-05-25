"""
Vidya Voice POC — Streamlit App (Gemini backend, text mode)

Run: streamlit run app_browser.py
"""

import asyncio
import streamlit as st
from datetime import datetime
from realtime_handler import VidyaTextSession
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ─── Session state ────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "api_key":  os.getenv("GEMINI_API_KEY"),
        "session":  None,       # VidyaTextSession
        "chat_log": [],
        "extracted_info": {
            "name": None, "background": None, "career_context": None,
            "skills": None, "goal": None, "time_commitment": None,
            "preferred_language": None,
        },
        "turn_count":   0,
        "aha_reached":  False,
        "started":      False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run_async(coro):
    """Run an async coroutine from sync Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def detect_phase(info, turn):
    filled = sum(1 for v in info.values() if v is not None)
    phases = [
        (1, "Rapport & Language",  "#A78BFA"),
        (2, "Identity & Context",  "#60A5FA"),
        (3, "Urgency & Pain",      "#F97316"),
        (4, "Skills & Resources",  "#34D399"),
        (5, "Goal & Belief",       "#FBBF24"),
        (6, "Commitment",          "#F472B6"),
        (7, "Future You Reveal",   "#22C55E"),
    ]
    idx = min(filled, 6)
    return phases[idx]


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    init_state()

    st.set_page_config(
        page_title="Vidya — Gemini Live POC",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
      .stApp { background:#0B0F19; }
      #MainMenu, footer, header { visibility:hidden; }
      .stDeployButton { display:none; }
      [data-testid="stSidebar"] { background:#0F172A; border-right:1px solid #1E293B; }
      .stButton>button { border-radius:12px !important; font-weight:600 !important;
                         font-family:'Plus Jakarta Sans',sans-serif !important; }
      .stTextInput>div>div>input {
          background:#1E293B !important; color:#E2E8F0 !important;
          border:1px solid #334155 !important; border-radius:12px !important; }
      .science-badge { display:inline-block; background:rgba(167,139,250,0.15);
          color:#A78BFA; font-size:11px; padding:3px 10px; border-radius:20px;
          margin:2px 4px; font-weight:600; }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("""
        <div style="text-align:center;padding:20px 0 10px;">
          <div style="font-size:42px;font-weight:800;
               background:linear-gradient(135deg,#A78BFA,#6D28D9);
               -webkit-background-clip:text;-webkit-text-fill-color:transparent;">VIDYA</div>
          <div style="font-size:12px;color:#64748B;letter-spacing:2px;
               text-transform:uppercase;margin-top:2px;">Gemini Live POC</div>
        </div>
        """, unsafe_allow_html=True)

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

        # Extracted info
        st.markdown("""<div style="font-size:13px;font-weight:700;color:#A78BFA;
                    letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;">
                    📋 Extracted Info</div>""", unsafe_allow_html=True)

        info = st.session_state.extracted_info
        for label, key in [
            ("👤 Name",       "name"),
            ("🏫 Background", "background"),
            ("💼 Trigger",    "career_context"),
            ("⚡ Skills",     "skills"),
            ("🎯 Goal",       "goal"),
            ("⏰ Time/Week",  "time_commitment"),
            ("🌐 Language",   "preferred_language"),
        ]:
            value = info[key]
            bg     = "#1E293B" if value else "#0F172A"
            border = "solid #334155" if value else "dashed #1E293B"
            color  = "#E2E8F0" if value else "#475569"
            italic = "" if value else "font-style:italic;"
            display = value if value else "Waiting..."
            opacity = "1" if value else "0.5"
            st.markdown(f"""
            <div style="background:{bg};border:1px {border};border-radius:8px;
                        padding:8px 12px;margin-bottom:6px;opacity:{opacity};">
              <div style="font-size:10px;color:#64748B;text-transform:uppercase;
                          letter-spacing:0.5px;">{label}</div>
              <div style="font-size:13px;color:{color};margin-top:2px;{italic}">
                  {display}</div>
            </div>""", unsafe_allow_html=True)

        filled = sum(1 for v in info.values() if v)
        pct    = int(filled / 7 * 100)
        st.markdown(f"""
        <div style="margin-top:12px;">
          <div style="font-size:11px;color:#64748B;margin-bottom:4px;">
              Info gathered: {filled}/7 ({pct}%)</div>
          <div style="background:#1E293B;border-radius:8px;height:8px;overflow:hidden;">
            <div style="background:linear-gradient(90deg,#6D28D9,#A78BFA);
                        width:{pct}%;height:100%;border-radius:8px;
                        transition:width 0.5s ease;"></div>
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("""<div style="font-size:13px;font-weight:700;color:#A78BFA;
                    letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;">
                    🧠 Science Applied</div>""", unsafe_allow_html=True)
        phase_science = {
            1: ["Cognitive Load","Translanguaging"],
            2: ["Schema Theory","ZPD"],
            3: ["Funds of Knowledge","Self-Efficacy"],
            4: ["Schema Theory","Self-Efficacy"],
            5: ["Goal-Setting","Stereotype Threat"],
            6: ["Implementation Intentions"],
            7: ["Possible Selves"],
        }
        phase_num = detect_phase(info, st.session_state.turn_count)[0]
        for s in phase_science.get(phase_num, []):
            st.markdown(f'<span class="science-badge">{s}</span>', unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("""<div style="font-size:11px;color:#475569;text-align:center;">
                    Powered by<br>
                    <span style="color:#4285F4;font-weight:700;">Gemini</span>
                    <span style="color:#EA4335;font-weight:700;"> 2.0 </span>
                    <span style="color:#FBBC05;font-weight:700;">Flash</span>
                    </div>""", unsafe_allow_html=True)

    # ── Main ─────────────────────────────────────────────────────────────────
    col_chat, col_panel = st.columns([3, 1])

    with col_chat:
        st.markdown("""
        <div style="margin-bottom:20px;">
          <h1 style="font-size:26px;font-weight:800;color:#E2E8F0;margin:0;
                     font-family:'Plus Jakarta Sans',sans-serif;">
              🎙️ Talk to Vidya
          </h1>
          <p style="color:#64748B;font-size:14px;margin-top:6px;">
              Science-backed onboarding · Powered by Gemini 2.0 Flash ·
              Hindi, English, or mix
          </p>
        </div>
        """, unsafe_allow_html=True)

        chat_container = st.container(height=480)

        with chat_container:
            if not st.session_state.started and st.session_state.api_key:
                if st.button("▶️  Start Conversation with Vidya",
                             use_container_width=True, type="primary"):
                    sess = VidyaTextSession(st.session_state.api_key)
                    opening = run_async(sess.start())
                    st.session_state.session = sess
                    st.session_state.chat_log.append({
                        "role": "assistant", "text": opening,
                        "time": datetime.now().strftime("%H:%M")
                    })
                    st.session_state.started = True
                    st.session_state.turn_count = 1
                    st.rerun()

            elif not st.session_state.api_key:
                st.markdown("""
                <div style="text-align:center;padding:120px 40px;color:#475569;">
                  <div style="font-size:48px;margin-bottom:12px;">🔑</div>
                  <div style="font-size:16px;font-weight:600;color:#64748B;">
                      Enter your Google AI API key in the sidebar</div>
                  <div style="font-size:13px;margin-top:8px;color:#475569;">
                      Get one free at
                      <a href="https://aistudio.google.com/apikey"
                         style="color:#A78BFA;">aistudio.google.com</a>
                  </div>
                </div>""", unsafe_allow_html=True)

            else:
                for entry in st.session_state.chat_log:
                    avatar = "🎓" if entry["role"] == "assistant" else "🧑"
                    with st.chat_message(entry["role"], avatar=avatar):
                        st.markdown(entry["text"])

        if st.session_state.started:
            user_input = st.chat_input(
                "Type your message (Hindi, English, or mix)...",
                key="chat_input"
            )
            if user_input:
                now = datetime.now().strftime("%H:%M")
                st.session_state.chat_log.append(
                    {"role": "user", "text": user_input, "time": now}
                )
                st.session_state.turn_count += 1

                sess: VidyaTextSession = st.session_state.session
                with st.spinner("Vidya is thinking..."):
                    response = run_async(sess.send(user_input))

                # Sync extracted info back to session state
                st.session_state.extracted_info = sess.info

                st.session_state.chat_log.append(
                    {"role": "assistant", "text": response, "time": now}
                )
                st.session_state.turn_count += 1

                if any(p in response.lower() for p in [
                    "12 week","12 hafte","picture","future","ready?","ready ho?","shuru"
                ]):
                    st.session_state.aha_reached = True

                st.rerun()

    with col_panel:
        # Turn counter
        st.markdown(f"""
        <div style="background:#1E293B;border:1px solid #334155;border-radius:14px;
                    padding:16px;text-align:center;margin-bottom:12px;">
          <div style="font-size:10px;color:#64748B;text-transform:uppercase;
                      letter-spacing:1px;">Turn</div>
          <div style="font-size:40px;font-weight:800;color:#A78BFA;margin:4px 0;">
              {st.session_state.turn_count}</div>
        </div>""", unsafe_allow_html=True)

        # Phase
        p_num, p_name, p_color = detect_phase(
            st.session_state.extracted_info, st.session_state.turn_count
        )
        st.markdown(f"""
        <div style="background:#1E293B;border:1px solid {p_color}44;border-radius:14px;
                    padding:16px;text-align:center;margin-bottom:12px;">
          <div style="font-size:10px;color:#64748B;text-transform:uppercase;
                      letter-spacing:1px;">Phase {p_num}</div>
          <div style="font-size:15px;font-weight:700;color:{p_color};margin:6px 0;">
              {p_name}</div>
        </div>""", unsafe_allow_html=True)

        # Phase ladder
        all_phases = [
            ("Rapport",1),("Context",2),("Pain",3),("Skills",4),
            ("Belief",5),("Commit",6),("Reveal",7),
        ]
        st.markdown("""<div style="background:#1E293B;border:1px solid #334155;
                    border-radius:14px;padding:16px;margin-bottom:12px;">""",
                   unsafe_allow_html=True)
        for name, num in all_phases:
            active = num == p_num
            done   = num < p_num
            c  = "#A78BFA" if active else ("#22C55E" if done else "#334155")
            ic = "●" if active else ("✓" if done else "○")
            tc = "#E2E8F0" if active else ("#94A3B8" if done else "#475569")
            fw = "600" if active else "400"
            st.markdown(f"""
            <div style="display:flex;align-items:center;margin-bottom:4px;">
              <span style="color:{c};font-size:13px;margin-right:8px;
                           font-weight:bold;">{ic}</span>
              <span style="color:{tc};font-size:12px;font-weight:{fw};">{name}</span>
            </div>""", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Aha
        if st.session_state.aha_reached:
            st.markdown("""
            <div style="background:linear-gradient(135deg,#065F46,#047857);
                        border-radius:14px;padding:16px;text-align:center;">
              <div style="font-size:28px;">✨</div>
              <div style="font-size:14px;font-weight:700;color:#D1FAE5;">AHA REACHED</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background:#1E293B;border:1px dashed #334155;
                        border-radius:14px;padding:16px;text-align:center;opacity:0.6;">
              <div style="font-size:10px;color:#475569;text-transform:uppercase;
                          letter-spacing:1px;">Aha Moment</div>
              <div style="font-size:14px;color:#475569;margin-top:4px;">Pending...</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 New Conversation", use_container_width=True):
            keys = ["session","chat_log","turn_count","aha_reached","started"]
            for k in keys:
                if k in st.session_state:
                    del st.session_state[k]
            st.session_state.extracted_info = {k: None for k in st.session_state.extracted_info}
            st.rerun()


if __name__ == "__main__":
    main()
