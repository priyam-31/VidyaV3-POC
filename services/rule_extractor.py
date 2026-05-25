"""
Rule-Based Signal Extractor
Uses regex patterns, keywords, and heuristics to extract obvious signals.
Fast, explainable, low-cost extraction.
"""

import re
from typing import Dict, Optional
from models.learner_state_model import SignalExtractionResult


class RuleBasedExtractor:
    """
    Extracts signals using predefined rules and keyword matching.
    Perfect for high-confidence, low-latency extraction.
    """

    # Persona Detection Rules
    LOW_WAGE_KEYWORDS = [
        r"\b(?:first|second|third|final|4th)\s+(?:year|semester|sem)\b",
        r"\bcollege\b",
        r"\buniversity\b",
        r"\bstudent\b",
        r"\bcampus\b",
        r"\bplacement\s+(?:season|drive|cell)\b",
        r"\b(?:btw|bye)\b",  # common in student speech
        r"\bcs\s+branch\b",
        r"\bplacement\s+pressure\b",
        r"\b(?:vit|iit|nit|bits|jnu|du)\b",  # College names
        r"\bbtechb",  # BTech degree
        r"\bm\.?tech\b",  # MTech degree
        r"\bdeployment|internship\b",
    ]

    HIGH_WAGE_KEYWORDS = [
        r"\b(?:infosys|tcs|cognizant|wipro|accenture)\b",
        r"\bservice\s+engineer\b",
        r"\bservices\b",
        r"\bsoftware\s+engineer\b",
        r"\byears?\s+(?:of\s+)?experience\b",
        r"\b(?:sr|senior)\s+software\b",
        r"\b(?:staff|principal)\s+engineer\b",
        r"\bcareer\s+growth\b",
    ]

    LANGUAGE_PREFERENCE_RULES = {
        "english": [
            r"\b(?:english|in\s+english)\b",
            r"\b(?:speak|talk|language)\s+(?:in\s+)?english\b",
        ],
        "hindi": [
            r"\b(?:हिंदी|hindi)\b",
            r"[\u0900-\u097F]",  # Devanagari script
            r"\b(?:hindi\s+mein|in\s+hindi)\b",
        ],
        "hinglish": [
            r"(?:yaar|bhai|sala|arre|haan|nahi)",  # Hinglish markers
            r"(?:\b\w+\s+[\u0900-\u097F]|\b[\u0900-\u097F]\s+\w+)",  # Mixed script
        ],
    }

    URGENCY_KEYWORDS = {
        "high": [
            r"\b(?:urgent|asap|immediately|now|quickly|soon)\b",
            r"\b(?:before|by)\s+(?:summer|month|week)\b",
            r"\bplacement\s+(?:drive|season)\b",
            r"\bneed\s+(?:to|a)\s+job\b",
            r"\bcompany\s+(?:switch|change)\b",
        ],
        "low": [
            r"\b(?:no\s+rush|whenever|take\s+time)\b",
            r"\b(?:just|just\s+exploring|curious)\b",
        ],
    }

    MOTIVATION_KEYWORDS = {
        "placement_pressure": [
            r"\bplacement\b",
            r"\bneed\s+(?:a\s+)?job\b",
            r"\bfinal\s+(?:year|semester)\b",
            r"\bjob\s+(?:search|hunt)\b",
            r"\b(?:feel|left|behind|compared|pressure)\b",
            r"\b(?:behind|lag|lagging)\b",
        ],
        "career_growth": [
            r"\bcareer\s+(?:growth|advancement|progression)\b",
            r"\b(?:senior|staff|lead)\s+(?:engineer|role)\b",
            r"\bnext\s+level\b",
            r"\bcompany\s+(?:type|preference|product|service)\b",
        ],
        "financial_necessity": [
            r"\b(?:salary|pay|earn|money|lpa|ctc)\b",
            r"\b(?:financial|pay\s+raise|package)\b",
            r"\b(?:10|15|20|25|30)\s+(?:lpa|package)\b",
        ],
        "social_proof": [
            r"\bfriend\b",
            r"\bcolleague\b",
            r"\bpeer\b",
            r"\beveryone\s+(?:is|else)\b",
            r"\b(?:compared\s+to|vs|versus)\b",
            r"\b(?:others|everyone else)\b",
        ],
        "curiosity": [
            r"\b(?:curious|interested|exploring|want\s+to|would\s+like)\b",
            r"\bwant\s+to\s+learn\b",
        ],
    }

    SELF_EFFICACY_KEYWORDS = {
        "low": [
            r"\b(?:can't|cannot|don't|doubt|unsure|worried)\b",
            r"\b(?:scared|afraid|anxious)\b",
            r"\b(?:never\s+done|no\s+experience)\b",
            r"\b(?:too\s+hard|impossible|complex)\b",
            r"\b(?:don't\s+know|don't\s+have)\b",
            r"\b(?:behind|lagging|left\s+behind)\b",
        ],
        "high": [
            r"\b(?:can|confident|sure|experienced)\b",
            r"\b(?:done\s+this|built|created)\b",
            r"\b(?:easy|straightforward|basics)\b",
            r"\b(?:have|got|know)\s+(?:javascript|html|css|python|java|skills)\b",
        ],
    }

    LEARNING_STYLE_KEYWORDS = {
        "example_driven": [
            r"\b(?:example|case\s+study|real-world|practical)\b",
            r"\b(?:show\s+me|demonstrate|how\s+to)\b",
        ],
        "theory_first": [
            r"\b(?:concept|theory|fundamental|understand\s+why)\b",
            r"\b(?:deep\s+dive|architecture)\b",
        ],
        "project_based": [
            r"\b(?:project|build|create|make|develop)\b",
            r"\b(?:hands-on|by\s+doing)\b",
        ],
    }

    # Technical skills detection
    SKILLS_KEYWORDS = [
        r"\b(?:javascript|python|java|c\+\+|typescript|golang|rust)\b",
        r"\b(?:react|vue|angular|node|express)\b",
        r"\b(?:html|css|sql|mongodb)\b",
        r"\b(?:git|docker|aws|gcp|azure)\b",
        r"\b(?:frontend|front-end|backend|back-end|fullstack|full-stack)\b",
    ]

    # Goal/aspiration keywords
    GOAL_KEYWORDS = [
        r"\b(?:become|be|become a|work as)\s+(?:developer|engineer|designer)\b",
        r"\b(?:want|would like|aspire|dream|goal)\b",
        r"\bsalary|package|lpa|ctc\b",
    ]

    # Time commitment keywords
    TIME_COMMITMENT_KEYWORDS = {
        "high": [
            r"\b(?:[5-9]|[0-9]{2,})\s*(?:hours?|hrs)\s*(?:per|a)?\s*(?:week|day)\b",
            r"\b(?:full\s+time|dedicated|consistently)\b",
        ],
        "low": [
            r"\b(?:1|2)\s*(?:hours?|hrs)\s*(?:per|a)?\s*(?:week|day)\b",
            r"b(?:occasional|whenever|sporadic)\b",
        ],
    }

    PROOF_ORIENTATION_KEYWORDS = {
        "high": [
            r"\b(?:why|proof|evidence|data|statistic)\b",
            r"\b(?:show\s+me|how\s+do\s+you|what's\s+the)\b",
        ],
    }

    STEREOTYPE_THREAT_KEYWORDS = [
        r"\b(?:imposter\s+syndrome|not\s+like\s+others)\b",
        r"\b(?:everyone\s+else)\b",
        r"\b(?:doubt\s+myself|comparing\s+to)\b",
    ]

    GOAL_CLARITY_KEYWORDS = {
        "high": [
            r"\b(?:want|goal|target|plan|aim)\s+(?:to|is)\b",
            r"\b(?:specific|clear|exact|accha goal)\b",
            r"\b(?:role|company|salary|timeline|lpa)\b",
            r"\b(?:developer|engineer|designer|frontend|backend)\b",
            r"\b(?:product|service|startup|company)\s+(?:based|type)\b",
            r"\b(?:15|10|20|25)\s+lpa\b",
            r"\b(?:junior|mid-level|senior)\s+(?:developer|engineer)\b",
        ],
        "low": [
            r"\b(?:not\s+sure|unclear|vague|confused)\b",
            r"\b(?:figuring\s+out|exploring|just\s+exploring)\b",
        ],
    }

    # NEW: Educational & Behavioral Signal Keywords
    ANXIETY_LEVEL_KEYWORDS = {
        "high": [
            r"\b(?:scared|afraid|anxious|nervous|worried|stressed)\b",
            r"\b(?:overwhelmed|panicked|tension|pressure)\b",
            r"\b(?:can't\s+sleep|losing\s+sleep|not\s+sleeping)\b",
            r"\b(?:my\s+heart|racing|pounding)\b",
        ],
        "low": [
            r"\b(?:calm|confident|relaxed|comfortable|at\s+ease)\b",
            r"\b(?:no\s+pressure|chilled|cool)\b",
        ],
    }

    COMPARISON_ANXIETY_KEYWORDS = {
        "high": [
            r"\b(?:compared\s+to|vs|versus|others)\b",
            r"\b(?:everyone\s+else|people\s+like|my\s+peers)\b",
            r"\b(?:behind|lagging|left\s+behind|catching\s+up)\b",
            r"\b(?:same\s+age|my\s+batch|cohort)\b",
            r"\b(?:better\s+than|good\s+as|not\s+as\s+good)\b",
        ],
        "low": [
            r"\b(?:focus\s+on\s+(?:myself|me)|my\s+own\s+pace)\b",
            r"\b(?:don't\s+(?:care|worry)\s+(?:what|who))\b",
        ],
    }

    STRUCTURE_DEPENDENCE_KEYWORDS = {
        "high": [
            r"\b(?:roadmap|syllabus|curriculum|structure|planned)\b",
            r"\b(?:tell\s+me\s+what|what\s+should|should\s+i)\b",
            r"\b(?:step\s+by\s+step|sequence|order)\b",
            r"\b(?:guidance|guidance|direction|leading)\b",
        ],
        "low": [
            r"\b(?:figure\s+out|explore|on\s+my\s+own|self-learner)\b",
            r"\b(?:independent|self-directed|learn\s+myself)\b",
        ],
    }

    ABSTRACTION_TOLERANCE_KEYWORDS = {
        "high": [
            r"\b(?:concept|theory|fundamental|architecture|design\s+pattern)\b",
            r"\b(?:how\s+it\s+works|why|principle)\b",
            r"\b(?:abstract|generalize|broad\s+understanding)\b",
        ],
        "low": [
            r"\b(?:concrete\s+example|show\s+me|demonstrate|real-world|practical)\b",
            r"\b(?:can't\s+understand|don't\s+get\s+it|confusing)\b",
            r"\b(?:specific|tangible|concrete)\b",
        ],
    }

    INFORMATION_DENSITY_TOLERANCE_KEYWORDS = {
        "high": [
            r"\b(?:a\s+lot|tons|comprehensive|complete|in\s+depth)\b",
            r"\b(?:detailed|thorough|all\s+the|everything)\b",
            r"\b(?:can\s+handle|no\s+problem|bring\s+it\s+on)\b",
        ],
        "low": [
            r"\b(?:simpler|break\s+it\s+down|slow|small\s+pieces|one\s+thing)\b",
            r"\b(?:too\s+much|too\s+fast|information\s+overload)\b",
            r"\b(?:easy|basic|simple|foundational)\b",
        ],
    }

    CONFIDENCE_STABILITY_KEYWORDS = {
        "fragile": [
            r"\b(?:one\s+mistake|small\s+error|any\s+failure|doubt\s+myself)\b",
            r"\b(?:discouraged|demoralized|give\s+up|quit)\b",
            r"\b(?:once\s+i\s+fail|if\s+i\s+(?:get|make\s+an\s+error))\b",
        ],
        "stable": [
            r"\b(?:keep\s+trying|keep\s+going|bounce\s+back)\b",
            r"\b(?:failure\s+is|learn\s+from|mistake\s+helps)\b",
            r"\b(?:persistent|resilient|determined)\b",
        ],
    }

    SELF_DIRECTED_LEARNING_KEYWORDS = {
        "high": [
            r"\b(?:self-learner|independent|teach\s+myself|learn\s+on\s+my\s+own)\b",
            r"\b(?:resources|youtube|documentation|explore)\b",
            r"\b(?:don't\s+need|figure\s+out\s+myself)\b",
        ],
        "low": [
            r"\b(?:tell\s+me|guide\s+me|show\s+me\s+how|lost|confused)\b",
            r"\b(?:depend\s+on|need\s+help|need\s+guidance)\b",
        ],
    }

    BEST_EXPLANATION_STYLE_KEYWORDS = {
        "analogy_based": [
            r"\b(?:like\s+(?:when|a|this)|similar\s+to|it's\s+like|imagine)\b",
            r"\b(?:compare|comparison|similar|analogy)\b",
        ],
        "visual": [
            r"\b(?:show\s+me|visualize|diagram|chart|picture|draw)\b",
            r"\b(?:see\s+how|visual|graphic)\b",
        ],
        "stepwise": [
            r"\b(?:step\s+by\s+step|one\s+by\s+one|first\s+then|sequence)\b",
            r"\b(?:break\s+down|break\s+it|part\s+by\s+part)\b",
        ],
        "practical": [
            r"\b(?:real-world|practical|example|use\s+case|actual)\b",
            r"\b(?:how\s+to|hands-on|build|create)\b",
        ],
        "theory_first": [
            r"\b(?:concept|theory|fundamental|why|principle|understand\s+why)\b",
            r"\b(?:first\s+explain|before\s+coding|background)\b",
        ],
        "code_first": [
            r"\b(?:code|coding|show\s+code|example\s+code)\b",
            r"\b(?:by\s+coding|hands-on\s+coding)\b",
        ],
    }

    FEEDBACK_SENSITIVITY_KEYWORDS = {
        "high": [
            r"\b(?:sensitive|easily\s+(?:offended|hurt)|critical|harsh)\b",
            r"\b(?:don't\s+like\s+(?:feedback|criticism|being\s+corrected))\b",
            r"\b(?:my\s+feelings|take\s+it\s+personally)\b",
        ],
        "low": [
            r"\b(?:appreciate\s+feedback|give\s+me\s+feedback|honest\s+feedback)\b",
            r"\b(?:constructive\s+criticism|critique|correction)\b",
        ],
    }

    INTERVIEW_CONFIDENCE_KEYWORDS = {
        "high": [
            r"\b(?:interview\s+(?:ready|confident|experience))\b",
            r"\b(?:done\s+(?:interviews|lots\s+of))\b",
            r"\b(?:speak|communication|articulate|express)\b",
        ],
        "low": [
            r"\b(?:interview\s+(?:fear|anxiety|panic|scared|worried))\b",
            r"\b(?:tongue-tied|get\s+nervous|blank\s+(?:mind|out))\b",
            r"\b(?:first\s+interview|never\s+interviewed)\b",
        ],
    }

    # Session Closure Trigger Keywords
    # These patterns indicate when the AI should close the session (coaching call end)
    SESSION_CLOSURE_TRIGGER_KEYWORDS = [
        r"\b(?:let's\s+get\s+started|let's\s+begin|let's\s+start)\b",
        r"\blet's?\s+do\s+(?:this|it)\b",
        r"\b(?:here's\s+what\s+(?:happens\s+)?next|here's\s+the\s+plan)\b",
        r"\b(?:see\s+you|catch\s+you)\s+(?:in|on|after)\b",
        r"\b(?:program\s+(?:kickoff|starts))\b",
        r"\b(?:next\s+phase\s+(?:is|begins))\b",
        r"\b(?:ready\s+to\s+dive\s+in|ready\s+to\s+begin)\b",
    ]

    # User Commitment/Ready Signals (user indicates readiness for next phase)
    USER_COMMITMENT_KEYWORDS = [
        r"\b(?:yes|yep|yeah|yup|absolutely|definitely|definitely|sure|okay|ok|ofc|of course)\b",
        r"\b(?:let's\s+do\s+(?:this|it)|let's\s+go)\b",
        r"\b(?:i'm\s+ready|i\s+am\s+ready|ready\s+to\s+start)\b",
        r"\b(?:sounds\s+(?:good|great|perfect))\b",
    ]

    @staticmethod
    def _match_keywords(text: str, keyword_patterns: list[str]) -> bool:
        """Helper to check if any keyword pattern matches"""
        text_lower = text.lower()
        for pattern in keyword_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _count_keyword_matches(text: str, keyword_patterns: list[str]) -> int:
        """Helper to count how many keyword patterns match"""
        text_lower = text.lower()
        count = 0
        for pattern in keyword_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                count += 1
        return count

    @staticmethod
    def _match_keyword_dict(
        text: str, keyword_dict: Dict[str, list[str]]
    ) -> Optional[str]:
        """Helper to find which category matches (returns first match)"""
        text_lower = text.lower()
        for category, patterns in keyword_dict.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return category
        return None

    def extract_persona(self, text: str) -> Optional[str]:
        """Extract persona: low_wage or high_wage"""
        text_lower = text.lower()

        # Count matches for each persona
        low_wage_matches = sum(
            1 for pattern in self.LOW_WAGE_KEYWORDS
            if re.search(pattern, text_lower, re.IGNORECASE)
        )
        high_wage_matches = sum(
            1 for pattern in self.HIGH_WAGE_KEYWORDS
            if re.search(pattern, text_lower, re.IGNORECASE)
        )

        if low_wage_matches > high_wage_matches and low_wage_matches > 0:
            return "low_wage"
        elif high_wage_matches > low_wage_matches and high_wage_matches > 0:
            return "high_wage"

        return None

    def extract_language_preference(self, text: str) -> Optional[str]:
        """Extract language preference"""
        # Check for English first
        if self._match_keywords(text, self.LANGUAGE_PREFERENCE_RULES.get("english", [])):
            return "english"
        # Check for Hindi (most specific Devanagari)
        if self._match_keywords(text, self.LANGUAGE_PREFERENCE_RULES.get("hindi", [])):
            return "hindi"
        # Then check for Hinglish
        if self._match_keywords(text, self.LANGUAGE_PREFERENCE_RULES.get("hinglish", [])):
            return "hinglish"

        return None

    def extract_urgency(self, text: str) -> Optional[str]:
        """Extract urgency level"""
        if self._match_keywords(text, self.URGENCY_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.URGENCY_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_motivation(self, text: str) -> Optional[str]:
        """Extract primary motivation"""
        return self._match_keyword_dict(text, self.MOTIVATION_KEYWORDS)

    def extract_self_efficacy(self, text: str) -> Optional[str]:
        """Extract self-efficacy signal"""
        if self._match_keywords(text, self.SELF_EFFICACY_KEYWORDS.get("low", [])):
            return "low"
        if self._match_keywords(text, self.SELF_EFFICACY_KEYWORDS.get("high", [])):
            return "high"
        return None

    def extract_learning_style(self, text: str) -> Optional[str]:
        """Extract learning style preference"""
        return self._match_keyword_dict(text, self.LEARNING_STYLE_KEYWORDS)

    def extract_proof_orientation(self, text: str) -> bool:
        """Extract if user has high proof orientation"""
        return self._match_keywords(text, self.PROOF_ORIENTATION_KEYWORDS.get("high", []))

    def extract_stereotype_threat(self, text: str) -> bool:
        """Extract if user shows signs of stereotype threat"""
        return self._match_keywords(text, self.STEREOTYPE_THREAT_KEYWORDS)

    def extract_goal_clarity(self, text: str) -> Optional[str]:
        """Extract goal clarity level"""
        # Check for explicit goal keywords first
        if self._match_keywords(text, self.GOAL_KEYWORDS):
            # If they mention specific role, company type, or salary - that's HIGH clarity
            if self._match_keywords(text, [r"\b(?:developer|frontend|backend|engineer|role)\b", r"\b(?:product|service|startup|company)\b", r"\blpa|package|salary\b"]):
                return "high"
        
        if self._match_keywords(text, self.GOAL_CLARITY_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.GOAL_CLARITY_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_time_commitment(self, text: str) -> Optional[str]:
        """Extract time commitment level"""
        if self._match_keywords(text, self.TIME_COMMITMENT_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.TIME_COMMITMENT_KEYWORDS.get("low", [])):
            return "low"
        return None

    # NEW: Educational & Behavioral Signal Extractors
    def extract_anxiety_level(self, text: str) -> Optional[str]:
        """Extract overall anxiety level"""
        if self._match_keywords(text, self.ANXIETY_LEVEL_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.ANXIETY_LEVEL_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_comparison_anxiety(self, text: str) -> Optional[str]:
        """Extract comparison anxiety level"""
        if self._match_keywords(text, self.COMPARISON_ANXIETY_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.COMPARISON_ANXIETY_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_structure_dependence(self, text: str) -> Optional[str]:
        """Extract structure dependence level"""
        if self._match_keywords(text, self.STRUCTURE_DEPENDENCE_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.STRUCTURE_DEPENDENCE_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_abstraction_tolerance(self, text: str) -> Optional[str]:
        """Extract abstraction tolerance level"""
        if self._match_keywords(text, self.ABSTRACTION_TOLERANCE_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.ABSTRACTION_TOLERANCE_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_information_density_tolerance(self, text: str) -> Optional[str]:
        """Extract information density tolerance"""
        if self._match_keywords(text, self.INFORMATION_DENSITY_TOLERANCE_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.INFORMATION_DENSITY_TOLERANCE_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_confidence_stability(self, text: str) -> Optional[str]:
        """Extract confidence stability level"""
        if self._match_keywords(text, self.CONFIDENCE_STABILITY_KEYWORDS.get("fragile", [])):
            return "fragile"
        if self._match_keywords(text, self.CONFIDENCE_STABILITY_KEYWORDS.get("stable", [])):
            return "stable"
        return None

    def extract_self_directed_learning_ability(self, text: str) -> Optional[str]:
        """Extract self-directed learning ability"""
        if self._match_keywords(text, self.SELF_DIRECTED_LEARNING_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.SELF_DIRECTED_LEARNING_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_best_explanation_style(self, text: str) -> Optional[str]:
        """Extract best explanation style"""
        return self._match_keyword_dict(text, self.BEST_EXPLANATION_STYLE_KEYWORDS)

    def extract_feedback_sensitivity(self, text: str) -> Optional[str]:
        """Extract feedback sensitivity level"""
        if self._match_keywords(text, self.FEEDBACK_SENSITIVITY_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.FEEDBACK_SENSITIVITY_KEYWORDS.get("low", [])):
            return "low"
        return None

    def extract_interview_confidence(self, text: str) -> Optional[str]:
        """Extract interview confidence level"""
        if self._match_keywords(text, self.INTERVIEW_CONFIDENCE_KEYWORDS.get("high", [])):
            return "high"
        if self._match_keywords(text, self.INTERVIEW_CONFIDENCE_KEYWORDS.get("low", [])):
            return "low"
        return None

    def detect_session_closure_trigger(self, text: str) -> bool:
        """
        Detect if AI response contains session closure trigger phrases.
        Used to mark conversation end and close the session.
        
        Returns:
            True if text contains phrases like "let's get started", "here's what happens next", etc.
        """
        return self._match_keywords(text, self.SESSION_CLOSURE_TRIGGER_KEYWORDS)

    def detect_user_commitment(self, text: str) -> bool:
        """
        Detect if user shows commitment/readiness signals.
        Indicates user is ready to proceed to next phase.
        
        Returns:
            True if text contains commitment phrases like "yes", "ready", "let's do it", etc.
        """
        return self._match_keywords(text, self.USER_COMMITMENT_KEYWORDS)

    def check_language_mixing_violation(self, text: str, expected_language: str) -> bool:
        """
        Check if text violates language purity rule.
        Returns True if inappropriate language mixing detected.
        
        Args:
            text: The text to check
            expected_language: User's selected language ("english", "hindi", or "hinglish")
        
        Returns:
            True if language mixing violation detected
        """
        if expected_language == "english":
            # English mode: should have minimal or no Devanagari script
            devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
            return devanagari_count > 2  # Allow 1-2 accidental characters
        
        elif expected_language == "hindi":
            # Hindi mode: should be primarily Devanagari, minimal English words (except tech terms)
            devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
            total_chars = len(re.findall(r"\w", text))
            # If less than 40% Devanagari, it's mixed too much toward English
            return (devanagari_count / total_chars < 0.4) if total_chars > 0 else False
        
        elif expected_language == "hinglish":
            # Hinglish mode: should maintain ~70% Hindi / 30% English mix
            # This is more permissive, just check for extreme imbalance
            devanagari_count = len(re.findall(r"[\u0900-\u097F]", text))
            total_chars = len(re.findall(r"\w", text))
            # Allow broader range for Hinglish: 30-70% Devanagari
            if total_chars > 0:
                ratio = devanagari_count / total_chars
                return ratio < 0.2 or ratio > 0.8  # Violation if too skewed
            return False
        
        return False

    def extract_all(self, text: str) -> SignalExtractionResult:
        """
        Run all rule-based extractors and return structured result.
        Calculates per-signal confidence based on keyword match counts.
        
        Returns:
            SignalExtractionResult with all extracted signals and per-signal confidence
        """
        signals = {}
        per_signal_confidence = {}
        evidence_parts = []
        
        print(f"[RuleExtractor] extract_all called with text: {text[:100]}", flush=True)

        # Extract persona with confidence
        if persona := self.extract_persona(text):
            text_lower = text.lower()
            low_wage_matches = self._count_keyword_matches(text_lower, self.LOW_WAGE_KEYWORDS)
            high_wage_matches = self._count_keyword_matches(text_lower, self.HIGH_WAGE_KEYWORDS)
            
            # Confidence = base 0.6 + (matches * 0.08), capped at 1.0
            max_matches = max(low_wage_matches, high_wage_matches)
            confidence = min(0.6 + (max_matches * 0.08), 1.0)
            
            signals["persona"] = persona
            per_signal_confidence["persona"] = confidence
            evidence_parts.append(f"persona={persona} ({confidence:.2f})")
            print(f"[RuleExtractor] Found persona: {persona} (confidence={confidence})", flush=True)

        # Language preference with confidence
        if lang_pref := self.extract_language_preference(text):
            text_lower = text.lower()
            if lang_pref == "english":
                matches = self._count_keyword_matches(text_lower, self.LANGUAGE_PREFERENCE_RULES.get("english", []))
                confidence = min(0.6 + (matches * 0.1), 1.0)
            elif lang_pref == "hindi":
                matches = self._count_keyword_matches(text_lower, self.LANGUAGE_PREFERENCE_RULES.get("hindi", []))
                confidence = min(0.6 + (matches * 0.1), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.LANGUAGE_PREFERENCE_RULES.get("hinglish", []))
                confidence = min(0.6 + (matches * 0.1), 1.0)
            
            signals["language_preference"] = lang_pref
            per_signal_confidence["language_preference"] = confidence
            evidence_parts.append(f"language={lang_pref} ({confidence:.2f})")

        # Urgency with confidence
        if urgency := self.extract_urgency(text):
            text_lower = text.lower()
            if urgency == "high":
                matches = self._count_keyword_matches(text_lower, self.URGENCY_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.URGENCY_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["urgency"] = urgency
            per_signal_confidence["urgency"] = confidence
            evidence_parts.append(f"urgency={urgency} ({confidence:.2f})")

        # Motivation with confidence
        if motivation := self.extract_motivation(text):
            text_lower = text.lower()
            matches = self._count_keyword_matches(text_lower, self.MOTIVATION_KEYWORDS.get(motivation, []))
            confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["motivation"] = motivation
            per_signal_confidence["motivation"] = confidence
            evidence_parts.append(f"motivation={motivation} ({confidence:.2f})")

        # Self-efficacy with confidence
        if self_eff := self.extract_self_efficacy(text):
            text_lower = text.lower()
            if self_eff == "low":
                matches = self._count_keyword_matches(text_lower, self.SELF_EFFICACY_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.SELF_EFFICACY_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["self_efficacy"] = self_eff
            per_signal_confidence["self_efficacy"] = confidence
            evidence_parts.append(f"self_efficacy={self_eff} ({confidence:.2f})")

        # Learning style with confidence
        if learning_style := self.extract_learning_style(text):
            text_lower = text.lower()
            matches = self._count_keyword_matches(text_lower, self.LEARNING_STYLE_KEYWORDS.get(learning_style, []))
            confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["learning_style"] = learning_style
            per_signal_confidence["learning_style"] = confidence
            evidence_parts.append(f"learning_style={learning_style} ({confidence:.2f})")

        # Goal clarity with confidence
        if goal_clarity := self.extract_goal_clarity(text):
            text_lower = text.lower()
            if goal_clarity == "high":
                matches = self._count_keyword_matches(text_lower, self.GOAL_CLARITY_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.GOAL_CLARITY_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["goal_clarity"] = goal_clarity
            per_signal_confidence["goal_clarity"] = confidence
            evidence_parts.append(f"goal_clarity={goal_clarity} ({confidence:.2f})")

        # Proof orientation with confidence
        if self.extract_proof_orientation(text):
            text_lower = text.lower()
            matches = self._count_keyword_matches(text_lower, self.PROOF_ORIENTATION_KEYWORDS.get("high", []))
            confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["proof_orientation"] = "high"
            per_signal_confidence["proof_orientation"] = confidence
            evidence_parts.append(f"proof_orientation=high ({confidence:.2f})")

        # Stereotype threat with confidence
        if self.extract_stereotype_threat(text):
            text_lower = text.lower()
            matches = self._count_keyword_matches(text_lower, self.STEREOTYPE_THREAT_KEYWORDS)
            confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["stereotype_threat"] = True
            per_signal_confidence["stereotype_threat"] = confidence
            evidence_parts.append(f"stereotype_threat=true ({confidence:.2f})")

        # Time commitment with confidence
        if time_commit := self.extract_time_commitment(text):
            text_lower = text.lower()
            if time_commit == "high":
                matches = self._count_keyword_matches(text_lower, self.TIME_COMMITMENT_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.TIME_COMMITMENT_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["time_commitment"] = time_commit
            per_signal_confidence["time_commitment"] = confidence
            evidence_parts.append(f"time_commitment={time_commit} ({confidence:.2f})")
            print(f"[RuleExtractor] Found time_commitment: {time_commit} (confidence={confidence})", flush=True)

        # NEW: Extract educational & behavioral signals
        # Anxiety level with confidence
        if anxiety := self.extract_anxiety_level(text):
            text_lower = text.lower()
            if anxiety == "high":
                matches = self._count_keyword_matches(text_lower, self.ANXIETY_LEVEL_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.ANXIETY_LEVEL_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["anxiety_level"] = anxiety
            per_signal_confidence["anxiety_level"] = confidence
            evidence_parts.append(f"anxiety_level={anxiety} ({confidence:.2f})")

        # Comparison anxiety with confidence
        if comp_anxiety := self.extract_comparison_anxiety(text):
            text_lower = text.lower()
            if comp_anxiety == "high":
                matches = self._count_keyword_matches(text_lower, self.COMPARISON_ANXIETY_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.COMPARISON_ANXIETY_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["comparison_anxiety"] = comp_anxiety
            per_signal_confidence["comparison_anxiety"] = confidence
            evidence_parts.append(f"comparison_anxiety={comp_anxiety} ({confidence:.2f})")

        # Structure dependence with confidence
        if struct_dep := self.extract_structure_dependence(text):
            text_lower = text.lower()
            if struct_dep == "high":
                matches = self._count_keyword_matches(text_lower, self.STRUCTURE_DEPENDENCE_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.STRUCTURE_DEPENDENCE_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["structure_dependence"] = struct_dep
            per_signal_confidence["structure_dependence"] = confidence
            evidence_parts.append(f"structure_dependence={struct_dep} ({confidence:.2f})")

        # Abstraction tolerance with confidence
        if abs_tol := self.extract_abstraction_tolerance(text):
            text_lower = text.lower()
            if abs_tol == "high":
                matches = self._count_keyword_matches(text_lower, self.ABSTRACTION_TOLERANCE_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.ABSTRACTION_TOLERANCE_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["abstraction_tolerance"] = abs_tol
            per_signal_confidence["abstraction_tolerance"] = confidence
            evidence_parts.append(f"abstraction_tolerance={abs_tol} ({confidence:.2f})")

        # Information density tolerance with confidence
        if info_den := self.extract_information_density_tolerance(text):
            text_lower = text.lower()
            if info_den == "high":
                matches = self._count_keyword_matches(text_lower, self.INFORMATION_DENSITY_TOLERANCE_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.INFORMATION_DENSITY_TOLERANCE_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["information_density_tolerance"] = info_den
            per_signal_confidence["information_density_tolerance"] = confidence
            evidence_parts.append(f"information_density_tolerance={info_den} ({confidence:.2f})")

        # Confidence stability with confidence
        if conf_stab := self.extract_confidence_stability(text):
            text_lower = text.lower()
            if conf_stab == "fragile":
                matches = self._count_keyword_matches(text_lower, self.CONFIDENCE_STABILITY_KEYWORDS.get("fragile", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.CONFIDENCE_STABILITY_KEYWORDS.get("stable", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["confidence_stability"] = conf_stab
            per_signal_confidence["confidence_stability"] = confidence
            evidence_parts.append(f"confidence_stability={conf_stab} ({confidence:.2f})")

        # Self-directed learning ability with confidence
        if self_dir := self.extract_self_directed_learning_ability(text):
            text_lower = text.lower()
            if self_dir == "high":
                matches = self._count_keyword_matches(text_lower, self.SELF_DIRECTED_LEARNING_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.SELF_DIRECTED_LEARNING_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["self_directed_learning_ability"] = self_dir
            per_signal_confidence["self_directed_learning_ability"] = confidence
            evidence_parts.append(f"self_directed_learning_ability={self_dir} ({confidence:.2f})")

        # Best explanation style with confidence
        if expl_style := self.extract_best_explanation_style(text):
            text_lower = text.lower()
            matches = self._count_keyword_matches(text_lower, self.BEST_EXPLANATION_STYLE_KEYWORDS.get(expl_style, []))
            confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["best_explanation_style"] = expl_style
            per_signal_confidence["best_explanation_style"] = confidence
            evidence_parts.append(f"best_explanation_style={expl_style} ({confidence:.2f})")

        # Feedback sensitivity with confidence
        if fb_sens := self.extract_feedback_sensitivity(text):
            text_lower = text.lower()
            if fb_sens == "high":
                matches = self._count_keyword_matches(text_lower, self.FEEDBACK_SENSITIVITY_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.FEEDBACK_SENSITIVITY_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["feedback_sensitivity"] = fb_sens
            per_signal_confidence["feedback_sensitivity"] = confidence
            evidence_parts.append(f"feedback_sensitivity={fb_sens} ({confidence:.2f})")

        # Interview confidence with confidence
        if interview_conf := self.extract_interview_confidence(text):
            text_lower = text.lower()
            if interview_conf == "high":
                matches = self._count_keyword_matches(text_lower, self.INTERVIEW_CONFIDENCE_KEYWORDS.get("high", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            else:
                matches = self._count_keyword_matches(text_lower, self.INTERVIEW_CONFIDENCE_KEYWORDS.get("low", []))
                confidence = min(0.6 + (matches * 0.08), 1.0)
            
            signals["interview_confidence"] = interview_conf
            per_signal_confidence["interview_confidence"] = confidence
            evidence_parts.append(f"interview_confidence={interview_conf} ({confidence:.2f})")

        # Calculate overall confidence as average of per-signal confidences
        overall_confidence = sum(per_signal_confidence.values()) / len(per_signal_confidence) if per_signal_confidence else 0.0

        return SignalExtractionResult(
            extracted_signals=signals,
            extraction_method="rule_based",
            confidence=overall_confidence,
            per_signal_confidence=per_signal_confidence,
            reasoning=f"Rule-based extraction found {len(evidence_parts)} signals: {', '.join(evidence_parts)}",
            raw_evidence=text[:100] + "..." if len(text) > 100 else text,
        )
