"""
AI-First Utility Selector

Instead of rule-based selection with AI as tie-breaker, this flips the model:
- Data sources generate CANDIDATES (all potential utilities)
- AI evaluates ALL candidates with full context and domain knowledge
- AI makes the final decision with reasoning

The data sources become advisors, the AI becomes the decision maker.
"""

import os
import json
import time
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

from .interfaces import SourceResult, LookupContext, UtilityType


def _load_openai_key():
    """Load OpenAI API key from environment or .env files."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    
    script_dir = Path(__file__).resolve().parent.parent
    env_paths = [
        script_dir / ".env",
        script_dir.parent / "PMD_scrape" / ".env",
    ]
    
    for env_path in env_paths:
        if env_path.exists():
            try:
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            if k == 'OPENAI_API_KEY':
                                os.environ[k] = v
                                return v
            except Exception:
                pass
    return None


# Load state utility knowledge from JSON file
def _load_state_knowledge():
    """Load state utility knowledge base from JSON file."""
    knowledge_path = Path(__file__).parent.parent / 'data' / 'state_utility_knowledge.json'
    if knowledge_path.exists():
        try:
            with open(knowledge_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

STATE_KNOWLEDGE = _load_state_knowledge()

def _get_state_context(state: str, utility_type: str) -> str:
    """Build context string from knowledge base for a specific state and utility type."""
    state_data = STATE_KNOWLEDGE.get(state, {})
    
    if not state_data:
        return """GENERAL UTILITY CONTEXT:
- Municipal utilities serve their specific city limits only
- Large IOUs serve most of a region except where municipals/co-ops exist
- Rural electric cooperatives (EMCs, RECs) serve areas outside city limits
- Special districts may have stale boundary data if cities have annexed the area"""
    
    util_data = state_data.get(utility_type, {})
    landscape = util_data.get('landscape', {})
    data_status = util_data.get('data_status', {})
    
    # Build context string
    lines = [f"{state} {utility_type.upper()} CONTEXT:"]
    
    if landscape.get('description'):
        lines.append(f"- Overview: {landscape['description']}")
    
    if landscape.get('major_players'):
        players = landscape['major_players']
        player_strs = [f"{p['name']} ({p['type']}, {p.get('coverage', 'various areas')})" for p in players[:5]]
        lines.append(f"- Major providers: {', '.join(player_strs)}")
    
    if landscape.get('key_insight'):
        lines.append(f"- KEY INSIGHT: {landscape['key_insight']}")
    
    if data_status.get('confidence'):
        conf = data_status['confidence']
        if conf in ['low', 'very_low', 'low_for_rural']:
            lines.append(f"- DATA WARNING: Our data confidence is {conf}. Consider that the correct provider may not be in our candidates.")
    
    if data_status.get('missing'):
        lines.append(f"- Known data gaps: {', '.join(data_status['missing'][:3])}")
    
    return "\n".join(lines)


@dataclass
class AIDecision:
    """Result from AI selector."""
    utility_name: str
    utility_type: str
    confidence: float
    selected_source: str
    reasoning: str
    all_candidates: List[Dict]


class AISelector:
    """
    AI-first utility selector that evaluates all candidates with full context.
    
    Data sources provide candidates, AI makes the decision.
    """
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.api_key = _load_openai_key()
        self.model = model
        if self.api_key:
            print(f"AISelector: OpenAI API key loaded (ends with ...{self.api_key[-4:]})")
        else:
            print("AISelector: WARNING - No OpenAI API key found")
    
    def select(
        self,
        context: LookupContext,
        candidates: List[SourceResult]
    ) -> AIDecision:
        """
        Given all candidates from data sources, use AI to select the correct utility.
        
        Args:
            context: Location and address info
            candidates: ALL results from ALL sources (not pre-filtered)
            
        Returns:
            AIDecision with selected utility and reasoning
        """
        # Filter to valid candidates
        valid_candidates = [c for c in candidates if c.utility_name]
        
        if not valid_candidates:
            return AIDecision(
                utility_name=None,
                utility_type=context.utility_type.value,
                confidence=0,
                selected_source="none",
                reasoning="No candidates found from any source",
                all_candidates=[]
            )
        
        # If only one candidate, use it
        if len(valid_candidates) == 1:
            c = valid_candidates[0]
            return AIDecision(
                utility_name=c.utility_name,
                utility_type=context.utility_type.value,
                confidence=c.confidence_score / 100.0,
                selected_source=c.source_name,
                reasoning=f"Single candidate from {c.source_name}",
                all_candidates=[self._candidate_to_dict(c)]
            )
        
        # Multiple candidates - let AI decide
        return self._ai_select(context, valid_candidates)
    
    def _ai_select(
        self,
        context: LookupContext,
        candidates: List[SourceResult]
    ) -> AIDecision:
        """Use AI to evaluate candidates and make a decision."""
        
        if not self.api_key:
            # Fallback to highest confidence
            best = max(candidates, key=lambda x: x.confidence_score)
            return AIDecision(
                utility_name=best.utility_name,
                utility_type=context.utility_type.value,
                confidence=best.confidence_score / 100.0 * 0.8,
                selected_source=best.source_name,
                reasoning="Fallback: No API key, using highest confidence candidate",
                all_candidates=[self._candidate_to_dict(c) for c in candidates]
            )
        
        # Build rich context for AI
        prompt = self._build_prompt(context, candidates)
        
        try:
            import requests
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system", 
                            "content": "You are a utility service territory expert. Your job is to determine which utility company actually provides service to a specific address. You have deep knowledge of how utilities work in the US - municipal utilities, IOUs, co-ops, special districts, deregulation, etc. Think carefully and explain your reasoning."
                        },
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1000
                },
                timeout=20
            )
            response.raise_for_status()
            
            result_text = response.json()["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            result = json.loads(result_text.strip())
            
            return AIDecision(
                utility_name=result["selected_utility"],
                utility_type=context.utility_type.value,
                confidence=result["confidence"],
                selected_source=result["selected_source"],
                reasoning=result["reasoning"],
                all_candidates=[self._candidate_to_dict(c) for c in candidates]
            )
            
        except Exception as e:
            print(f"AISelector error: {e}")
            # Fallback to highest confidence
            best = max(candidates, key=lambda x: x.confidence_score)
            return AIDecision(
                utility_name=best.utility_name,
                utility_type=context.utility_type.value,
                confidence=best.confidence_score / 100.0 * 0.8,
                selected_source=best.source_name,
                reasoning=f"Fallback due to error: {e}",
                all_candidates=[self._candidate_to_dict(c) for c in candidates]
            )
    
    def _build_prompt(self, context: LookupContext, candidates: List[SourceResult]) -> str:
        """Build a rich prompt with all context for AI decision making."""
        
        utility_type = context.utility_type.value.upper()
        
        # Get state-specific context from knowledge base
        state_context = _get_state_context(context.state, context.utility_type.value)
        
        # Build candidate list with rich details
        candidates_text = []
        for i, c in enumerate(candidates, 1):
            details = [
                f"{i}. **{c.utility_name}**",
                f"   - Source: {c.source_name}",
                f"   - Confidence: {c.confidence_score}%",
                f"   - Match type: {c.match_type}",
            ]
            if c.phone:
                details.append(f"   - Phone: {c.phone}")
            if c.website:
                details.append(f"   - Website: {c.website}")
            if c.raw_data:
                # Add relevant raw data hints
                if 'city' in c.raw_data:
                    details.append(f"   - Matched city: {c.raw_data['city']}")
                if 'district_id' in c.raw_data:
                    details.append(f"   - District ID: {c.raw_data['district_id']}")
                if 'type' in c.raw_data:
                    details.append(f"   - District type: {c.raw_data['type']}")
            candidates_text.append("\n".join(details))
        
        candidates_str = "\n\n".join(candidates_text)
        
        # Determine area type hints
        area_hints = []
        if context.city:
            area_hints.append(f"City: {context.city}")
        if context.county:
            area_hints.append(f"County: {context.county}")
        
        prompt = f"""# {utility_type} UTILITY SELECTION

## ADDRESS
{context.address}
{context.city}, {context.state} {context.zip_code}
{', '.join(area_hints)}

## CANDIDATES FROM DATA SOURCES
{candidates_str}

## STATE-SPECIFIC KNOWLEDGE
{state_context}

## SOURCE RELIABILITY GUIDE
- **municipal_water / municipal_electric / municipal_gas**: City-owned utilities. Very reliable IF the address is within that city's limits.
- **special_district_water**: MUDs, water districts. Boundary data may be stale if city has annexed the area.
- **state_gis / state_gis_gas**: State GIS boundary data. Usually accurate for service territories.
- **electric_coop**: Rural electric cooperatives. Authoritative for their service areas.
- **eia_861**: Federal EIA data. Good for identifying utilities but less precise on boundaries.
- **hifld**: Federal HIFLD dataset. Broad coverage but sometimes outdated.
- **zip_mapping_gas**: ZIP-code level gas utility mapping. Good for general area but not precise.

## YOUR TASK
Based on the address, candidates, and your knowledge of utility service territories:

1. **Analyze the location**: Is this urban, suburban, or rural? Inside city limits or unincorporated?

2. **Evaluate each candidate**: Consider the source reliability, match type, and whether it makes sense for this location.

3. **Apply domain knowledge**: Use what you know about utilities in {context.state} and this specific area.

4. **Make your decision**: Which utility actually provides {utility_type.lower()} service to this address?

Respond in JSON format:
```json
{{
    "selected_utility": "exact utility name",
    "selected_source": "source_name that provided this utility",
    "confidence": 0.XX,
    "reasoning": "Your step-by-step reasoning explaining WHY this utility serves this address, referencing specific factors that led to your decision"
}}
```"""
        
        return prompt
    
    def _candidate_to_dict(self, c: SourceResult) -> Dict:
        """Convert a SourceResult to a dict for storage."""
        return {
            "utility_name": c.utility_name,
            "source": c.source_name,
            "confidence": c.confidence_score,
            "match_type": c.match_type,
            "phone": c.phone,
            "website": c.website
        }


# Global instance
_ai_selector = None

def get_ai_selector() -> AISelector:
    """Get or create the global AISelector instance."""
    global _ai_selector
    if _ai_selector is None:
        _ai_selector = AISelector()
    return _ai_selector
