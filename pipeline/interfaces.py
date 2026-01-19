"""
Core interfaces for the utility lookup pipeline.

Defines the abstract base classes and data structures used by all pipeline components.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any


class UtilityType(Enum):
    """Types of utilities we can look up."""
    ELECTRIC = "electric"
    GAS = "gas"
    WATER = "water"


@dataclass
class LookupContext:
    """
    Input context for all data sources.
    
    Contains all the information needed to perform a utility lookup.
    """
    lat: Optional[float]
    lon: Optional[float]
    address: str
    city: str
    county: str
    state: str
    zip_code: str
    utility_type: UtilityType
    
    def __post_init__(self):
        # Normalize state to uppercase
        if self.state:
            self.state = self.state.upper()
        # Normalize ZIP to 5 digits
        if self.zip_code:
            self.zip_code = str(self.zip_code).strip()[:5]


@dataclass
class SourceResult:
    """
    Result from a single data source.
    
    Each data source returns one of these when queried.
    """
    source_name: str
    utility_name: Optional[str]
    confidence_score: int  # 0-100
    match_type: str  # 'point', 'zip', 'county', 'city', 'state'
    
    # Optional contact info
    phone: Optional[str] = None
    website: Optional[str] = None
    
    # Additional metadata
    raw_data: Optional[Dict[str, Any]] = None
    query_time_ms: int = 0
    error: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if this result has a valid utility name."""
        return bool(self.utility_name)


@dataclass
class PipelineResult:
    """
    Final result from the lookup pipeline.
    
    Contains the selected utility, confidence information, and metadata.
    """
    utility_name: Optional[str]
    utility_type: UtilityType
    confidence_score: int  # 0-100
    confidence_level: str  # 'verified', 'high', 'medium', 'low', 'none'
    source: str
    
    # Contact info
    phone: Optional[str] = None
    website: Optional[str] = None
    
    # Brand resolution
    brand_name: Optional[str] = None
    legal_name: Optional[str] = None
    
    # Market info
    deregulated_market: bool = False
    deregulated_note: Optional[str] = None
    
    # Cross-validation
    sources_agreed: bool = True
    agreeing_sources: List[str] = field(default_factory=list)
    disagreeing_sources: List[str] = field(default_factory=list)
    
    # SERP verification
    serp_verified: Optional[bool] = None
    serp_utility: Optional[str] = None
    
    # Debug/timing info
    all_results: List[SourceResult] = field(default_factory=list)
    timing_ms: int = 0
    
    @classmethod
    def empty(cls, utility_type: UtilityType) -> 'PipelineResult':
        """Create an empty result for when no utility is found."""
        return cls(
            utility_name=None,
            utility_type=utility_type,
            confidence_score=0,
            confidence_level='none',
            source='none'
        )
    
    @classmethod
    def confidence_level_from_score(cls, score: int) -> str:
        """Convert numeric score to confidence level string."""
        if score >= 85:
            return 'verified'
        elif score >= 70:
            return 'high'
        elif score >= 50:
            return 'medium'
        else:
            return 'low'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            'NAME': self.brand_name or self.utility_name,
            'TELEPHONE': self.phone,
            'WEBSITE': self.website,
            'STATE': None,  # Filled by caller
            'CITY': None,   # Filled by caller
            '_confidence': self.confidence_level,
            '_confidence_score': self.confidence_score,
            '_source': self.source,
            '_legal_name': self.legal_name,
            '_deregulated_market': self.deregulated_market,
            '_deregulated_note': self.deregulated_note,
            '_sources_agreed': self.sources_agreed,
            '_agreeing_sources': self.agreeing_sources,
            '_disagreeing_sources': self.disagreeing_sources,
            '_serp_verified': self.serp_verified,
            '_timing_ms': self.timing_ms,
        }


class DataSource(ABC):
    """
    Abstract base class for all data sources.
    
    Each data source (GIS, EIA, HIFLD, etc.) implements this interface.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source (e.g., 'state_gis', 'eia_861')."""
        pass
    
    @property
    @abstractmethod
    def supported_types(self) -> List[UtilityType]:
        """Which utility types this source can look up."""
        pass
    
    @property
    @abstractmethod
    def base_confidence(self) -> int:
        """Base confidence score for this source (0-100)."""
        pass
    
    @property
    def timeout_ms(self) -> int:
        """Maximum time to wait for this source (milliseconds)."""
        return 2000  # Default 2 seconds
    
    @abstractmethod
    def query(self, context: LookupContext) -> Optional[SourceResult]:
        """
        Query this data source.
        
        Args:
            context: The lookup context with address/location info
            
        Returns:
            SourceResult if found, None if not applicable or no result.
            Should handle its own errors and return None on failure.
        """
        pass
    
    def supports(self, utility_type: UtilityType) -> bool:
        """Check if this source supports the given utility type."""
        return utility_type in self.supported_types
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name='{self.name}' confidence={self.base_confidence}>"


# Confidence score constants (from confidence_scoring.py)
SOURCE_CONFIDENCE = {
    # Tier 1: Authoritative (90+)
    'user_confirmed': 95,
    'utility_direct_api': 92,
    'franchise_agreement': 92,
    'parcel_data': 90,
    'user_feedback': 88,
    'municipal_utility': 88,
    
    # Tier 2: High Quality (80-89)
    'special_district': 85,
    'state_gis': 85,
    'verified': 85,
    'state_puc_map': 82,
    'zip_override': 80,
    'railroad_commission': 80,
    
    # Tier 3: Good Quality (65-79)
    'findenergy': 78,
    'state_puc': 75,
    'eia_861': 70,
    'supplemental': 70,
    'electric_cooperative': 68,
    'state_ldc_mapping': 65,
    
    # Tier 4: Needs Verification (50-64)
    'google_serp': 60,
    'hifld_polygon': 58,
    'epa_sdwis': 55,
    'county_default': 50,
    
    # Tier 5: Low Confidence (<50)
    'county_match': 45,
    'heuristic': 30,
    'unknown': 15,
}

# Geographic precision bonuses
PRECISION_BONUS = {
    'point': 15,      # Point-in-polygon GIS query
    'address': 12,    # Exact address match
    'zip': 5,         # 5-digit ZIP match
    'zip3': 3,        # 3-digit ZIP prefix
    'county': 1,      # County-level match
    'city': 8,        # City-level match
    'state': 0,       # State-level only
}
