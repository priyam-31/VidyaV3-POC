"""
Prompt Context Injector
Converts learner state into compact context for injection into main LLM prompt.
Keeps injected context minimal to preserve token budget.
"""

from typing import Optional, Dict
from models.learner_state_model import LearnerState
from services.adaptation_engine import AdaptationEngine


class PromptContextInjector:
    """
    Builds and formats context to be injected into the main conversational prompt.
    Focus on COMPACT, HIGH-SIGNAL-VALUE context only.
    """

    @staticmethod
    def build_learner_context_section(learner_state: LearnerState) -> str:
        """
        Build the learner context section for prompt injection.
        This is the PRIMARY thing that gets injected.
        
        Returns:
            Compact learner context (5-10 lines max)
        """
        lines = []

        # Learner type/persona
        if learner_state.persona != "unknown":
            persona_label = learner_state.persona.replace("_", " ").title()
            lines.append(f"**Learner Type:** {persona_label}")

        # Key signals (only HIGH-impact ones)
        key_signals = []

        if learner_state.urgency == "high":
            key_signals.append("Time-sensitive | Goal-focused")

        if learner_state.self_efficacy == "low":
            key_signals.append("Building confidence | Start with foundations")

        if learner_state.stereotype_threat:
            key_signals.append("Needs evidence & concrete examples")

        if learner_state.motivation != "unknown":
            key_signals.append(f"Driver: {learner_state.motivation.replace('_', ' ').title()}")

        if key_signals:
            lines.append(f"**Key Signals:** {' | '.join(key_signals)}")

        # Learning preferences
        prefs = []
        if learner_state.learning_style == "example_driven":
            prefs.append("Examples first")
        if learner_state.language_preference in ["hindi", "hinglish"]:
            prefs.append(f"Language: {learner_state.language_preference}")

        if prefs:
            lines.append(f"**Preferences:** {' | '.join(prefs)}")

        return "\n".join(lines) if lines else "[No learner adaptations]"

    @staticmethod
    def build_adaptation_guidance(learner_state: LearnerState) -> str:
        """
        Build the adaptation guidance section.
        Tells LLM HOW to adapt the conversation.
        """
        engine = AdaptationEngine()

        priorities = engine.generate_adaptation_priorities(learner_state)
        tone = engine.generate_tone_guidance(learner_state)

        lines = [
            "**How to adapt this conversation:**",
            f"- {tone}",
        ]

        # Add top priorities
        for i, priority in enumerate(priorities[:3], 1):
            lines.append(f"- {priority}")

        return "\n".join(lines)

    @staticmethod
    def build_language_guidance(learner_state: LearnerState) -> Optional[str]:
        """
        Build STRICT language-specific guidance with enforcement rules.
        This ensures language choice is locked for the entire conversation.
        """
        if learner_state.language_preference == "unknown":
            return None

        engine = AdaptationEngine()
        instruction = engine.get_language_instruction(learner_state)
        
        if instruction:
            return instruction
        
        return None

    @staticmethod
    def build_scenario_specific_context(learner_state: LearnerState) -> Optional[str]:
        """
        Build highly specific scenario context based on actual user situation.
        This is MORE IMPORTANT than generic ICP guidance.
        
        Returns scenario-specific guidance or None if not enough context.
        """
        engine = AdaptationEngine()
        scenario = engine.generate_scenario_specific_guidance(learner_state)
        return scenario if scenario else None

    @staticmethod
    def build_full_injection(learner_state: LearnerState, include_section_headers: bool = True) -> str:
        """
        Build the FULL context injection to be added to the main prompt.
        This is what actually gets concatenated into the system prompt.
        
        Args:
            learner_state: Current learner state
            include_section_headers: Whether to include readable headers
            
        Returns:
            Formatted injection string ready for prompt concatenation
        """
        sections = []

        # Only inject if we have meaningful learner data
        if learner_state.turn_count == 0 and learner_state.persona == "unknown":
            return ""  # Don't inject empty context early on

        learner_context = PromptContextInjector.build_learner_context_section(learner_state)
        if learner_context != "[No learner adaptations]":
            sections.append(learner_context)

        adaptation_guidance = PromptContextInjector.build_adaptation_guidance(learner_state)
        if adaptation_guidance:
            sections.append(adaptation_guidance)

        language_guidance = PromptContextInjector.build_language_guidance(learner_state)
        if language_guidance:
            sections.append(f"**Language:** {language_guidance}")

        if not sections:
            return ""

        # Join sections with clear separation
        full_injection = "\n\n".join(sections)

        # Wrap in clear markers so it's easy to remove/debug
        if include_section_headers:
            return f"""
=== LEARNER ADAPTATION CONTEXT (Auto-Generated) ===
{full_injection}
=== END LEARNER CONTEXT ===
""".strip()

        return full_injection

    @staticmethod
    def build_injection_for_system_prompt(learner_state: LearnerState) -> str:
        """
        Build injection specifically for adding to system prompt.
        Formatted to integrate smoothly with existing prompt.
        
        Use this when you're building the final system prompt to send to Gemini.
        """
        injection = PromptContextInjector.build_full_injection(learner_state, include_section_headers=False)

        if not injection:
            return ""

        return f"""

## Learner Adaptation Context
{injection}"""

    @staticmethod
    def build_injection_for_user_prompt(learner_state: LearnerState) -> str:
        """
        Alternative: build injection to add to user context (instead of system prompt).
        Useful if you want learner context treated as part of conversation history.
        """
        injection = PromptContextInjector.build_full_injection(learner_state, include_section_headers=False)

        if not injection:
            return ""

        return f"""
[System context: {injection}]"""

    @staticmethod
    def estimate_injection_tokens(learner_state: LearnerState) -> int:
        """
        Estimate tokens used by injection.
        Rough estimate: ~1 token per 4 characters.
        """
        injection = PromptContextInjector.build_full_injection(learner_state)
        return len(injection) // 4

    @staticmethod
    def get_injection_size_report(learner_state: LearnerState) -> Dict[str, int]:
        """
        Detailed breakdown of injection size by section.
        """
        learner_context = PromptContextInjector.build_learner_context_section(learner_state)
        adaptation = PromptContextInjector.build_adaptation_guidance(learner_state)
        language = PromptContextInjector.build_language_guidance(learner_state) or ""

        return {
            "learner_context_chars": len(learner_context),
            "adaptation_chars": len(adaptation),
            "language_chars": len(language),
            "total_chars": len(learner_context) + len(adaptation) + len(language),
            "estimated_tokens": (len(learner_context) + len(adaptation) + len(language)) // 4,
        }

    @staticmethod
    def update_learner_state_from_extraction(
        learner_state: LearnerState,
        extracted_info: Dict[str, Optional[str]]
    ) -> LearnerState:
        """
        Update learner state with scenario-specific information extracted from conversation.
        
        Args:
            learner_state: Current learner state
            extracted_info: Dict with keys like 'company', 'college', 'goal', etc.
            
        Returns:
            Updated learner state with scenario context
        """
        if not extracted_info:
            return learner_state
        
        # Update scenario-specific fields
        if extracted_info.get("company") and extracted_info["company"] != "unknown":
            learner_state.current_company = extracted_info["company"]
        
        if extracted_info.get("college") and extracted_info["college"] != "unknown":
            learner_state.college_name = extracted_info["college"]
        
        if extracted_info.get("career_context"):
            learner_state.specific_pain_point = extracted_info["career_context"]
        
        if extracted_info.get("goal"):
            learner_state.specific_goal = extracted_info["goal"]
        
        return learner_state


from typing import Dict
