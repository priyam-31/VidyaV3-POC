# Vidya Voice Onboarding POC

**Science-backed voice onboarding conversation for career transformation.**

Two ICPs served: **Stuck Service Engineers** and **Tier 2/3 Engineering Students**.
No hardcoded scripts — the AI adapts to whoever walks in.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    STREAMLIT UI                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │  Chat Area   │  │ Info Panel   │  │ Phase Tracker  │  │
│  │  (voice/text)│  │ (extracted)  │  │ (7 phases)     │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────┘  │
│         │                │                                │
│  ┌──────▼────────────────▼───────┐                       │
│  │      Info Extractor           │ ← Heuristic NLP       │
│  │  (name, skills, goal, etc.)   │   from user messages   │
│  └──────┬────────────────────────┘                       │
└─────────┼────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────┐
│   OpenAI API                │
│                             │
│   Option A: Chat API        │ ← app_browser.py (text mode)
│   (gpt-4o + system prompt)  │    Works everywhere, no mic needed
│                             │
│   Option B: Realtime API    │ ← app.py + realtime_handler.py
│   (WebSocket + voice)       │    Requires mic + pyaudio
│                             │
└─────────────────────────────┘
```

## The Science Inside

The system prompt (`vidya_prompt.py`) is the brain. It encodes 10 educational
psychology principles — not as guidelines, but as conversation laws:

| Principle | Where It Fires |
|-----------|---------------|
| Cognitive Load Theory (Sweller) | ONE question per turn, short responses |
| Translanguaging (García) | Hindi/English offer in first message, code-mixing |
| Schema Theory (Bartlett) | Anchor advice to skills user already named |
| Stereotype Threat (Steele) | NEVER proactively mention college tier disadvantage |
| Self-Efficacy (Bandura) | Affirm strengths BEFORE surfacing gaps |
| Possible Selves (Markus & Nurius) | Personalised "Future You" reveal at conversation end |
| Goal-Setting Theory (Locke & Latham) | Convert vague goals to specific targets |
| Implementation Intentions (Gollwitzer) | Ask WHEN, not just how many hours |
| Funds of Knowledge (Moll) | All prior experience = valuable |
| Zone of Proximal Development (Vygotsky) | Language calibrated to user level |

**The AI does NOT follow a script.** It follows a 7-phase architecture
(Rapport → Context → Pain → Skills → Belief → Commitment → Reveal) and
adapts based on what the user actually says.

---

## Files

```
vidya-voice-poc-gemini/
├── app_browser.py        # ← START HERE — Streamlit app (text mode, works everywhere)
├── app.py                # Streamlit app (voice mode, needs pyaudio + mic)
├── realtime_handler.py   # OpenAI Realtime API WebSocket manager
├── vidya_prompt.py       # The science-encoded system prompt
├── requirements.txt      # Dependencies
├── models/               # Data models for learner state
├── services/             # Signal extraction and learner state management
├── temp_learner_states/  # Saved conversation states
└── README.md             # This file
```

## Quick Start

### Option 1: Text Mode (Recommended for testing)

```bash
pip install streamlit openai
streamlit run app_browser.py
```

1. Enter your OpenAI API key in the sidebar
2. Click "Start Conversation with Vidya"
3. Type naturally — Hindi, English, or mix
4. Watch the sidebar extract info in real-time

### Option 2: Voice Mode (Requires mic + PyAudio)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Requires:
- OpenAI API key with Realtime API access
- PyAudio (may need `portaudio` on Mac: `brew install portaudio`)
- Working microphone

### Option 3: CLI Voice (Direct WebSocket)

```python
from realtime_handler import VidyaVoiceSession

session = VidyaVoiceSession(
    api_key="sk-...",
    on_user_transcript=lambda t: print(f"[You] {t}"),
    on_assistant_transcript=lambda t: print(f"[Vidya] {t}"),
    on_info_update=lambda i: print(f"[Info] {i}"),
)
session.connect()
session.start_microphone()

# Talk naturally... Vidya responds via speaker
# Press Ctrl+C to stop

input("Press Enter to stop...")
session.stop()
```

---

## What Gets Extracted

The app extracts 7 data points from natural conversation (no forms):

| Field | Example |
|-------|---------|
| Name | "Arjun Sharma" |
| Background | "Working at Wipro (2 yrs)" or "Final Year B.Tech at IIIT" |
| Career Context | "Batchmate got ₹22L at PhonePe, I'm still at ₹6.4L" |
| Skills | "Java, Spring Boot, SQL" |
| Goal | "Product company, ₹18L+" |
| Time/Week | "12 hrs/week (evenings)" |
| Language | "Hindi / Hinglish" |

---

## How to Customise

### Add new ICPs
The system prompt is ICP-agnostic — it adapts to any user. But you can
add ICP-specific wrong beliefs to the prompt in `vidya_prompt.py` under
the "Common wrong beliefs" section.

### Change the voice
In `realtime_handler.py`, change `"voice": "shimmer"` to:
- `"alloy"` — neutral
- `"echo"` — male
- `"fable"` — British
- `"onyx"` — deep male
- `"nova"` — female
- `"shimmer"` — female (current, warm tone)

### Adjust conversation length
In `vidya_prompt.py`, modify `max_response_output_tokens` (currently 300)
to control response length. Lower = snappier turns.

---

## Deployment

For production, you'd want:
1. **Audio streaming via WebRTC** — use `streamlit-webrtc` or deploy as
   a React app with direct WebSocket to OpenAI
2. **Persistent storage** — save extracted info to a database
3. **Analytics** — track phase progression, dropout points, aha rates
4. **Voice Activity Detection tuning** — adjust `silence_duration_ms`
   and `threshold` for Indian accent + ambient noise patterns

---

## Known Limitations

- **Text mode** uses Chat API (gpt-4o), not Realtime API — no voice I/O
- **Voice mode** requires local mic access — won't work in cloud-deployed Streamlit
- **Info extraction** is heuristic (regex) — production should use LLM extraction
- **No persistent memory** — each session starts fresh
- **Single user** — no concurrent session handling
