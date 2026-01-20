"""
Backward-compatible loader for Texas territory data.

During migration, this module loads data from JSON files but exposes
the same dict names as the original hardcoded dicts.

Usage:
    from data.texas_loader import (
        TEXAS_TDUS,
        TEXAS_ZIP_PREFIX_TO_TDU,
        TEXAS_GAS_LDCS,
        TEXAS_GAS_ZIP_PREFIX,
        TEXAS_GAS_ZIP_OVERRIDES,
    )
"""

import json
from pathlib import Path

_TEXAS_TERRITORIES = None

def _load_texas_territories():
    """Load Texas territories from JSON file."""
    global _TEXAS_TERRITORIES
    if _TEXAS_TERRITORIES is None:
        path = Path(__file__).parent / 'texas_territories.json'
        if path.exists():
            with open(path, 'r') as f:
                _TEXAS_TERRITORIES = json.load(f)
        else:
            # Fallback to empty structure
            _TEXAS_TERRITORIES = {
                'electric': {'tdus': {}, 'zip_to_tdu': {}, 'municipal_cities': {}, 'coops': []},
                'gas': {'ldcs': {}, 'zip_to_ldc': {}, 'zip_overrides': {}}
            }
    return _TEXAS_TERRITORIES


# Lazy-loaded properties that match original dict names
class _LazyDict(dict):
    """Dict that loads data on first access."""
    def __init__(self, loader):
        self._loader = loader
        self._loaded = False
    
    def _ensure_loaded(self):
        if not self._loaded:
            data = self._loader()
            self.update(data)
            self._loaded = True
    
    def __getitem__(self, key):
        self._ensure_loaded()
        return super().__getitem__(key)
    
    def __contains__(self, key):
        self._ensure_loaded()
        return super().__contains__(key)
    
    def get(self, key, default=None):
        self._ensure_loaded()
        return super().get(key, default)
    
    def keys(self):
        self._ensure_loaded()
        return super().keys()
    
    def values(self):
        self._ensure_loaded()
        return super().values()
    
    def items(self):
        self._ensure_loaded()
        return super().items()


# Electric
TEXAS_TDUS = _LazyDict(lambda: _load_texas_territories()['electric']['tdus'])
TEXAS_ZIP_PREFIX_TO_TDU = _LazyDict(lambda: _load_texas_territories()['electric']['zip_to_tdu'])
TEXAS_MUNICIPAL_CITIES = _LazyDict(lambda: _load_texas_territories()['electric']['municipal_cities'])

# Gas
TEXAS_GAS_LDCS = _LazyDict(lambda: _load_texas_territories()['gas']['ldcs'])
TEXAS_GAS_ZIP_PREFIX = _LazyDict(lambda: _load_texas_territories()['gas']['zip_to_ldc'])
TEXAS_GAS_ZIP_OVERRIDES = _LazyDict(lambda: _load_texas_territories()['gas']['zip_overrides'])

# List (not a dict)
def get_texas_coops():
    """Get list of Texas electric cooperatives."""
    return _load_texas_territories()['electric']['coops']

TEXAS_COOPS = get_texas_coops()
