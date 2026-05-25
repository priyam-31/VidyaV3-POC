"""
Adaptation Engine
Maps learner state to concrete conversation adaptations and prompt guidance.
"""

from typing import List
from models.learner_state_model import LearnerState


class AdaptationEngine:
    """
    Converts learner state into actionable conversation adaptations.
    Generates guidance for the main LLM prompt.
    """

    @staticmethod
    def generate_tone_guidance(learner_state: LearnerState) -> str:
        """
        Generate brief tone guidance based on learner state.
        
        Returns:
            1-2 sentence guidance on conversation tone
        """
        tone_parts = []

        if learner_state.self_efficacy == "low":
            tone_parts.append("supportive and affirming")
        elif learner_state.self_efficacy == "high":
            tone_parts.append("intellectually challenging")

        if learner_state.urgency == "high":
            tone_parts.append("action-oriented and pragmatic")

        if learner_state.stereotype_threat:
            tone_parts.append("concrete and evidence-based (avoid generic reassurance)")

        if not tone_parts:
            return "Be naturally conversational and curious about the learner's perspective."

        return f"Be {', '.join(tone_parts)} in this conversation."

    @staticmethod
    def generate_adaptation_priorities(learner_state: LearnerState) -> List[str]:
        """
        Generate top 3-5 adaptation priorities based on learner state.
        These guide what the LLM should focus on.
        """
        priorities = []

        # Self-efficacy adaptations
        if learner_state.self_efficacy == "low":
            priorities.append("Build confidence gradually - affirm foundations before moving to advanced topics")

        # Stereotype threat adaptations
        if learner_state.stereotype_threat:
            priorities.append("Use concrete examples and evidence-based reasoning (avoids imposter syndrome)")

        # Learning style adaptations
        if learner_state.learning_style == "example_driven":
            priorities.append("Lead with real-world examples and case studies before theory")
        elif learner_state.learning_style == "theory_first":
            priorities.append("Explain underlying concepts and architecture before diving into practice")

        # Urgency adaptations
        if learner_state.urgency == "high":
            priorities.append("Focus conversation toward concrete next steps and immediate actions")

        # Motivation adaptations
        if learner_state.motivation == "placement_pressure":
            priorities.append("Frame learning in context of hiring outcomes and practical job skills")
        elif learner_state.motivation == "financial_necessity":
            priorities.append("Emphasize ROI, salary progression, and market value")

        # Commitment adaptations
        if learner_state.commitment_strength == "high":
            priorities.append("Lean into deeper discussions, push for ambitious thinking")

        # Add one more if we have room (goal clarity)
        if learner_state.goal_clarity == "low" and len(priorities) < 4:
            priorities.append("Help crystallize vague goals into specific, measurable targets")

        # Return top 4 priorities
        return priorities[:4] if priorities else [
            "Engage naturally and understand the learner's context",
        ]

    @staticmethod
    def generate_avoid_patterns(learner_state: LearnerState) -> List[str]:
        """
        Generate list of patterns to AVOID based on learner state.
        """
        avoid = []

        # Self-efficacy avoids
        if learner_state.self_efficacy == "low":
            avoid.append("Overwhelming multi-step roadmaps or overly technical jargon")
            avoid.append("Comparisons to other successful learners or 'how easy it is'")

        # Stereotype threat avoids
        if learner_state.stereotype_threat:
            avoid.append("Generic motivation or reassurance (feels inauthentic)")
            avoid.append("Vague statements - be specific and evidence-based")

        # Learning style avoids
        if learner_state.learning_style == "example_driven":
            avoid.append("Extended theoretical explanations without examples")

        # Urgency avoids
        if learner_state.urgency == "high":
            avoid.append("Lengthy philosophical discussions or tangents")

        # Goal clarity avoids
        if learner_state.goal_clarity == "low":
            avoid.append("Assuming you know what they want - keep clarifying")

        return avoid[:3]  # Top 3 to avoid

    @staticmethod
    def get_language_instruction(learner_state: LearnerState) -> str:
        """Get strict language-specific instruction for the LLM"""
        if learner_state.language_preference == "hinglish":
            return "STRICT RULE: Respond in Hinglish ONLY (70% Hindi + 30% English). Do NOT use other languages. Tech terms like API, CSS, Python are acceptable. Do NOT switch to pure English or pure Hindi."
        elif learner_state.language_preference == "hindi":
            return "STRICT RULE: Respond in Hindi ONLY. Do NOT use English words except: standard tech terms (API, CSS, HTML, JavaScript, Python, etc.) and company names. No English phrases allowed. This is mandatory for entire conversation."
        elif learner_state.language_preference == "english":
            return "STRICT RULE: Respond in English ONLY. Do NOT use Hindi, Hinglish, or any other language. Tech terms and company names only. This is mandatory for entire conversation."

        return "Use English unless the learner specifically requests otherwise."

    @staticmethod
    def generate_scenario_specific_guidance(learner_state: LearnerState) -> str:
        """
        Generate HIGHLY SPECIFIC guidance based on user's exact scenario, not generic ICP.
        
        E.g., if user says "I'm working at TCS as a service engineer", generate guidance
        specific to THAT situation, not generic working professional advice.
        """
        scenario_parts = []

        # SPECIFIC COMPANY/SECTOR CONTEXT
        if hasattr(learner_state, 'current_company') and learner_state.current_company and learner_state.current_company != "unknown":
            scenario_parts.append(f"**Current Situation**: Working at {learner_state.current_company}")
            
            # Service company specific
            if any(word in learner_state.current_company.lower() for word in ['tcs', 'infosys', 'wipro', 'accenture', 'cognizant', 'service']):
                scenario_parts.append("**Service Company Context**: You have real-world problem-solving and client-handling skills. Your advantage: you understand production systems, not theory.")
                scenario_parts.append("**What to leverage**: Your service experience IS your differentiator. Product companies value this — they need people who've lived with messy real-world constraints.")
                scenario_parts.append("**Wrong belief to address**: 'I need to learn everything from scratch' — NO. You already know how systems scale, how to handle production issues, how to communicate with clients. Build ON that.")

            # Product company - if they say they work at product company
            elif any(word in learner_state.current_company.lower() for word in ['amazon', 'microsoft', 'google', 'flipkart', 'swiggy', 'unacademy', 'product']):
                scenario_parts.append("**Product Company Context**: You're already in product. Your focus: leveling up within company or moving to a higher-impact role.")
                scenario_parts.append("**What to leverage**: Product thinking, user-centric mindset, shipping velocity. Your advantage over service engineers.")

        # SPECIFIC COLLEGE/TIER CONTEXT  
        elif hasattr(learner_state, 'college_name') and learner_state.college_name and learner_state.college_name != "unknown":
            scenario_parts.append(f"**College**: {learner_state.college_name}")
            
            if any(word in learner_state.college_name.lower() for word in ['iit', 'nit', 'tier-1']):
                scenario_parts.append("**IIT/NIT Context**: Your advantage is already clear on resume. Focus on: interview depth, system design, behavioral edge.")
            else:
                scenario_parts.append("**Tier-2/Tier-3 Context**: Your advantage is RESILIENCE. You've probably worked harder than your IIT peers. Use this.")
                scenario_parts.append("**Wrong belief to address**: 'Tier-2 college means I can't get product companies' — FALSE. Recent hiring data shows 30-40% of product hires are from Tier-2/3. What matters: your interview performance, not college name.")

        # SPECIFIC MOTIVATION/PAIN POINT
        if hasattr(learner_state, 'specific_pain_point') and learner_state.specific_pain_point and learner_state.specific_pain_point != "unknown":
            scenario_parts.append(f"**Your Pain Point**: {learner_state.specific_pain_point}")
            
            if 'placement' in learner_state.specific_pain_point.lower():
                scenario_parts.append("**Placement Crisis**: This is solvable. You have 12-16 weeks to get interview-ready. Companies hire hard in Sep-Oct and Jan-Feb.")
            elif 'appraisal' in learner_state.specific_pain_point.lower() or 'stuck' in learner_state.specific_pain_point.lower():
                scenario_parts.append("**Career Stagnation**: This is deliberate — you need a different skill to stand out. Not a character flaw, a skill gap.")
            elif 'rejected' in learner_state.specific_pain_point.lower() or 'interview' in learner_state.specific_pain_point.lower():
                scenario_parts.append("**Interview Failure**: Not a reflection of your ability. Interview skills are SEPARATE from coding ability. We fix this.")

        # SPECIFIC GOAL
        if hasattr(learner_state, 'specific_goal') and learner_state.specific_goal and learner_state.specific_goal != "unknown":
            scenario_parts.append(f"**Your Goal**: {learner_state.specific_goal}")
            
            if 'product' in learner_state.specific_goal.lower():
                scenario_parts.append("**Product Company Goal**: Your roadmap is clear: system design (the 30% gap most service engineers have), behavioral readiness, and 1-2 focused projects.")
            elif 'startup' in learner_state.specific_goal.lower():
                scenario_parts.append("**Startup Goal**: Speed matters more than depth. Your learning should focus on MVP-building, not theoretical perfection.")
            elif 'salary' in learner_state.specific_goal.lower() or 'hike' in learner_state.specific_goal.lower():
                scenario_parts.append("**Salary/Promotion Goal**: This is tied to skill visibility. The plan: build one standout project that showcases your new skill.")

        if scenario_parts:
            return "\n".join(scenario_parts) + "\n\n**CRITICAL**: Tailor every piece of advice to this specific scenario. Don't give generic advice that could apply to someone at a different company or college."
        
        return ""
