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
import struct
import sys
import os
from typing import Callable, Optional, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

try:
    import pyaudio
except ImportError:
    raise ImportError("pip install pyaudio")

try:
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("pip install google-genai")

from vidya_prompt import get_system_prompt

# Setup path for learner system imports
parent_dir = os.path.dirname(__file__)
sys.path.insert(0, parent_dir)
sys.path.insert(0, os.path.join(parent_dir, 'models'))

# Import learner system modules
try:
    from models.learner_state_model import SignalExtractionResult
    from services.prompt_injector import PromptContextInjector
    LEARNER_SYSTEM_AVAILABLE = True
except Exception as e:
    print(f"[RealTime] Learner system not available: {e}", flush=True)
    LEARNER_SYSTEM_AVAILABLE = False


# Audio constants
MIC_RATE     = 16000   # Gemini input: 16kHz PCM
SPEAKER_RATE = 24000   # Gemini output: 24kHz PCM
FORMAT       = pyaudio.paInt16
CHANNELS     = 1
CHUNK        = 1024

# Silence detection constants
SILENCE_THRESHOLD = 300      # RMS amplitude threshold (quieter = silent)
SILENCE_DURATION = 2.0       # Seconds of silence to consider turn complete
SILENCE_FRAMES = int(SILENCE_DURATION * MIC_RATE / CHUNK)  # ~32 frames at 16kHz, 1024 bytes/frame

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
            hindi = ["hoon","hai","mein","kya","haan","nahin","theek","chalega",
                     "yaar","bhai","samajh","matlab","bilkul","sahi","dekho"]
            if sum(1 for w in hindi if w in tl) >= 2:
                self.info["preferred_language"] = "Hindi / Hinglish"
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
    Mic audio → Gemini Live API → speaker audio, with transcript callbacks.
    Now with integrated learner signal extraction.
    """

    def __init__(
        self,
        api_key: str,
        on_user_transcript: Optional[Callable[[str], None]] = None,
        on_assistant_transcript: Optional[Callable[[str], None]] = None,
        on_status_change: Optional[Callable[[str], None]] = None,
        on_info_update: Optional[Callable[[Dict], None]] = None,
        # NEW: Learner system components
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
        
        # NEW: Learner system callbacks
        self._on_learner_signals = on_learner_signals or (lambda s: None)
        self._on_learner_context = on_learner_context or (lambda c: None)
        
        self.extractor  = InfoExtractor()
        
        # NEW: Learner system components
        self.learner_state_manager = learner_state_manager
        self.signal_orchestrator = signal_orchestrator
        self.learner_session_id = learner_session_id or "streamlit_session"
        self.learner_state = None
        self.conversation_history: list = []
        self.last_processed_user_message = ""  # Track the last processed message to avoid reprocessing fragments        self.pending_user_message = ""  # Temporarily store user message to process when model responds
        self.model_is_responding = False  # Track if model is currently responding        
        if learner_state_manager and signal_orchestrator:
            print(f"[Learner System] Signal extraction enabled", flush=True)

        self._stop      = asyncio.Event()
        self._pa: Optional[pyaudio.PyAudio] = None
        self._transcript_buffer = ""  # Buffer for streaming transcripts
        self._buffer_timer: Optional[asyncio.Task] = None

    def _calculate_rms(self, audio_data: bytes) -> float:
        """Calculate RMS (root mean square) amplitude from 16-bit PCM audio frame."""
        try:
            # Unpack 16-bit signed integers (little-endian)
            samples = struct.unpack(f'<{len(audio_data)//2}h', audio_data)
            if not samples:
                return 0.0
            # Calculate RMS
            mean_square = sum(s * s for s in samples) / len(samples)
            rms = (mean_square ** 0.5) / 32768.0  # Normalize to 0-1 range
            return rms
        except Exception as e:
            print(f"[RealTime] Error calculating RMS: {e}", flush=True)
            return 0.0

    def _is_silent(self, audio_data: bytes) -> bool:
        """Check if audio frame is below silence threshold."""
        rms = self._calculate_rms(audio_data)
        return rms < (SILENCE_THRESHOLD / 32768.0)
    
    def _process_learner_signals(self, user_message: str):
        """Extract learner signals from user message and build context."""
        if not LEARNER_SYSTEM_AVAILABLE or not self.learner_state_manager or not self.signal_orchestrator:
            print(f"[Learner System] SKIPPED: System not available (LEARNER_SYSTEM_AVAILABLE={LEARNER_SYSTEM_AVAILABLE})", flush=True)
            return
        
        try:
            print(f"[Learner System] Processing message: {user_message[:100]}", flush=True)
            
            # Get learner state
            if not self.learner_state:
                print(f"[Learner System] Initializing learner state for session: {self.learner_session_id}", flush=True)
                self.learner_state = self.learner_state_manager.get_or_initialize(self.learner_session_id)
            
            print(f"[Learner System] Current turn_count before processing: {self.learner_state.turn_count}", flush=True)
            
            # LLM-first extraction: always use LLM (with rule-based fallback if needed)
            print(f"[Learner System] Turn {self.learner_state.turn_count} - using LLM-first extraction", flush=True)
            
            # Extract signals with LLM-first approach
            extraction = self.signal_orchestrator.extract_signals(
                user_message=user_message,
                learner_state=self.learner_state,
                conversation_history=self.conversation_history,
                use_llm=True,  # Always use LLM extraction (LLM-first approach)
            )
            
            print(f"[Learner System] Extraction result: method={extraction.get('extraction_method')}, signals={extraction.get('merged_signals')}", flush=True)
            
            # Update learner state
            # Get the best extraction result (prefer LLM if available)
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
            
            # ALSO UPDATE WITH SCENARIO-SPECIFIC INFORMATION from conversation extraction
            extracted_info = self.extractor.get()
            self.learner_state = PromptContextInjector.update_learner_state_from_extraction(
                self.learner_state, extracted_info
            )
            
            print(f"[Learner System] After update: turn_count={self.learner_state.turn_count}, detected_signals={self.learner_state.detected_signals}, confidence_scores={self.learner_state.confidence_scores}", flush=True)
            print(f"[Learner System] Scenario context: company={self.learner_state.current_company}, college={self.learner_state.college_name}, goal={self.learner_state.specific_goal}", flush=True)
            
            # Send signals callback
            signals_dict = self.learner_state.to_signal_summary() if self.learner_state else {}
            self._on_learner_signals(signals_dict)
            
            # Build and send context injection
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
                # Also build scenario-specific context (more specific than generic ICP)
                scenario_context = PromptContextInjector.build_scenario_specific_context(
                    self.learner_state
                ) or ""
            except Exception as e:
                print(f"[Learner System] Initial context build failed: {e}", flush=True)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=get_system_prompt(learner_context, scenario_context=scenario_context))]
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
        self._pa = pyaudio.PyAudio()
        print(f"[RealTime] PyAudio initialized", flush=True)

        try:
            print(f"[RealTime] Attempting to connect to Gemini Live API...", flush=True)
            async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
                print(f"[RealTime] Connected! Starting audio tasks...", flush=True)
                self._on_status("ready")
                print(f"[RealTime] System prompt will trigger initial greeting. Listening for audio...", flush=True)
                
                self._on_status("listening")
                # Receive and send audio concurrently - bot will greet via system prompt
                await asyncio.gather(
                    self._send_audio(session),
                    self._receive(session),
                )
        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)[:100]}"
            print(f"[RealTime] Connection error: {error_msg}", flush=True)
            import traceback
            traceback.print_exc()
            
            # Check if it's a keepalive timeout - this is expected sometimes
            if "keepalive" in str(e).lower() or "ping timeout" in str(e).lower():
                print(f"[RealTime] Connection keepalive timeout (expected in long sessions) - gracefully closing", flush=True)
                self._on_status("keepalive_timeout")
            else:
                self._on_status(f"error: {error_msg}")
        finally:
            if self._pa:
                self._pa.terminate()
            # Properly close the client
            try:
                await client.aio.aclose()
            except:
                pass
            self._on_status("disconnected")
            print(f"[RealTime] Session ended", flush=True)

    def stop(self):
        self._stop.set()

    async def _flush_transcript_buffer(self, force=False):
        """Flush buffered transcript after natural pause (1000ms) of no new input (or force immediately)."""
        if not force:
            await asyncio.sleep(1.0)  # Wait 1000ms (1 sec) for natural sentence boundaries in speech
        
        if self._transcript_buffer.strip():
            text = self._transcript_buffer.strip()
            print(f"[RealTime] Assistant full message: {text}", flush=True)
            self._on_asst(text)
            
            # NEW: Track assistant message in conversation history
            self.conversation_history.append({"role": "assistant", "content": text})
            
            self._transcript_buffer = ""

    async def _send_audio(self, session):
        mic = self._pa.open(
            format=FORMAT, channels=CHANNELS, rate=MIC_RATE,
            input=True, frames_per_buffer=CHUNK,
        )
        print(f"[RealTime] Microphone stream opened", flush=True)
        try:
            frame_count = 0
            silent_frame_count = 0
            user_speaking = False
            
            while not self._stop.is_set():
                data = await asyncio.get_event_loop().run_in_executor(
                    None, mic.read, CHUNK
                )
                frame_count += 1
                
                # Check if this frame is silent - for logging/diagnostics only
                is_silent = self._is_silent(data)
                
                if is_silent:
                    silent_frame_count += 1
                    # Log when silence threshold reached (informational)
                    if silent_frame_count == SILENCE_FRAMES:
                        print(f"[RealTime] Silence detected ({SILENCE_DURATION}s) - user turn likely complete", flush=True)
                else:
                    # User is speaking
                    if not user_speaking:
                        print(f"[RealTime] User started speaking at frame {frame_count}", flush=True)
                        user_speaking = True
                    silent_frame_count = 0
                
                # IMPORTANT: Always send audio frames to maintain connection
                # Gemini Live API has built-in VAD and expects continuous stream
                # Do NOT pause sending - the API relies on the continuous audio stream
                try:
                    await session.send_realtime_input(
                        audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                    )
                    if frame_count % 100 == 0:  # Log every 100 frames (~1.6 sec of audio)
                        print(f"[RealTime] Sent {frame_count} audio frames to Gemini...", flush=True)
                except Exception as e:
                    print(f"[RealTime] Error sending audio chunk: {type(e).__name__}: {str(e)[:100]}", flush=True)
                    # Check if this is a fatal connection error
                    error_str = str(e).lower()
                    if any(x in error_str for x in ["connectionclosed", "websocket", "1011"]):
                        print(f"[RealTime] Connection closed by server, stopping audio send", flush=True)
                        self._stop.set()
                        break
                    # Otherwise retry - transient errors might recover
        except Exception as e:
            print(f"[RealTime] Fatal error in audio send loop: {type(e).__name__}: {e}", flush=True)
        finally:
            mic.stop_stream()
            mic.close()
            print(f"[RealTime] Microphone stream closed", flush=True)

    async def _receive(self, session):
        speaker = self._pa.open(
            format=FORMAT, channels=CHANNELS, rate=SPEAKER_RATE,
            output=True, frames_per_buffer=CHUNK,
        )
        print(f"[RealTime] Speaker stream opened for output audio", flush=True)
        
        try:
            while not self._stop.is_set():
                response_count = 0
                print(f"[RealTime] Starting to receive from Gemini Live API...", flush=True)
                
                try:
                    async for response in session.receive():
                        response_count += 1
                        
                        if self._stop.is_set():
                            print(f"[RealTime] Stop signal received, exiting receive loop", flush=True)
                            return
                            
                        sc = response.server_content
                        if not sc:
                            print(f"[RealTime] Response #{response_count} has no server_content, skipping", flush=True)
                            continue
                        
                        # Check for empty response (turn end marker) - just ignore and continue
                        is_empty = not sc.model_turn and not sc.input_transcription and not sc.output_transcription
                        if is_empty:
                            print(f"[RealTime] Response #{response_count} is empty (spacing/keepalive)", flush=True)
                            continue
                        
                        # Play audio from model turn
                        if sc.model_turn and sc.model_turn.parts:
                            for part in sc.model_turn.parts:
                                if part.inline_data:
                                    try:
                                        speaker.write(part.inline_data.data)
                                    except Exception as e:
                                        print(f"[RealTime] Error playing audio: {e}", flush=True)
                            
                            # Model is responding - FIRST TIME this happens, process the pending user message
                            if not self.model_is_responding and self.pending_user_message:
                                self.model_is_responding = True
                                print(f"[RealTime] *** MODEL AUDIO RECEIVED - Processing pending user message ***", flush=True)
                                
                                if self.pending_user_message != self.last_processed_user_message:
                                    print(f"[RealTime] Processing: {self.pending_user_message[:100]}", flush=True)
                                    self._process_learner_signals(self.pending_user_message)
                                    self.last_processed_user_message = self.pending_user_message
                                    self.conversation_history.append({"role": "user", "content": self.pending_user_message})
                        
                        # User transcript (speech-to-text of user's audio)
                        if sc.input_transcription and sc.input_transcription.text.strip():
                            t = sc.input_transcription.text.strip()
                            print(f"[RealTime] User said (fragment): {t}", flush=True)
                            self.extractor.update("user", t)
                            self._on_user(t)
                            self._on_info(self.extractor.get())
                            # Store as pending - will be processed when model starts responding
                            self.pending_user_message = t
                            self.model_is_responding = False  # User is still speaking (or just finished)
                        
                        # Assistant transcript (bot's generated response text)
                        if sc.output_transcription and sc.output_transcription.text:
                            text = sc.output_transcription.text.strip()
                            if text:
                                # Bot is generating output - process pending user message if not already done
                                if not self.model_is_responding and self.pending_user_message:
                                    self.model_is_responding = True
                                    print(f"[RealTime] *** OUTPUT TRANSCRIPTION DETECTED ***", flush=True)
                                    print(f"[RealTime] Processing pending user message: {self.pending_user_message[:100]}", flush=True)
                                    
                                    if self.pending_user_message != self.last_processed_user_message:
                                        self._process_learner_signals(self.pending_user_message)
                                        self.last_processed_user_message = self.pending_user_message
                                        self.conversation_history.append({"role": "user", "content": self.pending_user_message})
                                
                                self._transcript_buffer += text + " "
                                print(f"[RealTime] Bot buffering: {text}", flush=True)
                                
                                # Reset timer to flush buffer after 1000ms of no new input
                                if self._buffer_timer:
                                    self._buffer_timer.cancel()
                                self._buffer_timer = asyncio.create_task(self._flush_transcript_buffer())
                    
                    # Async for ended - the receive generator completed for this batch
                    print(f"[RealTime] Receive batch ended after {response_count} responses", flush=True)
                    print(f"[RealTime] Connection still active, ready for next user input", flush=True)
                    
                except StopAsyncIteration:
                    print(f"[RealTime] Receive generator completed after {response_count} responses", flush=True)
                    
        except asyncio.CancelledError:
            print(f"[RealTime] Receive loop cancelled", flush=True)
        except Exception as e:
            print(f"[RealTime] Error in receive loop: {type(e).__name__}: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            # Flush any remaining buffered transcript
            if self._transcript_buffer.strip():
                await self._flush_transcript_buffer(force=True)
            speaker.stop_stream()
            speaker.close()
            print(f"[RealTime] Speaker stream closed", flush=True)

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
