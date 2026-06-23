"""
Vidya Voice POC — Gemini Live Handler

Handles the Gemini Live API session via google-genai SDK.
Audio: raw 16-bit PCM, 16kHz in / 24kHz out, little-endian.

Usage (standalone):
    import asyncio
    from realtime_handler import VidyaVoiceSession

    async def main():
        session = VidyaVoiceSession(
            api_key="AIza...",
            on_user_transcript=lambda t: print(f"[You] {t}"),
            on_assistant_transcript=lambda t: print(f"[Vidya] {t}"),
            on_info_update=lambda i: print(f"[Info] {i}"),
        )
        await session.run()

    asyncio.run(main())
"""

import asyncio
import re
import base64
import json
import os
from typing import Callable, Optional, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    import websockets
except ImportError:
    raise ImportError("pip install websockets")

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("pip install google-genai")

from vidya_prompt import get_system_prompt
LEARNER_SYSTEM_AVAILABLE = False

# Audio constants
MIC_RATE     = 16000   # Gemini input: 16kHz PCM
SPEAKER_RATE = 24000   # Gemini output: 24kHz PCM

# Silence detection constants
SILENCE_THRESHOLD = 300      # RMS amplitude threshold (quieter = silent)
SILENCE_DURATION = 2.0       # Seconds of silence to consider turn complete
SILENCE_FRAMES = int(SILENCE_DURATION * MIC_RATE / 1024)  # ~32 frames at 16kHz, 1024 bytes/frame

# Load Gemini model from .env or use default
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-09-2025")


# ─── Info Extractor ───────────────────────────────────────────────────────────

class InfoExtractor:
    """Progressively extracts structured info from conversation text."""

    def __init__(self):
        self.info: Dict[str, Optional[str]] = {
            "name": None,
            "background": None,
            "career_context": None,
            "skills": None,
            "goal": None,
            "time_commitment": None,
            "preferred_language": None,
            "company": None,
            "college": None,
        }

    def update(self, role: str, text: str):
        if role != "user":
            return
        tl = text.lower().strip()

        if not self.info["name"]:
            for pat in [
                r"(?:i am|i'm|my name is|main|mera naam)\s+(\w+)",
                r"^(\w+)[\.\,\!\s]",
            ]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    n = m.group(1).strip().title()
                    skip = {"hi","hello","hey","yes","no","ok","sure","working",
                            "studying","fine","good","english","hindi","haan","nahi",
                            "the","i","my","a","an","it","is","am","so","yeah"}
                    if len(n) > 1 and n.lower() not in skip:
                        self.info["name"] = n
                        break

        if not self.info["preferred_language"]:
            hindi_words = ["hoon","hai","mein","kya","haan","nahin","theek","chalega",
                           "yaar","bhai","samajh","matlab","bilkul","sahi","dekho"]
            tamil_words = ["naan","ungal","enna","romba","vanakkam","illa","seri"]
            telugu_words = ["nenu","meeru","emiti","chala","bagundi","namaskaaram"]
            bengali_words = ["ami","amar","tumi","tomr","achho","bhalo","ki","haan"]
            malayalam_words = ["njan","ningal","enthu","sheriyanu","undo","alle"]
            marathi_words = ["mi","majha","tumhi","aahe","nahi","bara","chan"]
            gujarati_words = ["hoon","tamhe","kem","chho","saru","nathi","hari"]
            kannada_words = ["naanu","neevu","enu","houdu","illa","chennagide"]
            urdu_words = ["mein","aap","kya","haan","nahi","theek","shukriya","janab"]

            tl_words = set(tl.split())
            if sum(1 for w in hindi_words if w in tl) >= 2:
                self.info["preferred_language"] = "Hindi / Hinglish"
            elif sum(1 for w in tamil_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Tamil"
            elif sum(1 for w in telugu_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Telugu"
            elif sum(1 for w in bengali_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Bengali"
            elif sum(1 for w in malayalam_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Malayalam"
            elif sum(1 for w in marathi_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Marathi"
            elif sum(1 for w in gujarati_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Gujarati"
            elif sum(1 for w in kannada_words if w in tl_words) >= 2:
                self.info["preferred_language"] = "Kannada"
            elif sum(1 for w in urdu_words if w in tl) >= 2:
                self.info["preferred_language"] = "Urdu"
            elif "english" in tl:
                self.info["preferred_language"] = "English"

        # Detect company (for working professionals)
        if not self.info["company"]:
            companies = ["tcs", "infosys", "wipro", "accenture", "cognizant", "tech mahindra",
                        "ibm", "amazon", "microsoft", "google", "flipkart", "swiggy", "unacademy",
                        "oracle", "cisco", "hcl", "capgemini", "deloitte"]
            for company in companies:
                if company in tl:
                    self.info["company"] = company.upper()
                    break

        # Detect college (for students)
        if not self.info["college"]:
            colleges = ["iit", "nit", "bits", "vit", "lpu", "manipal", "srm", "jiit", "ggsipu",
                       "delhi", "bombay", "madras", "kharagpur", "tier-2", "tier 2"]
            for college in colleges:
                if college in tl:
                    # Try to capture full college name if available
                    if "iit" in tl:
                        match = re.search(r"iit\s+(\w+)?", text, re.IGNORECASE)
                        self.info["college"] = (match.group(0) if match else "IIT").title()
                    elif "nit" in tl:
                        match = re.search(r"nit\s+(\w+)?", text, re.IGNORECASE)
                        self.info["college"] = (match.group(0) if match else "NIT").title()
                    else:
                        self.info["college"] = college.upper()
                    break

        if not self.info["background"]:
            if any(w in tl for w in ["studying","student","b.tech","btech","college",
                                      "university","year","semester","padhai","final year"]):
                self.info["background"] = text[:120].strip()
            elif any(w in tl for w in ["working","work","company","job","kaam"]):
                self.info["background"] = text[:120].strip()

        if not self.info["skills"]:
            kw = ["python","java","javascript","react","node","sql","c++","html",
                  "css","docker","spring boot","microservices","pandas","machine learning",
                  "ml","git","aws","flutter","typescript","excel","power bi","etl"]
            found = [s.title() for s in kw if s in tl]
            if found:
                self.info["skills"] = ", ".join(found)

        if not self.info["career_context"]:
            urgency = ["placement","appraisal","hike","laid off","bench","batchmate",
                       "stuck","frustrated","linkedin","switch","rejected","failed",
                       "interview","salary","promotion"]
            if any(w in tl for w in urgency):
                self.info["career_context"] = text[:120].strip()

        if not self.info["goal"]:
            goals = ["product company","startup","switch","role","salary","lpa",
                     "ctc","promotion","senior","data engineer","frontend","backend",
                     "fullstack","placement","job"]
            if any(w in tl for w in goals):
                self.info["goal"] = text[:120].strip()

        if not self.info["time_commitment"]:
            m = re.search(r"(\d+)\s*(?:hours?|ghante|hrs?)", tl)
            if m:
                hrs = m.group(1)
                when = []
                if any(w in tl for w in ["morning","subah"]): when.append("mornings")
                if any(w in tl for w in ["evening","shaam","night"]): when.append("evenings")
                if "weekend" in tl: when.append("weekends")
                tag = f" ({', '.join(when)})" if when else ""
                self.info["time_commitment"] = f"{hrs} hrs/week{tag}"

    def get(self) -> Dict[str, Optional[str]]:
        return self.info.copy()

    def pct(self) -> int:
        filled = sum(1 for v in self.info.values() if v is not None)
        return int(filled / len(self.info) * 100)


# ─── Voice Session ────────────────────────────────────────────────────────────

class VidyaVoiceSession:
    """
    Gemini Live voice session.
    Browser audio → WebSocket → Gemini Live API → WebSocket → browser speaker.
    Transcript callbacks and learner signal extraction unchanged.
    """

    def __init__(
        self,
        api_key: str,
        on_user_transcript: Optional[Callable[[str], None]] = None,
        on_assistant_transcript: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_info_update: Optional[Callable[[Dict], None]] = None,
        chosen_languages: Optional[list] = None,
        # Learner system components
        learner_state_manager = None,
        signal_orchestrator = None,
        learner_session_id: Optional[str] = None,
        on_learner_signals: Optional[Callable[[Dict], None]] = None,
        on_learner_context: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self._on_user   = on_user_transcript or (lambda t: print(f"[You] {t}"))
        self._on_asst   = on_assistant_transcript or (lambda t: print(f"[Vidya] {t}"))
        self._on_status = on_status_change or (lambda s: print(f"[Status] {s}"))
        self._on_info   = on_info_update or (lambda i: None)
        self.chosen_languages = chosen_languages or []

        # Learner system callbacks
        self._on_learner_signals = on_learner_signals or (lambda s: None)
        self._on_learner_context = on_learner_context or (lambda c: None)

        self.extractor  = InfoExtractor()

        # Learner system components
        self.learner_state_manager = learner_state_manager
        self.signal_orchestrator = signal_orchestrator
        self.learner_session_id = learner_session_id or "streamlit_session"
        self.learner_state = None
        self.conversation_history: list = []
        self.last_processed_user_message = ""
        self.pending_user_message = ""
        self.model_is_responding = False

        if learner_state_manager and signal_orchestrator:
            print(f"[Learner System] Signal extraction enabled", flush=True)

        self._stop      = asyncio.Event()
        self._ws        = None                  # WebSocket connection to browser
        self._audio_queue: asyncio.Queue = asyncio.Queue()
        self._transcript_buffer = ""
        self._buffer_timer: Optional[asyncio.Task] = None

    def _process_learner_signals(self, user_message: str):
        """Extract learner signals from user message and build context."""
        if not LEARNER_SYSTEM_AVAILABLE or not self.learner_state_manager or not self.signal_orchestrator:
            print(f"[Learner System] SKIPPED: System not available (LEARNER_SYSTEM_AVAILABLE={LEARNER_SYSTEM_AVAILABLE})", flush=True)
            return

        try:
            print(f"[Learner System] Processing message: {user_message[:100]}", flush=True)

            if not self.learner_state:
                print(f"[Learner System] Initializing learner state for session: {self.learner_session_id}", flush=True)
                self.learner_state = self.learner_state_manager.get_or_initialize(self.learner_session_id)

            print(f"[Learner System] Current turn_count before processing: {self.learner_state.turn_count}", flush=True)
            print(f"[Learner System] Turn {self.learner_state.turn_count} - using LLM-first extraction", flush=True)

            extraction = self.signal_orchestrator.extract_signals(
                user_message=user_message,
                learner_state=self.learner_state,
                conversation_history=self.conversation_history,
                use_llm=True,
            )

            print(f"[Learner System] Extraction result: method={extraction.get('extraction_method')}, signals={extraction.get('merged_signals')}", flush=True)

            primary_result = extraction.get("llm_result") or extraction.get("rule_result")

            signal_result = SignalExtractionResult(
                extracted_signals=extraction["merged_signals"],
                extraction_method=extraction["extraction_method"],
                confidence=primary_result.confidence if primary_result else 0.7,
                per_signal_confidence=primary_result.per_signal_confidence if primary_result else {},
                reasoning=primary_result.reasoning if primary_result else "",
            )

            print(f"[Learner System] Signal result: {len(signal_result.extracted_signals)} signals, confidence={signal_result.confidence}", flush=True)

            updated_state = self.learner_state_manager.update_from_extraction(
                self.learner_session_id, signal_result
            )
            if updated_state is None:
                print(f"[Learner System] ERROR: update_from_extraction returned None!", flush=True)
                return
            self.learner_state = updated_state

            updated_state = self.learner_state_manager.update_conversation_turn(
                self.learner_session_id, extraction.get("engagement_score")
            )
            if updated_state is None:
                print(f"[Learner System] ERROR: update_conversation_turn returned None!", flush=True)
                return
            self.learner_state = updated_state

            extracted_info = self.extractor.get()
            self.learner_state = PromptContextInjector.update_learner_state_from_extraction(
                self.learner_state, extracted_info
            )

            print(f"[Learner System] After update: turn_count={self.learner_state.turn_count}", flush=True)

            signals_dict = self.learner_state.to_signal_summary() if self.learner_state else {}
            self._on_learner_signals(signals_dict)

            learner_context = PromptContextInjector.build_injection_for_system_prompt(
                self.learner_state
            )
            self._on_learner_context(learner_context)

            print(f"[Learner System] ✓ Successfully processed turn {self.learner_state.turn_count}", flush=True)

        except Exception as e:
            print(f"[Learner System] ERROR Signal extraction failed: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()

    async def run(self):
        """Connect to Gemini Live and run until stop() is called."""
        print(f"[RealTime] Starting session with model={GEMINI_MODEL}", flush=True)
        client = genai.Client(api_key=self.api_key)
        print(f"[RealTime] Client created", flush=True)

        # Build system prompt with initial learner context (if available)
        learner_context = ""
        scenario_context = ""
        if LEARNER_SYSTEM_AVAILABLE and self.learner_state_manager and self.signal_orchestrator:
            try:
                self.learner_state = self.learner_state_manager.get_or_initialize("streamlit_session")
                learner_context = PromptContextInjector.build_injection_for_system_prompt(
                    self.learner_state
                )
                scenario_context = PromptContextInjector.build_scenario_specific_context(
                    self.learner_state
                ) or ""
            except Exception as e:
                print(f"[Learner System] Initial context build failed: {e}", flush=True)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=get_system_prompt(
                    learner_context,
                    scenario_context=scenario_context,
                    chosen_languages=self.chosen_languages if self.chosen_languages else None,
                ))]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Aoede"
                    )
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )
        print(f"[RealTime] Config created with learner context injection", flush=True)

        self._on_status("connecting")

        try:
            print(f"[RealTime] Attempting to connect to Gemini Live API...", flush=True)
            async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
                print(f"[RealTime] Connected! Starting audio tasks...", flush=True)
                self._on_status("ready")
                self._on_status("listening")
                await asyncio.gather(
                    self._send_audio(session),
                    self._receive(session),
                )
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"[RealTime] Connection error: {error_msg}", flush=True)
            import traceback
            traceback.print_exc()

            if "keepalive" in str(e).lower() or "ping timeout" in str(e).lower():
                print(f"[RealTime] Connection keepalive timeout - gracefully closing", flush=True)
                self._on_status("keepalive_timeout")
            else:
                self._on_status(f"error: {error_msg}")
        finally:
            try:
                await client.aio.aclose()
            except:
                pass
            self._on_status("disconnected")
            print(f"[RealTime] Session ended", flush=True)

    def stop(self):
        self._stop.set()

    async def _flush_transcript_buffer(self, force=False):
        """Flush buffered transcript after natural pause of no new input."""
        if not force:
            await asyncio.sleep(1.0)

        if self._transcript_buffer.strip():
            text = self._transcript_buffer.strip()
            print(f"[RealTime] Assistant full message: {text}", flush=True)
            self._on_asst(text)
            self.conversation_history.append({"role": "assistant", "content": text})
            self._transcript_buffer = ""

    async def _send_audio(self, session):
        """Read audio chunks from browser via WebSocket queue and send to Gemini."""
        print(f"[RealTime] _send_audio: waiting for browser audio chunks", flush=True)
        frame_count = 0
        try:
            while not self._stop.is_set():
                try:
                    data = await asyncio.wait_for(self._audio_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                frame_count += 1
                try:
                    await session.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
                    if frame_count % 100 == 0:
                        print(f"[RealTime] Sent {frame_count} audio frames to Gemini", flush=True)
                except Exception as e:
                    print(f"[RealTime] Error sending audio chunk: {type(e).__name__}: {str(e)[:100]}", flush=True)
                    error_str = str(e).lower()
                    if any(x in error_str for x in ["connectionclosed", "websocket", "1011"]):
                        print(f"[RealTime] Connection closed by server, stopping audio send", flush=True)
                        self._stop.set()
                        break
        except asyncio.CancelledError:
            print(f"[RealTime] _send_audio cancelled", flush=True)
        except Exception as e:
            print(f"[RealTime] Fatal error in audio send loop: {type(e).__name__}: {e}", flush=True)
        finally:
            print(f"[RealTime] _send_audio ended after {frame_count} frames", flush=True)

    async def _receive(self, session):
        """Receive audio+transcripts from Gemini and send audio back to browser via WebSocket."""
        print(f"[RealTime] _receive: started", flush=True)
        try:
            while not self._stop.is_set():
                response_count = 0
                try:
                    async for response in session.receive():
                        response_count += 1

                        if self._stop.is_set():
                            return

                        sc = response.server_content
                        if not sc:
                            continue

                        is_empty = not sc.model_turn and not sc.input_transcription and not sc.output_transcription
                        if is_empty:
                            continue

                        # Send audio back to browser via WebSocket
                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data and self._ws:
                                    try:
                                        audio_b64 = base64.b64encode(part.inline_data.data).decode()
                                        await self._ws.send_text(json.dumps({
                                            "type": "audio",
                                            "data": audio_b64
                                        }))
                                    except Exception as e:
                                        print(f"[RealTime] Error sending audio to browser: {e}", flush=True)

                            if not self.model_is_responding and self.pending_user_message:
                                self.model_is_responding = True
                                print(f"[RealTime] *** MODEL AUDIO RECEIVED - Processing pending user message ***", flush=True)
                                if self.pending_user_message != self.last_processed_user_message:
                                    print(f"[RealTime] Processing: {self.pending_user_message[:100]}", flush=True)
                                    self._process_learner_signals(self.pending_user_message)
                                    self.last_processed_user_message = self.pending_user_message
                                    self.conversation_history.append({"role": "user", "content": self.pending_user_message})

                        # User transcript
                        if sc.input_transcription and sc.input_transcription.text.strip():
                            t = sc.input_transcription.text.strip()
                            print(f"[RealTime] User said (fragment): {t}", flush=True)
                            self.extractor.update("user", t)
                            self._on_user(t)
                            self._on_info(self.extractor.get())
                            self.pending_user_message = t
                            self.model_is_responding = False

                        # Assistant transcript
                        if sc.output_transcription and sc.output_transcription.text:
                            text = sc.output_transcription.text.strip()
                            if text:
                                if not self.model_is_responding and self.pending_user_message:
                                    self.model_is_responding = True
                                    print(f"[RealTime] *** OUTPUT TRANSCRIPTION DETECTED ***", flush=True)
                                    if self.pending_user_message != self.last_processed_user_message:
                                        self._process_learner_signals(self.pending_user_message)
                                        self.last_processed_user_message = self.pending_user_message
                                        self.conversation_history.append({"role": "user", "content": self.pending_user_message})

                                self._transcript_buffer += text + " "
                                print(f"[RealTime] Bot buffering: {text}", flush=True)

                                if self._buffer_timer:
                                    self._buffer_timer.cancel()
                                self._buffer_timer = asyncio.create_task(self._flush_transcript_buffer())

                    print(f"[RealTime] Receive batch ended after {response_count} responses", flush=True)

                except StopAsyncIteration:
                    print(f"[RealTime] Receive generator completed", flush=True)

        except asyncio.CancelledError:
            print(f"[RealTime] Receive loop cancelled", flush=True)
        except Exception as e:
            print(f"[RealTime] Error in receive loop: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            if self._transcript_buffer.strip():
                await self._flush_transcript_buffer(force=True)
            print(f"[RealTime] _receive ended", flush=True)

    @property
    def info(self) -> Dict:
        return self.extractor.get()


# ─── Text session (for Streamlit text/chat mode) ──────────────────────────────

class VidyaTextSession:
    """
    Async text session using Gemini (gemini-2.0-flash).
    Used as the backend for app_browser.py.
    """

    def __init__(self, api_key: str):
        self.client  = genai.Client(api_key=api_key)
        self.history = []
        self.extractor = InfoExtractor()

    async def start(self) -> str:
        return await self.send(
            "[SYSTEM: The user just opened the app. This is your very first message. "
            "Speak ONLY in English first. Greet them warmly as Vidya. Ask their name. "
            "After getting their name, offer them language choice (English or Hindi). "
            "2-3 sentences max. Warm and human, not corporate.]"
        )

    async def send(self, user_text: str) -> str:
        self.extractor.update("user", user_text)
        self.history.append({"role": "user", "parts": [{"text": user_text}]})

        response = await self.client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=self.history,
            config=types.GenerateContentConfig(
                system_instruction=get_system_prompt(),
                temperature=0.7,
                max_output_tokens=300,
            ),
        )
        reply = response.text or ""
        self.history.append({"role": "model", "parts": [{"text": reply}]})
        self.extractor.update("assistant", reply)
        return reply

    @property
    def info(self) -> Dict:
        return self.extractor.get()

    @property
    def info_pct(self) -> int:
        return self.extractor.pct()
