"""
Resident Guide module for PM utility guides.
"""

from .fallback_templates import get_fallback_template, FALLBACK_TEMPLATES
from .deregulated_explainers import (
    get_deregulated_explainer,
    is_deregulated_state,
    TEXAS_DELIVERY_UTILITIES
)

__all__ = [
    'get_fallback_template',
    'FALLBACK_TEMPLATES',
    'get_deregulated_explainer',
    'is_deregulated_state',
    'TEXAS_DELIVERY_UTILITIES'
]
