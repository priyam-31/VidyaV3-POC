"""
Signal Extraction Orchestrator (v2)
LLM-first signal extraction with rule-based fallback.
Provides comprehensive signal detection with per-signal confidence scores.
"""

from typing import Dict, Any, Optional, List
from models.learner_state_model import SignalExtractionResult, LearnerState
from services.rule_extractor import RuleBasedExtractor
from services.llm_signal_extractor_v2 import LLMSignalExtractorV2
from services.adaptation_engine import AdaptationEngine


class SignalExtractionOrchestrator:
    """
    LLM-first signal extraction orchestrator.
    
    Strategy:
    1. Try LLM extraction (comprehensive, all signals with confidence)
    2. If LLM fails, fallback to rule-based extraction
    3. Never use only rule-based by default
    
    This ensures:
    - Maximum signal coverage
    - Better confidence scoring
    - More nuanced understanding of learner psychology
    """

    def __init__(self, llm_api_key: Optional[str] = None):
        """
        Initialize orchestrator with extractors.
        
        Args:
            llm_api_key: Optional API key for LLM extraction. If not provided, only rule-based works.
        """
        self.rule_extractor = RuleBasedExtractor()
        self.llm_extractor: Optional[LLMSignalExtractorV2] = None

        if llm_api_key:
            try:
                self.llm_extractor = LLMSignalExtractorV2(api_key=llm_api_key)
                print("[SignalOrchestrator] LLM extractor initialized (v2 - LLM-first approach)", flush=True)
            except Exception as e:
                print(f"[SignalOrchestrator] Warning: LLM extractor initialization failed: {e}", flush=True)
        else:
            print("[SignalOrchestrator] No API key provided - will use rule-based extraction only", flush=True)

    def extract_signals(
        self,
        user_message: str,
        learner_state: Optional[LearnerState] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Extract signals from user message using LLM-first approach.
        
        Process:
        1. Try LLM extraction FIRST (comprehensive signal detection with confidence)
        2. If LLM fails or returns low confidence, fallback to rule-based
        3. Return best result with confidence scores
        
        Args:
            user_message: Latest message from user
            learner_state: Current learner state (for context)
            conversation_history: Previous messages (for context)
            use_llm: Whether to attempt LLM extraction (default: yes, ignored if no API key)
            
        Returns:
            Dictionary with:
                - llm_result: LLMSignalExtractorV2Result
                - rule_result: RuleExtractionResult (if LLM fails)
                - merged_signals: Combined signals dict
                - engagement_score: Optional engagement quality (0-10)
                - extraction_method: "llm_based" or "rule_based"
        """
        result = {
            "llm_result": None,
            "rule_result": None,
            "merged_signals": {},
            "per_signal_confidence": {},  # Track confidence scores
            "engagement_score": None,
            "extraction_method": "rule_based",
            "execution_time_ms": 0,
            "llm_used": False,
        }

        import time
        start_time = time.time()

        # Step 1: Try LLM extraction FIRST (if enabled and available)
        if use_llm and self.llm_extractor:
            try:
                llm_result = self.llm_extractor.extract(
                    user_message=user_message,
                    conversation_history=conversation_history,
                    current_learner_state=learner_state.to_signal_summary()
                    if learner_state else None,
                )
                result["llm_result"] = llm_result
                result["merged_signals"] = dict(llm_result.extracted_signals)
                result["per_signal_confidence"] = dict(llm_result.per_signal_confidence)
                result["extraction_method"] = "llm_based"
                result["llm_used"] = True

                # Get engagement score from LLM
                try:
                    result["engagement_score"] = self.llm_extractor.extract_engagement_quality(
                        user_message
                    )
                except Exception as e:
                    print(f"[SignalOrchestrator] Engagement scoring failed: {e}", flush=True)
                    result["engagement_score"] = 5.0  # Default

                print(f"[SignalOrchestrator] LLM extraction succeeded: {len(result['merged_signals'])} signals", flush=True)

            except Exception as e:
                print(f"[SignalOrchestrator] LLM extraction failed: {e} - falling back to rule-based", flush=True)
                result["llm_result"] = None
                # Will proceed to rule-based extraction below

        # Step 2: If LLM not used or failed, use rule-based extraction as fallback
        if not result["llm_used"]:
            print(f"[SignalOrchestrator] Using rule-based extraction", flush=True)
            try:
                rule_result = self.rule_extractor.extract_all(user_message)
                result["rule_result"] = rule_result
                result["merged_signals"] = dict(rule_result.extracted_signals)
                result["per_signal_confidence"] = dict(rule_result.per_signal_confidence)
                result["extraction_method"] = "rule_based"

                # Calculate engagement for rule-based
                if result["engagement_score"] is None:
                    result["engagement_score"] = self._calculate_engagement_quality(
                        user_message,
                        rule_result,
                        conversation_history
                    )

            except Exception as e:
                print(f"[SignalOrchestrator] Rule-based extraction also failed: {e}", flush=True)
                result["merged_signals"] = {}
                result["engagement_score"] = 5.0

        end_time = time.time()
        result["execution_time_ms"] = round((end_time - start_time) * 1000, 2)

        return result

    def extract_signals_async(
        self,
        user_message: str,
        learner_state: Optional[LearnerState] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ):
        """
        Async extraction (for future use with event loop).
        For now, just wraps the sync version.
        """
        return self.extract_signals(
            user_message=user_message,
            learner_state=learner_state,
            conversation_history=conversation_history,
            use_llm=True,
        )

    def should_extract_llm_on_this_turn(self, turn_count: int) -> bool:
        """
        ALWAYS return True for LLM extraction.
        With LLM-first approach, we always try LLM.
        The extractor itself decides when to use rule-based fallback.
        
        Args:
            turn_count: Current conversation turn
            
        Returns:
            True (always try LLM, let it fallback if needed)
        """
        return True  # LLM-first approach: always attempt LLM extraction

    def _calculate_engagement_quality(
        self,
        user_message: str,
        rule_extraction_result: 'SignalExtractionResult',
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> float:
        """
        Calculate engagement quality score (0-10) based on rule-based extraction.
        Factors:
        - Message length and detail
        - Number of signals detected
        - Signal confidence average
        - Conversation turn count
        
        Returns:
            Engagement score 0-10
        """
        if not user_message or user_message.strip() in ["<noise>", ""]:
            return 3.0  # Low engagement for noise/empty
        
        score = 5.0  # Base score
        
        # +0.5 per word (detailed messages are more engaged)
        word_count = len(user_message.split())
        score += min(word_count * 0.1, 2.0)  # Max +2.0
        
        # +1.0 for each signal detected (max 3.0 additional)
        signal_count = len(rule_extraction_result.extracted_signals)
        score += min(signal_count * 0.5, 3.0)
        
        # +1.0 if average confidence is high
        if rule_extraction_result.per_signal_confidence:
            avg_confidence = sum(rule_extraction_result.per_signal_confidence.values()) / len(rule_extraction_result.per_signal_confidence)
            if avg_confidence > 0.7:
                score += 1.0
            elif avg_confidence > 0.5:
                score += 0.5
        
        # Conversation turn context
        if conversation_history and len(conversation_history) > 5:
            score += 0.5  # Sustained engagement
        
        return min(max(score, 0.0), 10.0)  # Clamp to 0-10

    def get_extraction_cost_estimate(self) -> Dict[str, Any]:
        """
        Estimate monthly costs for different extraction strategies.
        Based on Gemini pricing.
        """
        return {
            "strategy": "hybrid (rule-based + selective LLM)",
            "monthly_conversations": 1000,
            "llm_calls_per_conversation": 0.5,  # Every other turn
            "estimated_llm_calls": 500,
            "cost_per_call": 0.0001,  # ~Gemini 1.5 Flash pricing
            "estimated_monthly_cost": "$0.05",
            "cost_per_conversation": "$0.00005",
            "note": "Costs drop to ~$0 after collecting 200+ conversations (train local model)",
        }

    def get_extraction_quality_report(
        self,
        extraction_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate quality/diagnostic report on extraction.
        """
        return {
            "method": extraction_result["extraction_method"],
            "signals_found": len(extraction_result["merged_signals"]),
            "rule_confidence": extraction_result["rule_result"].confidence
            if extraction_result["rule_result"] else 0,
            "llm_confidence": extraction_result["llm_result"].confidence
            if extraction_result["llm_result"] else None,
            "execution_time_ms": extraction_result["execution_time_ms"],
            "signals": extraction_result["merged_signals"],
            "engagement_score": extraction_result.get("engagement_score"),
        }


# Example usage and demo
if __name__ == "__main__":
    print("Signal Extraction Orchestrator initialized")
    print("See documentation for usage examples")
