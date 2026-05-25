"""
File-based Persistence for Learner State
Temporary storage for testing and evaluation.
Saves learner state signals to JSON files when conversations complete.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from models.learner_state_model import LearnerState


class LearnerStatePersistence:
    """
    Persists learner state to temporary JSON files for testing and evaluation.
    
    Storage Structure:
    - temp_learner_states/
      - {session_id}_{timestamp}.json
      - index.json (list of all saved sessions)
    """

    PERSISTENCE_DIR = Path("temp_learner_states")

    def __init__(self):
        """Initialize persistence directory"""
        self.PERSISTENCE_DIR.mkdir(exist_ok=True)

    def save_session_state(
        self,
        learner_state: LearnerState,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Save a learner state to a JSON file.
        
        Args:
            learner_state: The LearnerState to save
            metadata: Optional metadata (conversation duration, message count, etc.)
            
        Returns:
            Path to saved file
        """
        timestamp = datetime.utcnow().isoformat().replace(":", "-")
        filename = f"{learner_state.session_id}_{timestamp}.json"
        filepath = self.PERSISTENCE_DIR / filename

        # Prepare state data
        state_data = {
            "session_id": learner_state.session_id,
            "user_id": learner_state.user_id,
            "saved_at": datetime.utcnow().isoformat(),
            
            # Extracted Signals (all 20 signals)
            "signals": {
                "persona": learner_state.persona,
                "language_preference": learner_state.language_preference,
                "urgency": learner_state.urgency,
                "self_efficacy": learner_state.self_efficacy,
                "motivation": learner_state.motivation,
                "goal_clarity": learner_state.goal_clarity,
                "learning_style": learner_state.learning_style,
                "proof_orientation": learner_state.proof_orientation,
                "commitment_strength": learner_state.commitment_strength,
                "stereotype_threat": learner_state.stereotype_threat,
                # NEW: Educational & Behavioral Signals
                "anxiety_level": learner_state.anxiety_level,
                "comparison_anxiety": learner_state.comparison_anxiety,
                "structure_dependence": learner_state.structure_dependence,
                "abstraction_tolerance": learner_state.abstraction_tolerance,
                "information_density_tolerance": learner_state.information_density_tolerance,
                "confidence_stability": learner_state.confidence_stability,
                "self_directed_learning_ability": learner_state.self_directed_learning_ability,
                "best_explanation_style": learner_state.best_explanation_style,
                "feedback_sensitivity": learner_state.feedback_sensitivity,
                "interview_confidence": learner_state.interview_confidence,
            },
            
            # Conversation Metrics
            "conversation_metrics": {
                "turn_count": learner_state.turn_count,
                "messages_count": learner_state.messages_count,
                "engagement_curve": learner_state.engagement_curve,
            },
            
            # Signal Detection History
            "detected_signals": learner_state.detected_signals,
            
            # Confidence Scores
            "confidence_scores": learner_state.confidence_scores,
            
            # Timestamps
            "timestamp_created": learner_state.timestamp_created.isoformat(),
            "timestamp_updated": learner_state.timestamp_updated.isoformat(),
            
            # Metadata
            "metadata": metadata or {},
        }

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2, ensure_ascii=False)

        # Update index
        self._update_index(learner_state.session_id, filename)

        return str(filepath)

    def load_session_state(self, session_id: str, filename: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Load a saved learner state from file.
        
        Args:
            session_id: Session ID to load
            filename: Optional specific filename. If not provided, loads latest.
            
        Returns:
            Loaded state data or None if not found
        """
        if filename:
            filepath = self.PERSISTENCE_DIR / filename
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        else:
            # Find latest file for this session
            pattern = f"{session_id}_*.json"
            files = sorted(self.PERSISTENCE_DIR.glob(pattern), reverse=True)
            if files:
                with open(files[0], "r", encoding="utf-8") as f:
                    return json.load(f)

        return None

    def list_saved_sessions(self) -> List[Dict[str, Any]]:
        """
        List all saved sessions with summary information.
        
        Returns:
            List of session summaries
        """
        if not (self.PERSISTENCE_DIR / "index.json").exists():
            return []

        with open(self.PERSISTENCE_DIR / "index.json", "r", encoding="utf-8") as f:
            return json.load(f)

    def get_session_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get summary of a specific session.
        
        Returns:
            Session summary or None if not found
        """
        state_data = self.load_session_state(session_id)
        if not state_data:
            return None

        return {
            "session_id": state_data["session_id"],
            "user_id": state_data["user_id"],
            "saved_at": state_data["saved_at"],
            "signals_detected": len(state_data["detected_signals"]),
            "turn_count": state_data["conversation_metrics"]["turn_count"],
            "messages_count": state_data["conversation_metrics"]["messages_count"],
            "key_signals": {
                "persona": state_data["signals"]["persona"],
                "motivation": state_data["signals"]["motivation"],
                "self_efficacy": state_data["signals"]["self_efficacy"],
            },
            "signal_confidence_avg": (
                sum(state_data["confidence_scores"].values()) 
                / len(state_data["confidence_scores"]) 
                if state_data["confidence_scores"] else 0
            ),
        }

    def export_evaluation_report(self, session_id: Optional[str] = None) -> str:
        """
        Generate a human-readable evaluation report of learner state signals.
        
        Args:
            session_id: Specific session to report on. If None, reports on all.
            
        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append("LEARNER STATE EVALUATION REPORT")
        report.append("=" * 80)
        report.append("")

        if session_id:
            state_data = self.load_session_state(session_id)
            if state_data:
                report.extend(self._format_session_report(state_data))
        else:
            # Report on all sessions
            index = self.list_saved_sessions()
            if not index:
                report.append("No saved sessions found.")
            else:
                report.append(f"Total Sessions Saved: {len(index)}\n")
                for session_summary in index:
                    sid = session_summary["session_id"]
                    state_data = self.load_session_state(sid)
                    if state_data:
                        report.extend(self._format_session_report(state_data))
                        report.append("")

        return "\n".join(report)

    def _format_session_report(self, state_data: Dict[str, Any]) -> List[str]:
        """Format a single session for reporting"""
        lines = []
        lines.append(f"Session ID: {state_data['session_id']}")
        lines.append(f"User ID: {state_data['user_id']}")
        lines.append(f"Saved: {state_data['saved_at']}")
        lines.append("")

        # Signals
        lines.append("EXTRACTED SIGNALS:")
        lines.append("-" * 40)
        for signal_name, signal_value in state_data["signals"].items():
            confidence = state_data["confidence_scores"].get(signal_name, 0.0)
            lines.append(f"  {signal_name}: {signal_value} (confidence: {confidence:.2f})")
        lines.append("")

        # Metrics
        lines.append("CONVERSATION METRICS:")
        lines.append("-" * 40)
        metrics = state_data["conversation_metrics"]
        lines.append(f"  Turns: {metrics['turn_count']}")
        lines.append(f"  Messages: {metrics['messages_count']}")
        if metrics["engagement_curve"]:
            avg_engagement = sum(metrics["engagement_curve"].values()) / len(metrics["engagement_curve"])
            lines.append(f"  Avg Engagement: {avg_engagement:.2f}/10")
        lines.append("")

        # Detection History
        if state_data["detected_signals"]:
            lines.append("DETECTION HISTORY:")
            lines.append("-" * 40)
            for signal in state_data["detected_signals"][:10]:  # First 10
                lines.append(f"  - {signal}")
            if len(state_data["detected_signals"]) > 10:
                lines.append(f"  ... and {len(state_data['detected_signals']) - 10} more")
            lines.append("")

        return lines

    def _update_index(self, session_id: str, filename: str):
        """Update the index.json with new session"""
        index_path = self.PERSISTENCE_DIR / "index.json"

        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
        else:
            index = []

        # Check if session already in index
        session_in_index = any(s["session_id"] == session_id for s in index)
        if not session_in_index:
            index.append({
                "session_id": session_id,
                "filename": filename,
                "saved_at": datetime.utcnow().isoformat(),
            })

        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)

    def cleanup_old_sessions(self, keep_count: int = 50):
        """
        Clean up old session files, keeping only the most recent.
        
        Args:
            keep_count: Number of most recent sessions to keep
        """
        files = sorted(
            self.PERSISTENCE_DIR.glob("*.json"),
            key=os.path.getmtime,
            reverse=True
        )

        # Don't delete index.json
        files = [f for f in files if f.name != "index.json"]

        if len(files) > keep_count:
            for old_file in files[keep_count:]:
                old_file.unlink()
                print(f"Deleted old session: {old_file.name}")
