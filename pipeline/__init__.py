"""
Utility Lookup Pipeline

A refactored architecture for utility lookups with:
- Parallel data source queries
- Cross-validation
- Best-confidence selection
- Enrichment and verification
"""

from .interfaces import (
    UtilityType,
    LookupContext,
    SourceResult,
    PipelineResult,
    DataSource,
)

from .pipeline import LookupPipeline

__all__ = [
    'UtilityType',
    'LookupContext', 
    'SourceResult',
    'PipelineResult',
    'DataSource',
    'LookupPipeline',
]
