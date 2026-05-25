"""
Enhanced LLM-Based Signal Extraction (v2)
Primary extraction method with comprehensive signal detection and per-signal confidence.
Falls back to rule-based extraction if LLM fails.
"""

import json
import os
from typing import Optional, Dict, Any, List
import google.generativeai as genai
from models.learner_state_model import SignalExtractionResult


class LLMSignalExtractorV2:
    """
    Primary LLM-based signal extraction with:
    - Comprehensive signal detection (all learner state signals)
    - Per-signal confidence scoring based on evidence strength
    - Structured JSON output with reasoning per signal
    - Fallback to rule-based extraction on failure
    - Better error handling and logging
    """

    # Confidence multipliers based on evidence types
    CONFIDENCE_MULTIPLIERS = {
        "explicit_statement": 0.95,      # Direct quote from user
        "strong_inference": 0.85,        # Clear inference from context
        "moderate_inference": 0.70,      # Reasonable inference but some ambiguity
        "weak_inference": 0.55,          # Speculative inference
        "default": 0.50,                 # No evidence, just guessing
    }

    EXTRACTION_PROMPT_TEMPLATE = """You are an expert psychological profiler analyzing a learner's message.
Your task: Extract ALL psychological and contextual signals that predict learning success.

=== CURRENT CONTEXT ===
Learner State (if available):
{current_state}

Previous Conversation (last 2-3 exchanges):
{conversation_context}

=== USER'S LATEST MESSAGE ===
"{user_message}"

=== YOUR TASK ===
Analyze this message and extract ALL of these signals (return null if not detectable):

1. **persona** (low_wage | high_wage | unknown)
   - College student: mentions year, semester, placement, campus, college/university name
   - Service engineer: mentions specific IT company, years of experience, career advancement
   
2. **language_preference** (english | hindi | hinglish | unknown)
   - english: Requests to speak/teach in English
   - hindi: Uses Devanagari script, requests Hindi
   - hinglish: Mixes Hindi + English (yaar, bhai, arre)

3. **urgency** (low | medium | high | unknown)
   - high: Mentions deadlines, "ASAP", "before month/week", placement season, need job soon
   - low: "no rush", "take time", "just exploring"
   - medium: In-between, no clear time pressure

4. **self_efficacy** (low | medium | high | unknown)
   - low: "can't do it", "don't know", "scared", "behind others", "no experience"
   - high: "confident", "done this before", "have skills", "basics are easy"
   - medium: Neutral, neither confident nor doubtful

5. **motivation** (placement_pressure | career_growth | curiosity | financial_necessity | social_proof | unknown)
   - placement_pressure: Mentions placement season, job hunting, being left behind
   - career_growth: Mentions senior role, advancement, next level
   - curiosity: "interested", "want to learn", "exploring"
   - financial_necessity: Mentions salary, package, money, LPA
   - social_proof: "friends doing it", "everyone else", "compared to others"

6. **goal_clarity** (low | medium | high | unknown)
   - high: Specific role, company type, or salary target mentioned
   - low: Vague, "just want to get a job", "learn something"
   - medium: Some goals but not crystal clear

7. **learning_style** (example_driven | theory_first | project_based | mixed | unknown)
   - example_driven: "show me", "real-world examples", "how to", "case studies"
   - theory_first: "why?", "understand concept", "deep dive", "architecture"
   - project_based: "build", "make", "hands-on", "by doing"
   - mixed: Shows interest in multiple approaches

8. **proof_orientation** (low | medium | high | unknown)
   - high: Asks for data, examples, evidence, outcomes
   - low: Accepts general reassurance, focuses on feeling/vibes
   - medium: Balanced approach

9. **commitment_strength** (low | medium | high | unknown)
   - high: Willing to put in work, shows persistence, asks deep questions
   - low: Casual, "just seeing", minimal engagement
   - medium: Moderate engagement

10. **stereotype_threat** (true | false)
    - true: Signs of self-doubt despite competence, imposter syndrome, "am I good enough?"
    - false: No such concerns

11. **anxiety_level** (low | medium | high | unknown)
    - high: "scared", "anxious", "nervous", "overwhelmed", "losing sleep"
    - low: "calm", "confident", "relaxed", "comfortable"
    - medium: Neutral or mixed anxiety signals

12. **comparison_anxiety** (low | medium | high | unknown)
    - high: Mentions "compared to others", "everyone else", "behind", "lagging", "my peers"
    - low: "focus on myself", "my own pace", "don't care what others think"
    - medium: Neutral or mixed

13. **structure_dependence** (low | medium | high | unknown)
    - high: Wants roadmap, syllabus, step-by-step guidance, structure, clear plan
    - low: Prefers independent learning, self-directed, "figure it out myself"
    - medium: Balanced preference

14. **abstraction_tolerance** (low | medium | high | unknown)
    - high: Interested in concepts, theory, architecture, why things work
    - low: Prefers concrete examples, "show me", practical, real-world
    - medium: Balanced approach

15. **information_density_tolerance** (low | medium | high | unknown)
    - high: Can handle comprehensive, detailed, information-dense explanations
    - low: Needs simpler breakdowns, small pieces, one thing at a time
    - medium: Balanced preference

16. **confidence_stability** (fragile | moderate | stable | unknown)
    - fragile: "one mistake ruins it", easily discouraged, gives up on small failures
    - stable: "bounce back", "keep trying", learns from mistakes, resilient
    - moderate: In-between resilience

17. **self_directed_learning_ability** (low | medium | high | unknown)
    - high: "self-learner", "independent", uses resources, explores on own
    - low: "need guidance", "tell me how", depends on others, gets lost easily
    - medium: Balanced independence

18. **best_explanation_style** (analogy_based | visual | stepwise | practical | theory_first | code_first | unknown)
    - analogy_based: Likes comparisons, "like when", metaphors
    - visual: Wants diagrams, charts, visual representations
    - stepwise: Prefers step-by-step, sequential breakdown
    - practical: Wants real-world examples, use cases
    - theory_first: Wants concepts before implementation
    - code_first: Wants code examples, hands-on coding

19. **feedback_sensitivity** (low | medium | high | unknown)
    - high: Defensive, easily hurt by criticism, "my feelings", sensitive feedback
    - low: "appreciate feedback", "give me honest feedback", open to critique
    - medium: Balanced sensitivity

20. **interview_confidence** (low | medium | high | unknown)
    - high: "done interviews", "experienced", "confident speaking"
    - low: "interview anxiety", "tongue-tied", "never interviewed", "get nervous"
    - medium: Neutral or mixed

=== OUTPUT FORMAT ===
Return a VALID JSON object (no markdown, no code blocks) with:
{{
  "persona": "value or null",
  "language_preference": "value or null",
  "urgency": "value or null",
  "self_efficacy": "value or null",
  "motivation": "value or null",
  "goal_clarity": "value or null",
  "learning_style": "value or null",
  "proof_orientation": "value or null",
  "commitment_strength": "value or null",
  "stereotype_threat": true/false/null,
  "anxiety_level": "low|medium|high or null",
  "comparison_anxiety": "low|medium|high or null",
  "structure_dependence": "low|medium|high or null",
  "abstraction_tolerance": "low|medium|high or null",
  "information_density_tolerance": "low|medium|high or null",
  "confidence_stability": "fragile|moderate|stable or null",
  "self_directed_learning_ability": "low|medium|high or null",
  "best_explanation_style": "analogy_based|visual|stepwise|practical|theory_first|code_first or null",
  "feedback_sensitivity": "low|medium|high or null",
  "interview_confidence": "low|medium|high or null",
  
  "per_signal_confidence": {{
    "persona": 0.0-1.0,
    "language_preference": 0.0-1.0,
    ... (confidence score for EACH of the 20 signals)
  }},
  
  "evidence": {{
    "persona": "Brief evidence or null",
    "language_preference": "Brief evidence or null",
    ... (evidence for EACH of the 20 signals)
  }}
}}

=== IMPORTANT RULES ===
1. Return null for signals with insufficient evidence
2. Base confidence on evidence strength (0.95=explicit, 0.85=strong inference, 0.70=moderate, 0.55=weak, 0.50=guessing)
3. Return ONLY valid JSON - no explanations, no markdown
4. Include confidence scores for ALL 20 signals (even null ones get 0.0-0.3)
5. Be conservative with high confidence (0.8+) - only for explicit or very strong evidence
6. NEW signals (anxiety through interview_confidence) infer from: emotional wording, confidence patterns, communication style, learning preferences, behavioral cues, interview fears, structure seeking, explanation requests
7. Only return NEW signal values when confidence is HIGH, otherwise return null
"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini client"""
        if api_key:
            genai.configure(api_key=api_key)
        elif os.getenv("GEMINI_API_KEY"):
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        else:
            raise ValueError(
                "No GEMINI_API_KEY provided. Set via parameter or environment variable."
            )

        # Try latest model first, fallback to alternatives
        try:
            self.client = genai.GenerativeModel("gemini-2.0-flash")
            self.model_name = "gemini-2.0-flash"
        except Exception:
            try:
                self.client = genai.GenerativeModel("gemini-1.5-flash")
                self.model_name = "gemini-1.5-flash"
            except Exception:
                # Fallback to pro if flash unavailable
                self.client = genai.GenerativeModel("gemini-pro")
                self.model_name = "gemini-pro"

    def _format_conversation_context(
        self, conversation_history: Optional[List[Dict[str, str]]], max_messages: int = 3
    ) -> str:
        """Format last few messages for context"""
        if not conversation_history or len(conversation_history) == 0:
            return "[No previous context]"

        # Take last N message pairs (user + assistant)
        context_messages = conversation_history[-(max_messages * 2) :]

        formatted = []
        for msg in context_messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")[:150]  # Truncate for brevity
            formatted.append(f"{role}: {content}")

        return "\n".join(formatted) if formatted else "[No previous context]"

    def _format_current_state(self, learner_state: Optional[Dict[str, Any]]) -> str:
        """Format current learner state for context"""
        if not learner_state:
            return "[New session - no learner state yet]"

        lines = []
        
        # Only include non-unknown, non-default signals
        for key, value in learner_state.items():
            if key.startswith("_"):  # Skip private fields
                continue
            if value and value not in ["unknown", "medium"]:  # Skip defaults
                # Prettify key names
                pretty_key = key.replace("_", " ").title()
                lines.append(f"- {pretty_key}: {value}")

        return "\n".join(lines) if lines else "[Minimal learner state]"

    def _calculate_confidence_for_signal(
        self,
        evidence_strength: str,
        signal_name: str,
        signal_value: Any,
        raw_confidence: float,
    ) -> float:
        """
        Calculate final confidence score for a signal.
        
        Args:
            evidence_strength: "explicit_statement", "strong_inference", etc.
            signal_name: Name of the signal
            signal_value: The extracted value
            raw_confidence: Raw confidence from LLM
            
        Returns:
            Final confidence score (0-1)
        """
        if signal_value is None:
            # Null signals get very low confidence
            return raw_confidence if raw_confidence > 0 else 0.1
        
        # Use multiplier based on evidence type
        multiplier = self.CONFIDENCE_MULTIPLIERS.get(evidence_strength, 0.50)
        
        # Adjust based on signal value commonality
        # Boolean signals with True get lower confidence than with False
        if signal_name == "stereotype_threat" and signal_value is True:
            multiplier *= 0.85  # Less confident about negative traits
        
        final_confidence = min(multiplier * raw_confidence, 1.0)
        return round(final_confidence, 2)

    def extract(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_learner_state: Optional[Dict[str, Any]] = None,
    ) -> SignalExtractionResult:
        """
        Extract all psychological signals using Gemini.
        
        Args:
            user_message: Latest message from user
            conversation_history: Previous conversation messages for context
            current_learner_state: Current learner state (dict)
            
        Returns:
            SignalExtractionResult with extracted signals and per-signal confidence
        """
        print(f"[LLMSignalExtractorV2] Starting extraction for: {user_message[:80]}", flush=True)
        
        # Format context
        context = self._format_conversation_context(conversation_history)
        state = self._format_current_state(current_learner_state)

        # Build prompt
        prompt = self.EXTRACTION_PROMPT_TEMPLATE.format(
            current_state=state,
            user_message=user_message,
            conversation_context=context,
        )

        try:
            # Call Gemini with low temperature for consistency
            response = self.client.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    top_p=0.9,
                    top_k=30,
                ),
            )

            response_text = response.text.strip()
            print(f"[LLMSignalExtractorV2] Gemini response received ({len(response_text)} chars)", flush=True)

            # Clean markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            # Parse JSON
            extracted = json.loads(response_text)
            print(f"[LLMSignalExtractorV2] JSON parsed successfully", flush=True)

            # Extract signals (only non-null values)
            signals = {}
            per_signal_confidence = {}
            evidence = extracted.get("evidence", {})

            for key, value in extracted.items():
                if key in ["per_signal_confidence", "evidence"]:
                    continue

                # Get per-signal confidence from LLM or calculate it
                llm_confidence = extracted.get("per_signal_confidence", {}).get(key, 0.5)
                signal_evidence = evidence.get(key, "")

                # Determine evidence strength
                if value is None:
                    evidence_strength = "default"
                    final_confidence = 0.15  # Very low for null signals
                elif llm_confidence >= 0.85:
                    evidence_strength = "explicit_statement"
                    final_confidence = self._calculate_confidence_for_signal(
                        evidence_strength, key, value, llm_confidence
                    )
                elif llm_confidence >= 0.70:
                    evidence_strength = "strong_inference"
                    final_confidence = self._calculate_confidence_for_signal(
                        evidence_strength, key, value, llm_confidence
                    )
                elif llm_confidence >= 0.55:
                    evidence_strength = "moderate_inference"
                    final_confidence = self._calculate_confidence_for_signal(
                        evidence_strength, key, value, llm_confidence
                    )
                else:
                    evidence_strength = "weak_inference"
                    final_confidence = self._calculate_confidence_for_signal(
                        evidence_strength, key, value, llm_confidence
                    )

                # Always store confidence (even for null)
                per_signal_confidence[key] = final_confidence

                # Only add to signals if not null
                if value is not None:
                    signals[key] = value
                    print(
                        f"[LLMSignalExtractorV2] Signal: {key}={value} "
                        f"(confidence={final_confidence}, evidence={signal_evidence[:50]})",
                        flush=True
                    )

            # Calculate overall confidence as average of non-zero confidences
            non_zero_confidences = [c for c in per_signal_confidence.values() if c > 0.1]
            overall_confidence = (
                round(sum(non_zero_confidences) / len(non_zero_confidences), 2)
                if non_zero_confidences
                else 0.5
            )

            print(f"[LLMSignalExtractorV2] Extraction complete: {len(signals)} signals, "
                  f"overall_confidence={overall_confidence}", flush=True)

            return SignalExtractionResult(
                extracted_signals=signals,
                extraction_method="llm_based",
                confidence=overall_confidence,
                per_signal_confidence=per_signal_confidence,
                reasoning="LLM-based comprehensive signal extraction with per-signal confidence",
                raw_evidence=user_message[:100] + "..." if len(user_message) > 100 else user_message,
            )

        except json.JSONDecodeError as e:
            print(f"[LLMSignalExtractorV2] JSON parse failed: {str(e)}", flush=True)
            print(f"[LLMSignalExtractorV2] Raw response: {response_text[:200]}", flush=True)
            return self._create_fallback_result(
                user_message,
                reason=f"JSON parsing failed: {str(e)}"
            )
        except Exception as e:
            print(f"[LLMSignalExtractorV2] LLM extraction error: {str(e)}", flush=True)
            return self._create_fallback_result(
                user_message,
                reason=f"LLM error: {str(e)}"
            )

    def _create_fallback_result(
        self,
        user_message: str,
        reason: str = "Unknown error"
    ) -> SignalExtractionResult:
        """
        Create a fallback result when LLM extraction fails.
        This triggers the rule-based extractor to take over.
        """
        print(f"[LLMSignalExtractorV2] Fallback result (reason: {reason})", flush=True)
        return SignalExtractionResult(
            extracted_signals={},
            extraction_method="llm_based",
            confidence=0.0,
            per_signal_confidence={},
            reasoning=f"LLM extraction failed ({reason}) - will fall back to rule-based",
            raw_evidence=user_message[:100],
        )

    def extract_engagement_quality(self, user_message: str) -> float:
        """
        Quick scoring of message engagement quality (0-10).
        Used for engagement_curve tracking.
        """
        prompt = f"""Rate the engagement quality and depth of thinking in this message on a scale of 0-10.

0-2: One-word answer, minimal effort
3-4: Basic response, little elaboration
5-6: Adequate response with some detail
7-8: Thoughtful, specific examples or reasoning
9-10: Deeply engaged, nuanced thinking, multiple perspectives

Message: "{user_message}"

Return ONLY a single integer (0-10)."""

        try:
            response = self.client.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=0.3),
            )
            score = int(response.text.strip())
            return min(max(score, 0), 10)  # Clamp to 0-10
        except Exception as e:
            print(f"[LLMSignalExtractorV2] Engagement scoring failed: {e}", flush=True)
            return 5.0  # Default to medium if parsing fails
