"""
OpenAI Smart Selector for Utility Selection

Replaces rule-based utility selection with an LLM that reads all source results
and makes an informed decision about which utility serves a given address.

Key benefits:
- Fuzzy name matching (understands "CPS Energy" = "City Public Service")
- Contextual reasoning (weighs multiple sources intelligently)
- Edge case handling (spots suspicious results)
- Explainable decisions (provides reasoning for auditing)
"""

import os
import json
import time
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from pathlib import Path

from .interfaces import SourceResult, PipelineResult, UtilityType, LookupContext


def _load_openai_key():
    """Load OpenAI API key from environment or .env files."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    
    # Try to load from .env files
    script_dir = Path(__file__).resolve().parent.parent
    env_paths = [
        script_dir / ".env",
        script_dir.parent / "PMD_scrape" / ".env",
        script_dir.parent / "BrightData_AppFolio_Scraper" / ".env",
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

# Cache directory
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'smart_selector_cache')


@dataclass
class SelectionResult:
    """Result from the smart selector."""
    utility_name: str
    utility_type: str
    confidence: float
    confidence_level: str  # "verified", "high", "medium", "low"
    sources_agreed: bool
    dissenting_sources: List[str]
    reasoning: str
    selected_source: str


class SmartSelector:
    """
    LLM-powered utility selector that intelligently chooses between
    conflicting source results.
    """
    
    def __init__(self):
        self.api_key = _load_openai_key()
        self.model = "gpt-4o-mini"  # Fast and cheap, sufficient for this task
        self.cache = {}
        self._load_cache()
        if self.api_key:
            print(f"SmartSelector: OpenAI API key loaded (ends with ...{self.api_key[-4:]})")
        else:
            print("SmartSelector: WARNING - No OpenAI API key found, using fallback selection")
    
    def _load_cache(self):
        """Load cached decisions from disk."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, 'decisions.json')
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    self.cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.cache = {}
    
    def _save_cache(self):
        """Save cached decisions to disk."""
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(CACHE_DIR, 'decisions.json')
        with open(cache_file, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    def _get_cache_key(self, zip_code: str, utility_type: str, source_names: List[str]) -> str:
        """Generate cache key for a decision."""
        # Use ZIP prefix + utility type + sorted source names
        sources_hash = hashlib.md5('|'.join(sorted(source_names)).encode()).hexdigest()[:8]
        return f"{zip_code[:3]}:{utility_type}:{sources_hash}"
    
    def select_utility(
        self,
        context: LookupContext,
        source_results: List[SourceResult]
    ) -> SelectionResult:
        """
        Given results from multiple sources, select the most likely correct utility.
        
        Args:
            context: The lookup context with address info
            source_results: List of results from different data sources
            
        Returns:
            SelectionResult with the selected utility and reasoning
        """
        # Filter to valid results
        valid_results = [r for r in source_results if r.utility_name]
        
        if not valid_results:
            return SelectionResult(
                utility_name=None,
                utility_type=context.utility_type.value,
                confidence=0,
                confidence_level="none",
                sources_agreed=True,
                dissenting_sources=[],
                reasoning="No sources returned results",
                selected_source="none"
            )
        
        # If only one source returned data, use it directly
        if len(valid_results) == 1:
            r = valid_results[0]
            return SelectionResult(
                utility_name=r.utility_name,
                utility_type=context.utility_type.value,
                confidence=r.confidence_score / 100.0,
                confidence_level=self._confidence_level(r.confidence_score / 100.0),
                sources_agreed=True,
                dissenting_sources=[],
                reasoning=f"Single source ({r.source_name}) returned result",
                selected_source=r.source_name
            )
        
        # Check if all sources agree (normalized names match)
        normalized_names = [self._normalize_name(r.utility_name) for r in valid_results]
        if len(set(normalized_names)) == 1:
            best = max(valid_results, key=lambda x: x.confidence_score)
            return SelectionResult(
                utility_name=best.utility_name,
                utility_type=context.utility_type.value,
                confidence=min(0.98, best.confidence_score / 100.0 + 0.10),
                confidence_level="verified",
                sources_agreed=True,
                dissenting_sources=[],
                reasoning=f"All {len(valid_results)} sources agree",
                selected_source=best.source_name
            )
        
        # Check cache
        cache_key = self._get_cache_key(
            context.zip_code, 
            context.utility_type.value,
            [r.source_name for r in valid_results]
        )
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            # Verify cached utility is still in results
            for r in valid_results:
                if self._normalize_name(r.utility_name) == self._normalize_name(cached.get('utility_name', '')):
                    return SelectionResult(
                        utility_name=r.utility_name,
                        utility_type=context.utility_type.value,
                        confidence=cached.get('confidence', 0.85),
                        confidence_level=cached.get('confidence_level', 'high'),
                        sources_agreed=cached.get('sources_agreed', False),
                        dissenting_sources=cached.get('dissenting_sources', []),
                        reasoning=f"Cached decision: {cached.get('reasoning', '')}",
                        selected_source=r.source_name
                    )
        
        # Sources disagree - use LLM to evaluate
        result = self._llm_select(context, valid_results)
        
        # Cache the decision
        self.cache[cache_key] = {
            'utility_name': result.utility_name,
            'confidence': result.confidence,
            'confidence_level': result.confidence_level,
            'sources_agreed': result.sources_agreed,
            'dissenting_sources': result.dissenting_sources,
            'reasoning': result.reasoning,
            'timestamp': time.time()
        }
        self._save_cache()
        
        return result
    
    def _llm_select(
        self,
        context: LookupContext,
        source_results: List[SourceResult]
    ) -> SelectionResult:
        """
        Use OpenAI to evaluate conflicting source results.
        """
        if not self.api_key:
            # No API key - fall back to highest confidence source
            return self._fallback_select(context, source_results)
        
        # Build the prompt
        sources_text = "\n".join([
            f"- {r.source_name}: \"{r.utility_name}\" (confidence: {r.confidence_score}%)"
            for r in source_results
        ])
        
        utility_type = context.utility_type.value
        
        prompt = f"""You are a utility service territory expert. Given an address and results from multiple data sources, determine the most likely correct {utility_type} utility provider.

ADDRESS:
{context.address}
{context.city}, {context.state} {context.zip_code}

SOURCE RESULTS:
{sources_text}

CRITICAL RULES:
1. **Municipal utilities are authoritative for their city** - If the address is IN a city that has a municipal utility with that city's name, the municipal is correct. "Philadelphia Gas Works" serves Philadelphia, "Austin Energy" serves Austin, "Seattle City Light" serves Seattle.
2. **Municipal utilities ONLY serve their specific city limits** - "City of Homestead" only serves Homestead, NOT Miami. If the address city doesn't match the municipal utility's city, DO NOT select the municipal.
3. **For gas: PECO is electric-only in PA** - Philadelphia Gas Works (PGW) is the gas utility for Philadelphia. PECO provides electric service, not gas, in Philadelphia city proper.
4. **Large IOUs serve most of the region** - Florida Power & Light serves most of South Florida, Duke Energy serves most of NC. These are the default unless the address is specifically within a municipal territory.
5. **Aliases are common** - "FPL" = "Florida Power & Light", "BGE" = "Baltimore Gas & Electric", "PSE&G" = "Public Service Electric & Gas", "Dominion Energy" = "Virginia Electric & Power Co"
6. **State GIS and EIA data are authoritative** - Trust state_gis and eia sources over hifld for boundary accuracy.
7. **Ignore garbage results** - Skip results like "OR ELECTRIC", "TOWN OF X - (STATE)", or very short names unless they match the address city exactly.

Respond in JSON format ONLY (no markdown):
{{"selected_utility": "exact utility name to use", "selected_source": "which source you're trusting", "confidence": 0.XX, "sources_agree": false, "dissenting_sources": ["list", "of", "sources", "that", "disagree"], "reasoning": "Brief explanation of your decision"}}"""

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
                        {"role": "system", "content": "You are a utility service territory analyst. Always respond with valid JSON only, no markdown."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500
                },
                timeout=15
            )
            response.raise_for_status()
            
            result_data = response.json()
            result_text = result_data["choices"][0]["message"]["content"]
            
            # Parse JSON from response (handle markdown code blocks)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]
            
            result = json.loads(result_text.strip())
            
            return SelectionResult(
                utility_name=result["selected_utility"],
                utility_type=utility_type,
                confidence=result["confidence"],
                confidence_level=self._confidence_level(result["confidence"]),
                sources_agreed=result.get("sources_agree", False),
                dissenting_sources=result.get("dissenting_sources", []),
                reasoning=result["reasoning"],
                selected_source=result["selected_source"]
            )
            
        except Exception as e:
            print(f"SmartSelector LLM error: {e}")
            return self._fallback_select(context, source_results)
    
    def _fallback_select(
        self,
        context: LookupContext,
        source_results: List[SourceResult]
    ) -> SelectionResult:
        """Fallback to highest confidence source when LLM is unavailable."""
        # Prefer municipal > state_gis > eia > hifld > county_default
        SOURCE_PRIORITY = {
            'municipal': 100,
            'municipal_gas': 100,
            'state_gis': 90,
            'state_gis_gas': 90,
            'electric_coop': 80,
            'zip_mapping_gas': 75,
            'eia_861': 70,
            'hifld': 40,
            'hifld_gas': 40,
            'county_default': 30,
            'county_default_gas': 30,
        }
        
        # Score each result
        scored = []
        for r in source_results:
            score = r.confidence_score + SOURCE_PRIORITY.get(r.source_name, 0) * 0.3
            scored.append((score, r))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        
        dissenting = [r.source_name for _, r in scored[1:] 
                      if self._normalize_name(r.utility_name) != self._normalize_name(best.utility_name)]
        
        return SelectionResult(
            utility_name=best.utility_name,
            utility_type=context.utility_type.value,
            confidence=best.confidence_score / 100.0 * 0.9,  # Penalize for no LLM verification
            confidence_level="medium",
            sources_agreed=len(dissenting) == 0,
            dissenting_sources=dissenting,
            reasoning=f"Fallback: using highest priority source ({best.source_name})",
            selected_source=best.source_name
        )
    
    def _normalize_name(self, name: str) -> str:
        """Normalize utility name for comparison."""
        if not name:
            return ""
        name = name.upper()
        # Remove common suffixes
        for suffix in [" INC", " LLC", " CO", " CORP", " CORPORATION", " COMPANY", 
                       " ELECTRIC", " ELEC", " UTILITY", " UTILITIES", " COOP", 
                       " COOPERATIVE", " EMC", " REC", " PUD", " MUD", " - ", " (", ")"]:
            name = name.replace(suffix, "")
        # Remove punctuation
        name = "".join(c for c in name if c.isalnum() or c == " ")
        return name.strip()
    
    def _confidence_level(self, confidence: float) -> str:
        if confidence >= 0.95:
            return "verified"
        elif confidence >= 0.85:
            return "high"
        elif confidence >= 0.70:
            return "medium"
        else:
            return "low"


# Global instance for reuse
_smart_selector = None

def get_smart_selector() -> SmartSelector:
    """Get or create the global SmartSelector instance."""
    global _smart_selector
    if _smart_selector is None:
        _smart_selector = SmartSelector()
    return _smart_selector
