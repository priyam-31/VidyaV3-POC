"""
Learner State Model
Pydantic models for learner profiling and state management
"""

from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class LearnerState(BaseModel):
    """
    Core learner intelligence state.
    Keeps only the most important signals for context injection.
    Designed to be injected into prompts, not stored in vector DB initially.
    """

    # Core Demographics
    session_id: str = Field(..., description="Unique session identifier")
    user_id: Optional[str] = Field(None, description="Optional user ID for multi-session tracking")
    timestamp_created: datetime = Field(default_factory=datetime.utcnow)
    timestamp_updated: datetime = Field(default_factory=datetime.utcnow)

    # Persona Classification
    persona: Literal["low_wage", "high_wage", "unknown"] = Field(
        default="unknown",
        description="Primary persona classification"
    )

    # Language & Communication
    language_preference: Literal["english", "hindi", "hinglish", "unknown"] = Field(
        default="unknown",
        description="Preferred communication language"
    )

    # Psychological Signals
    urgency: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Perceived urgency or time pressure"
    )

    self_efficacy: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Confidence in ability to succeed (Bandura)"
    )

    motivation: Literal[
        "placement_pressure",
        "career_growth",
        "curiosity",
        "financial_necessity",
        "social_proof",
        "unknown"
    ] = Field(
        default="unknown",
        description="Primary motivation type"
    )

    goal_clarity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Clarity of learning goals and desired outcomes"
    )

    learning_style: Literal[
        "example_driven",
        "theory_first",
        "project_based",
        "mixed",
        "unknown"
    ] = Field(
        default="unknown",
        description="Preferred learning approach"
    )

    proof_orientation: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Need for evidence-based reasoning vs emotional persuasion"
    )

    commitment_strength: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Strength of commitment to learning/program"
    )

    stereotype_threat: bool = Field(
        default=False,
        description="Is user experiencing stereotype threat or imposter syndrome?"
    )

    # New Educational & Behavioral Signals
    anxiety_level: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Overall anxiety level in learning context"
    )

    comparison_anxiety: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Anxiety triggered by comparing self to peers/others"
    )

    structure_dependence: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Need for external structure (syllabus, roadmap) vs self-directed"
    )

    abstraction_tolerance: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Comfort with abstract concepts vs need for concrete examples"
    )

    information_density_tolerance: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Can handle info-dense explanations or needs simpler breakdowns"
    )

    confidence_stability: Literal["fragile", "moderate", "stable", "unknown"] = Field(
        default="unknown",
        description="How stable confidence is (fragile=easily shaken, stable=resilient to setbacks)"
    )

    self_directed_learning_ability: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Ability to learn independently without constant guidance"
    )

    best_explanation_style: Literal[
        "analogy_based",
        "visual",
        "stepwise",
        "practical",
        "theory_first",
        "code_first",
        "unknown"
    ] = Field(
        default="unknown",
        description="Most effective explanation style for this learner"
    )

    feedback_sensitivity: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="How receptive learner is to constructive feedback"
    )

    interview_confidence: Literal["low", "medium", "high", "unknown"] = Field(
        default="unknown",
        description="Confidence in interview settings (relevant for service engineers)"
    )

    # Scenario-Specific Context (NOT generic ICP - actual user situation)
    current_company: str = Field(
        default="unknown",
        description="Company the user currently works at (e.g., 'TCS', 'Infosys', 'Amazon')"
    )

    college_name: str = Field(
        default="unknown",
        description="College the user attends (e.g., 'IIT Delhi', 'Tier-2 college')"
    )

    specific_pain_point: str = Field(
        default="unknown",
        description="User's specific pain point (e.g., 'placement crisis', 'stuck in appraisal', 'interview rejections')"
    )

    specific_goal: str = Field(
        default="unknown",
        description="User's specific goal (e.g., 'switch to Amazon', 'product company engineer', 'senior role at current company')"
    )

    current_role_title: str = Field(
        default="unknown",
        description="Current job title if employed (e.g., 'Service Engineer', 'Senior Developer')"
    )

    years_in_current_role: float = Field(
        default=0.0,
        description="How long user has been in current role"
    )

    # Session Management
    session_status: Literal["active", "closed", "paused"] = Field(
        default="active",
        description="Current session status (active | closed | paused)"
    )

    user_showed_commitment: bool = Field(
        default=False,
        description="Has user shown clear commitment/readiness signals?"
    )

    session_closure_triggered: bool = Field(
        default=False,
        description="Has AI triggered session closure with 'let's get started' or similar phrase?"
    )

    enforce_language_purity: bool = Field(
        default=True,
        description="Should strictly enforce single language after user choice?"
    )

    detected_language_mixing_violations: int = Field(
        default=0,
        description="Count of language mixing violations detected"
    )

    # Signals Evolution (for detecting shifts)
    engagement_curve: Dict[int, float] = Field(
        default_factory=dict,
        description="Response quality per turn (0-10 scale)"
    )

    # Conversation Context
    turn_count: int = Field(default=0, description="Number of conversation turns")
    messages_count: int = Field(default=0, description="Total messages exchanged")

    # Confidence Scores (optional, for future ML model)
    confidence_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Confidence scores for each signal (0-1 scale)"
    )

    # Metadata for context
    detected_signals: list[str] = Field(
        default_factory=list,
        description="List of signals explicitly detected this turn"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_12345",
                "persona": "low_wage",
                "language_preference": "hinglish",
                "urgency": "high",
                "self_efficacy": "low",
                "motivation": "placement_pressure",
                "goal_clarity": "medium",
                "learning_style": "example_driven",
                "proof_orientation": "medium",
                "commitment_strength": "high",
                "stereotype_threat": True,
                "turn_count": 5,
                "messages_count": 10,
            }
        }

    def to_compact_context(self) -> str:
        """
        Convert learner state to compact prompt context (NOT full JSON).
        This is what gets injected into the main LLM prompt.
        """
        lines = []

        # Only inject HIGH-IMPACT signals
        if self.persona != "unknown":
            lines.append(f"- Learner Type: {self.persona.replace('_', ' ').title()}")

        if self.urgency == "high":
            lines.append(f"- Urgency: High (time-sensitive, wants quick results)")

        if self.self_efficacy == "low":
            lines.append(f"- Confidence: Building (avoid overwhelming, affirm foundations)")

        if self.stereotype_threat:
            lines.append(f"- Concern: Possible imposter syndrome (use concrete examples, avoid generic reassurance)")

        if self.motivation != "unknown":
            lines.append(f"- Main Driver: {self.motivation.replace('_', ' ').title()}")

        if self.learning_style == "example_driven":
            lines.append(f"- Prefers: Real-world examples over theory")

        if self.proof_orientation == "high":
            lines.append(f"- Approach: Evidence-based (data, examples, outcomes)")

        if self.language_preference in ["hindi", "hinglish"]:
            lines.append(f"- Language: Use {self.language_preference}")

        if self.commitment_strength == "high":
            lines.append(f"- Engagement: High (can discuss deeper topics, move toward action)")

        # NEW: Inject impactful behavioral signals
        if self.anxiety_level == "high":
            lines.append(f"- Mental State: High anxiety (be reassuring, avoid adding pressure)")

        if self.comparison_anxiety == "high":
            lines.append(f"- Concern: Comparison anxiety (focus on personal progress, not peer comparison)")

        if self.structure_dependence == "high":
            lines.append(f"- Need: Clear structure and roadmap (provide step-by-step guidance)")

        if self.abstraction_tolerance == "low":
            lines.append(f"- Style: Needs concrete examples (avoid abstract theory)")

        if self.information_density_tolerance == "low":
            lines.append(f"- Pace: Simpler breakdowns (avoid info overload)")

        if self.confidence_stability == "fragile":
            lines.append(f"- Resilience: Fragile confidence (frequent affirmation, normalize struggles)")

        if self.best_explanation_style != "unknown":
            style_name = self.best_explanation_style.replace('_', ' ').title()
            lines.append(f"- Best Teaching: {style_name} explanations")

        if self.feedback_sensitivity == "high":
            lines.append(f"- Feedback: Sensitive (frame constructively, focus on growth)")

        if self.interview_confidence == "low":
            lines.append(f"- Interview Skills: Building confidence (practice with encouragement)")

        if not lines:
            return "No specific learner adaptations detected yet."

        return "Learner Adaptations:\n" + "\n".join(lines)

        if not lines:
            return "No specific learner adaptations detected yet."

        return "Learner Adaptations:\n" + "\n".join(lines)

    def to_signal_summary(self) -> Dict[str, Any]:
        """
        Returns only the current signal state (without JSON bloat).
        Useful for debugging and logging.
        """
        return {
            "persona": self.persona,
            "language": self.language_preference,
            "urgency": self.urgency,
            "self_efficacy": self.self_efficacy,
            "motivation": self.motivation,
            "goal_clarity": self.goal_clarity,
            "learning_style": self.learning_style,
            "proof_orientation": self.proof_orientation,
            "commitment_strength": self.commitment_strength,
            "stereotype_threat": self.stereotype_threat,
            "anxiety_level": self.anxiety_level,
            "comparison_anxiety": self.comparison_anxiety,
            "structure_dependence": self.structure_dependence,
            "abstraction_tolerance": self.abstraction_tolerance,
            "information_density_tolerance": self.information_density_tolerance,
            "confidence_stability": self.confidence_stability,
            "self_directed_learning_ability": self.self_directed_learning_ability,
            "best_explanation_style": self.best_explanation_style,
            "feedback_sensitivity": self.feedback_sensitivity,
            "interview_confidence": self.interview_confidence,
            "turn_count": self.turn_count,
        }


class SignalExtractionResult(BaseModel):
    """Result from signal extraction pipeline"""

    extracted_signals: Dict[str, Any] = Field(
        description="Dictionary of extracted signals"
    )
    extraction_method: Literal["rule_based", "llm_based", "hybrid"] = Field(
        description="Which extraction method was used"
    )
    confidence: float = Field(
        ge=0, le=1,
        description="Overall confidence in extraction (0-1)"
    )
    per_signal_confidence: Dict[str, float] = Field(
        default_factory=dict,
        description="Confidence score for each signal (0-1 scale)"
    )
    reasoning: Optional[str] = Field(
        None,
        description="Human-readable explanation of what was extracted and why"
    )
    raw_evidence: Optional[str] = Field(
        None,
        description="Raw quote or evidence from user message"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "extracted_signals": {
                    "persona": "low_wage",
                    "urgency": "high",
                    "self_efficacy": "low"
                },
                "extraction_method": "hybrid",
                "confidence": 0.85,
                "per_signal_confidence": {
                    "persona": 0.9,
                    "urgency": 0.85,
                    "self_efficacy": 0.7
                },
                "reasoning": "User mentioned 'final semester' (college context) and 'need job before summer' (high urgency). Used words like 'not sure if I can' suggesting lower self-efficacy.",
                "raw_evidence": "I'm in my final semester and need to land a job before summer. Not sure if I can..."
            }
        }


class PromptContext(BaseModel):
    """Context to be injected into main conversational prompt"""

    learner_summary: str = Field(
        description="Compact learner adaptation summary"
    )
    adaptation_priorities: list[str] = Field(
        description="Top 3-5 adaptation priorities for this turn"
    )
    tone_guidance: str = Field(
        description="Brief guidance on conversation tone"
    )
    avoid_patterns: list[str] = Field(
        default_factory=list,
        description="Patterns to avoid based on learner state"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "learner_summary": "Learner Type: College Student\nUrgency: High\nConfidence: Building (avoid overwhelming)\nMain Driver: Placement Pressure",
                "adaptation_priorities": [
                    "Reduce intimidation and complexity",
                    "Use concrete, relatable examples",
                    "Move toward actionable steps",
                    "Build confidence gradually"
                ],
                "tone_guidance": "Supportive but practical. Acknowledge pressure without adding more. Show achievable path.",
                "avoid_patterns": [
                    "Generic motivation speeches",
                    "Overwhelming roadmaps",
                    "Comparison to others"
                ]
            }
        }
