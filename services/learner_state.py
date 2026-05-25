"""
Learner State Manager
Handles in-memory storage, initialization, and updates of learner state.
Future-compatible with Pinecone/vector DB.
"""

from typing import Optional, Dict, Any
from datetime import datetime
from models.learner_state_model import LearnerState, SignalExtractionResult


class LearnerStateManager:
    """
    Manages learner state in temporary in-memory storage.
    Can be extended to persist to database/vector store later.
    """

    def __init__(self):
        """Initialize in-memory session storage"""
        self.sessions: Dict[str, LearnerState] = {}

    def initialize_session(self, session_id: str, user_id: Optional[str] = None) -> LearnerState:
        """
        Initialize a new learner state for a session.
        
        Args:
            session_id: Unique session identifier
            user_id: Optional user ID for multi-session tracking
            
        Returns:
            Newly initialized LearnerState
        """
        learner_state = LearnerState(
            session_id=session_id,
            user_id=user_id,
        )
        self.sessions[session_id] = learner_state
        return learner_state

    def get_learner_state(self, session_id: str) -> Optional[LearnerState]:
        """Get learner state for a session"""
        return self.sessions.get(session_id)

    def get_or_initialize(self, session_id: str, user_id: Optional[str] = None) -> LearnerState:
        """Get existing state or initialize new one"""
        if session_id in self.sessions:
            return self.sessions[session_id]
        return self.initialize_session(session_id, user_id)

    def update_signal(
        self,
        session_id: str,
        signal_name: str,
        signal_value: Any,
        confidence: float = 0.8,
        replace_existing: bool = True,
    ) -> Optional[LearnerState]:
        """
        Update a single signal in learner state.
        
        Args:
            session_id: Session to update
            signal_name: Name of signal (must be valid LearnerState field)
            signal_value: Value to set
            confidence: Confidence score for this signal (0-1)
            replace_existing: If True, overwrite existing value. If False, only set if currently unknown.
            
        Returns:
            Updated LearnerState or None if session not found
        """
        if session_id not in self.sessions:
            return None

        learner_state = self.sessions[session_id]

        # Don't overwrite higher-confidence existing signals
        if not replace_existing:
            current_value = getattr(learner_state, signal_name, None)
            if current_value and current_value != "unknown":
                return learner_state

        # Update the signal
        setattr(learner_state, signal_name, signal_value)
        learner_state.timestamp_updated = datetime.utcnow()

        # Store confidence score
        learner_state.confidence_scores[signal_name] = confidence

        return learner_state

    def update_from_extraction(
        self,
        session_id: str,
        extraction_result: SignalExtractionResult,
        replace_low_confidence: bool = False,
    ) -> Optional[LearnerState]:
        """
        Update learner state from an extraction result.
        Updates signals based on per-signal confidence when available.
        Uses overall confidence as fallback.
        
        Args:
            session_id: Session to update
            extraction_result: Result from signal extraction
            replace_low_confidence: If True, replace even low-confidence signals
            
        Returns:
            Updated LearnerState or None if session not found
        """
        if session_id not in self.sessions:
            print(f"[LearnerState] Session {session_id} not found", flush=True)
            return None

        learner_state = self.sessions[session_id]
        # Lower threshold for rule-based extraction (more lenient)
        min_confidence = 0.3 if replace_low_confidence else 0.4
        updated_any = False
        
        print(f"[LearnerState] update_from_extraction: {len(extraction_result.extracted_signals)} signals to process", flush=True)

        # Update each extracted signal
        for signal_name, signal_value in extraction_result.extracted_signals.items():
            # Check if it's a valid field
            if not hasattr(learner_state, signal_name):
                print(f"[LearnerState] Skipping invalid signal: {signal_name}", flush=True)
                continue

            # Get per-signal confidence (or fall back to overall confidence)
            signal_confidence = extraction_result.per_signal_confidence.get(
                signal_name, 
                extraction_result.confidence
            )

            # Skip if confidence is below threshold (unless replacing low confidence)
            if signal_confidence < min_confidence and not replace_low_confidence:
                print(f"[LearnerState] Skipping {signal_name} - confidence {signal_confidence} < {min_confidence}", flush=True)
                continue

            # Get current value
            current_value = getattr(learner_state, signal_name, None)

            # Only update signal value if current is "unknown" or we have higher confidence
            current_confidence = learner_state.confidence_scores.get(signal_name, 0)
            if current_value == "unknown" or signal_confidence > current_confidence:
                setattr(learner_state, signal_name, signal_value)
                updated_any = True
                print(f"[LearnerState] Updated {signal_name}={signal_value} (confidence={signal_confidence})", flush=True)
            
            # ALWAYS store confidence score for detected signals (regardless of whether value changed)
            learner_state.confidence_scores[signal_name] = signal_confidence
            # Track this signal as detected (avoid duplicates)
            if signal_name not in learner_state.detected_signals:
                learner_state.detected_signals.append(signal_name)
                print(f"[LearnerState] Added to detected_signals: {signal_name}", flush=True)
        
        print(f"[LearnerState] Final detected_signals: {learner_state.detected_signals}", flush=True)
        print(f"[LearnerState] Final confidence_scores: {learner_state.confidence_scores}", flush=True)
        
        if updated_any:
            learner_state.timestamp_updated = datetime.utcnow()

        return learner_state

    def update_conversation_turn(
        self,
        session_id: str,
        engagement_score: Optional[float] = None,
    ) -> Optional[LearnerState]:
        """
        Update conversation turn metadata.
        Called after each user message is processed.
        This is the authoritative turn counter (NOT st.session_state.turn_count which counts fragments).
        
        Args:
            session_id: Session to update
            engagement_score: Optional engagement quality score (0-10)
            
        Returns:
            Updated LearnerState
        """
        if session_id not in self.sessions:
            return None

        learner_state = self.sessions[session_id]
        learner_state.turn_count += 1

        # Track engagement curve with actual turn count
        if engagement_score is not None:
            learner_state.engagement_curve[learner_state.turn_count] = engagement_score

        return learner_state

    def update_message_count(self, session_id: str) -> Optional[LearnerState]:
        """Increment message count"""
        if session_id not in self.sessions:
            return None

        learner_state = self.sessions[session_id]
        learner_state.messages_count += 1
        return learner_state

    def reset_session(self, session_id: str) -> bool:
        """Clear a session's state"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a compact summary of learner state for debugging"""
        learner_state = self.get_learner_state(session_id)
        if not learner_state:
            return None

        return {
            "session_id": session_id,
            "signals": learner_state.to_signal_summary(),
            "turn_count": learner_state.turn_count,
            "messages_count": learner_state.messages_count,
            "engagement_curve": learner_state.engagement_curve,
            "detected_signals": learner_state.detected_signals[-5:],  # Last 5
            "timestamp_updated": learner_state.timestamp_updated.isoformat(),
        }

    def get_all_sessions_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary of all active sessions"""
        return {
            session_id: self.get_session_summary(session_id)
            for session_id in self.sessions.keys()
        }
