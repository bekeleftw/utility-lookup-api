"""
Main pipeline orchestrator for utility lookups.

Coordinates parallel queries to data sources, cross-validation, and result selection.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import Dict, List, Optional, Tuple

from .interfaces import (
    UtilityType,
    LookupContext,
    SourceResult,
    PipelineResult,
    DataSource,
    SOURCE_CONFIDENCE,
    PRECISION_BONUS,
)
from .smart_selector import get_smart_selector, SmartSelector
from .ai_selector import get_ai_selector, AISelector


class LookupPipeline:
    """
    Orchestrates the utility lookup process.
    
    Pipeline stages:
    1. Query all applicable data sources in parallel
    2. Cross-validate results
    3. Select best result based on confidence
    4. Enrich with contact info and brand resolution
    5. Optional SERP verification for low-confidence results
    """
    
    def __init__(self, sources: List[DataSource] = None, max_workers: int = 5):
        """
        Initialize the pipeline.
        
        Args:
            sources: List of DataSource implementations to query
            max_workers: Maximum parallel queries
        """
        self.sources = sources or []
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Feature flags for gradual rollout
        self.enable_cross_validation = True
        self.enable_serp_verification = True
        self.enable_smart_selector = True  # Legacy - use SmartSelector for tie-breaking
        self.enable_ai_selector = True     # NEW: AI-first selection (data sources as advisors)
        self.serp_confidence_threshold = 70
        
        # Initialize selectors
        self._smart_selector = None
        self._ai_selector = None
        
        if self.enable_ai_selector:
            try:
                self._ai_selector = get_ai_selector()
            except Exception as e:
                print(f"Failed to initialize AISelector: {e}")
        
        if self.enable_smart_selector and not self._ai_selector:
            try:
                self._smart_selector = get_smart_selector()
            except Exception as e:
                print(f"Failed to initialize SmartSelector: {e}")
    
    def add_source(self, source: DataSource) -> None:
        """Add a data source to the pipeline."""
        self.sources.append(source)
    
    def lookup(self, context: LookupContext) -> PipelineResult:
        """
        Main entry point for utility lookup.
        
        Args:
            context: LookupContext with address/location info
            
        Returns:
            PipelineResult with the best utility match
        """
        start_time = time.time()
        
        # 1. Get applicable sources for this utility type
        applicable_sources = [s for s in self.sources if s.supports(context.utility_type)]
        
        if not applicable_sources:
            return PipelineResult.empty(context.utility_type)
        
        # 2. Query all sources in parallel
        results = self._query_parallel(applicable_sources, context)
        
        # Filter to valid results
        valid_results = [r for r in results if r.is_valid]
        
        if not valid_results:
            result = PipelineResult.empty(context.utility_type)
            result.timing_ms = int((time.time() - start_time) * 1000)
            result.all_results = results
            return result
        
        # 3. Cross-validate if enabled (for reporting, not decision making)
        if self.enable_cross_validation and len(valid_results) > 1:
            cv_result = self._cross_validate(valid_results)
        else:
            cv_result = None
        
        # 4. Select best result
        # Check if we have a high-confidence municipal match - skip AI if so
        municipal_match = None
        for r in valid_results:
            if r.source_name in ('municipal', 'municipal_electric', 'municipal_gas', 'municipal_water') and r.confidence_score >= 85:
                municipal_match = r
                break
        
        # Skip AI selector if we have a clear municipal match (saves 2-5 seconds)
        if municipal_match:
            primary = municipal_match
            if cv_result is None:
                cv_result = {}
            cv_result['ai_selector_skipped'] = 'high_confidence_municipal'
        # NEW: AI-first selection - AI evaluates ALL candidates with full context
        elif self._ai_selector and len(valid_results) > 1:
            # AI-first: Let AI evaluate all candidates and make the decision
            ai_decision = self._ai_selector.select(context, valid_results)
            
            # Find the matching source result
            primary = None
            for r in valid_results:
                if r.utility_name == ai_decision.utility_name or r.source_name == ai_decision.selected_source:
                    primary = r
                    break
            
            if not primary:
                # AI chose something not in results (shouldn't happen but handle it)
                primary = SourceResult(
                    source_name=ai_decision.selected_source,
                    utility_name=ai_decision.utility_name,
                    confidence_score=int(ai_decision.confidence * 100),
                    match_type='ai_selector'
                )
            
            # Store AI reasoning
            if cv_result is None:
                cv_result = {}
            cv_result['ai_selector_used'] = True
            cv_result['ai_selector_reasoning'] = ai_decision.reasoning
            
        elif self._smart_selector and cv_result and not cv_result.get('sources_agreed', True):
            # Legacy: Use SmartSelector for disagreement resolution
            selection = self._smart_selector.select_utility(context, valid_results)
            
            primary = None
            for r in valid_results:
                if r.utility_name == selection.utility_name or r.source_name == selection.selected_source:
                    primary = r
                    break
            
            if not primary:
                primary = SourceResult(
                    source_name=selection.selected_source,
                    utility_name=selection.utility_name,
                    confidence_score=int(selection.confidence * 100),
                    match_type='smart_selector'
                )
            
            cv_result['smart_selector_used'] = True
            cv_result['smart_selector_reasoning'] = selection.reasoning
            cv_result['confidence_adjustment'] = int((selection.confidence - 0.7) * 50)
        else:
            # Fallback: rule-based selection
            primary = self._select_primary(valid_results, cv_result)
        
        # 5. Build pipeline result
        result = self._build_result(primary, context, cv_result)
        result.all_results = results
        
        # 6. Enrich with contact info and brand resolution
        result = self._enrich(result, context)
        
        # 7. SERP verification - only when sources have a meaningful disagreement
        # Simple rule: clear majority = done, close split = ask the internet
        needs_serp = (
            self.enable_serp_verification and 
            not result.sources_agreed and
            len(result.disagreeing_sources) >= len(result.agreeing_sources)  # True tie or minority wins
        )
        if needs_serp:
            result = self._verify_with_serp(result, context)
        
        result.timing_ms = int((time.time() - start_time) * 1000)
        
        return result
    
    def _query_parallel(
        self, 
        sources: List[DataSource], 
        context: LookupContext
    ) -> List[SourceResult]:
        """
        Query multiple sources in parallel.
        
        Implements short-circuit optimization: if a high-confidence result
        is found early, cancel remaining queries.
        """
        futures = {}
        results = []
        
        # Submit all queries
        for source in sources:
            future = self.executor.submit(self._safe_query, source, context)
            futures[future] = source
        
        # Collect results as they complete
        for future in as_completed(futures, timeout=3.0):
            source = futures[future]
            try:
                result = future.result(timeout=0.1)
                if result:
                    results.append(result)
                    
                    # Short-circuit: if we get a 95+ confidence result, we're done
                    if result.confidence_score >= 95:
                        # Cancel remaining futures
                        for f in futures:
                            if not f.done():
                                f.cancel()
                        break
                        
            except TimeoutError:
                # Source took too long
                results.append(SourceResult(
                    source_name=source.name,
                    utility_name=None,
                    confidence_score=0,
                    match_type='none',
                    error='timeout'
                ))
            except Exception as e:
                results.append(SourceResult(
                    source_name=source.name,
                    utility_name=None,
                    confidence_score=0,
                    match_type='none',
                    error=str(e)
                ))
        
        return results
    
    def _safe_query(
        self, 
        source: DataSource, 
        context: LookupContext
    ) -> Optional[SourceResult]:
        """Query a source with error handling and timing."""
        start = time.time()
        try:
            result = source.query(context)
            if result:
                result.query_time_ms = int((time.time() - start) * 1000)
            return result
        except Exception as e:
            return SourceResult(
                source_name=source.name,
                utility_name=None,
                confidence_score=0,
                match_type='none',
                error=str(e),
                query_time_ms=int((time.time() - start) * 1000)
            )
    
    def _cross_validate(self, results: List[SourceResult]) -> Dict:
        """
        Cross-validate results from multiple sources.
        
        Returns dict with:
        - agreeing_sources: list of source names that agree
        - disagreeing_sources: list of source names that disagree
        - confidence_adjustment: points to add/subtract
        - primary_name: the utility name most sources agree on
        """
        from serp_verification import normalize_utility_name, is_alias
        
        # Group results by normalized utility name
        groups: Dict[str, List[SourceResult]] = {}
        
        for result in results:
            norm_name = normalize_utility_name(result.utility_name)
            
            # Check if this matches an existing group
            matched_group = None
            for group_name in groups:
                if is_alias(norm_name, group_name):
                    matched_group = group_name
                    break
            
            if matched_group:
                groups[matched_group].append(result)
            else:
                groups[norm_name] = [result]
        
        # Find the largest group
        sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
        top_group_name, top_group = sorted_groups[0]
        
        agreeing = [r.source_name for r in top_group]
        disagreeing = [r.source_name for r in results if r.source_name not in agreeing]
        
        # Calculate confidence adjustment
        total = len(results)
        agree_count = len(agreeing)
        
        if agree_count == total:
            adjustment = 20  # Full agreement
        elif agree_count > total / 2:
            adjustment = 10  # Majority agreement
        else:
            adjustment = -10  # Split
        
        return {
            'agreeing_sources': agreeing,
            'disagreeing_sources': disagreeing,
            'confidence_adjustment': adjustment,
            'primary_name': top_group[0].utility_name,  # Use original name
            'sources_agreed': len(disagreeing) == 0,
        }
    
    def _select_primary(
        self, 
        results: List[SourceResult], 
        cv_result: Optional[Dict]
    ) -> SourceResult:
        """
        Select the best result based on confidence and cross-validation.
        
        Priority order (highest confidence sources first):
        1. Municipal utilities (88) - most authoritative for cities they serve
        2. State GIS (85) - authoritative point-in-polygon
        3. Co-ops (68) - reliable for rural areas
        4. EIA (70) - good ZIP-level data
        5. HIFLD (58) - national coverage but less accurate
        6. County default (50) - fallback only
        """
        if not results:
            return None
        
        # Source priority order - higher priority sources win ties
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
        
        # Check for municipal vs special_district conflict for water in Texas
        # Texas cities often take over MUD services but MUD boundaries remain in TCEQ data
        has_municipal_water = any(r.source_name == 'municipal_water' and r.utility_name for r in results)
        has_special_district = any(r.source_name == 'special_district_water' and r.utility_name for r in results)
        prefer_municipal_over_special = has_municipal_water and has_special_district
        
        for r in results:
            # Base score from source confidence
            score = r.confidence_score
            
            # Add precision bonus
            score += PRECISION_BONUS.get(r.match_type, 0)
            
            # Add source priority bonus (scaled down to not overwhelm confidence)
            priority = SOURCE_PRIORITY.get(r.source_name, 0)
            score += priority * 0.3  # 30% weight on priority
            
            # SCALABLE FIX: When both municipal and special_district match for water,
            # prefer municipal because Texas cities typically take over MUD services
            # even though MUD boundaries remain in TCEQ records
            if prefer_municipal_over_special:
                if r.source_name == 'municipal_water':
                    score += 15  # Boost municipal to win over special district
                elif r.source_name == 'special_district_water':
                    score -= 10  # Penalize special district when municipal exists
            
            # Cross-validation bonus (reduced weight - don't let bad sources gang up)
            if cv_result and r.source_name in cv_result.get('agreeing_sources', []):
                # Only add CV bonus for high-quality sources
                if priority >= 70:
                    score += cv_result.get('confidence_adjustment', 0) * 0.5
            
            scored.append((score, r))
        
        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)
        
        return scored[0][1]
    
    def _build_result(
        self, 
        primary: SourceResult, 
        context: LookupContext,
        cv_result: Optional[Dict]
    ) -> PipelineResult:
        """Build the final pipeline result from the selected source result."""
        
        # Calculate final confidence
        confidence = primary.confidence_score
        confidence += PRECISION_BONUS.get(primary.match_type, 0)
        
        if cv_result:
            if primary.source_name in cv_result.get('agreeing_sources', []):
                confidence += cv_result.get('confidence_adjustment', 0)
        
        # Cap at 100
        confidence = min(100, max(0, confidence))
        
        return PipelineResult(
            utility_name=primary.utility_name,
            utility_type=context.utility_type,
            confidence_score=confidence,
            confidence_level=PipelineResult.confidence_level_from_score(confidence),
            source=primary.source_name,
            phone=primary.phone,
            website=primary.website,
            sources_agreed=cv_result.get('sources_agreed', True) if cv_result else True,
            agreeing_sources=cv_result.get('agreeing_sources', []) if cv_result else [],
            disagreeing_sources=cv_result.get('disagreeing_sources', []) if cv_result else [],
        )
    
    def _enrich(self, result: PipelineResult, context: LookupContext) -> PipelineResult:
        """Enrich result with brand resolution and deregulated market info."""
        try:
            from brand_resolver import resolve_brand_name_with_fallback
            from deregulated_markets import is_deregulated_state, get_deregulated_note
            
            # Brand resolution
            if result.utility_name:
                brand, legal = resolve_brand_name_with_fallback(result.utility_name, context.state)
                if brand:
                    result.brand_name = brand
                if legal:
                    result.legal_name = legal
            
            # Deregulated market check (electric only)
            if context.utility_type == UtilityType.ELECTRIC:
                result.deregulated_market = is_deregulated_state(context.state)
                if result.deregulated_market:
                    result.deregulated_note = get_deregulated_note(context.state)
                    
        except ImportError:
            pass  # Modules not available
        
        return result
    
    def _verify_with_serp(
        self, 
        result: PipelineResult, 
        context: LookupContext
    ) -> PipelineResult:
        """
        SERP verification to break ties when sources disagree.
        
        Simple rule: if SERP finds a utility, use it to validate or override.
        """
        try:
            from serp_verification import verify_utility_via_serp, is_alias
            
            serp_result = verify_utility_via_serp(
                address=context.address,
                city=context.city,
                state=context.state,
                utility_type=context.utility_type.value,
                expected_utility=result.utility_name or '',
                zip_code=context.zip_code
            )
            
            result.serp_verified = serp_result.verified
            result.serp_utility = serp_result.serp_utility
            
            if serp_result.serp_utility:
                # SERP found something - use it to break the tie
                if serp_result.verified:
                    # SERP confirms our selection - boost confidence
                    result.confidence_score = min(100, result.confidence_score + 15)
                    result.confidence_level = 'verified'
                else:
                    # SERP disagrees - check if SERP utility matches any disagreeing source
                    for source_result in result.all_results:
                        if source_result.utility_name and is_alias(serp_result.serp_utility, source_result.utility_name):
                            # SERP agrees with a different source - switch to it
                            result.utility_name = source_result.utility_name
                            result.source = f"{source_result.source_name}+serp"
                            result.phone = source_result.phone
                            result.website = source_result.website
                            result.confidence_score = 85  # SERP-verified
                            result.confidence_level = 'verified'
                            result.serp_verified = True
                            break
                    else:
                        # SERP found something new that doesn't match any source
                        # DON'T override SmartSelector's decision - SERP web scraping is less reliable
                        # than our curated data sources. Just note the discrepancy.
                        result.serp_verified = False
                        result.serp_utility = serp_result.serp_utility
                        # Keep the SmartSelector's decision but note SERP disagreed
            
        except Exception as e:
            # SERP failed - keep original result but note the failure
            result.serp_verified = None
        
        return result
    
    def shutdown(self):
        """Shutdown the thread pool executor."""
        self.executor.shutdown(wait=False)
